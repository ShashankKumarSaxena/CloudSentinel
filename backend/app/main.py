from contextlib import asynccontextmanager
from dataclasses import asdict
import hmac
from html import escape
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .auth import AuthService, AuthError, COOKIE_NAME, SESSION_HOURS, audit
from .models import (Inventory, TriageUpdate, CollectionRequest, TrainingDataset,
                     LoginRequest, UserCreate, UserUpdate, PasswordChange, ScheduleCreate, ScheduleUpdate)
from .ml import ModelService
from .collectors import CollectionError
from .engine import ScanEngine
from .monitoring import MonitorWorker, BusyOperation
from .notifications import EmailDelivery
from .operations import Operations, OperationError
from .rules import RULES
from .store import Store

ROOT = Path(__file__).resolve().parents[2]
MAX_IMPORT_BYTES = 2 * 1024 * 1024
PUBLIC_ROUTES = {('GET', '/api/v1/health'), ('GET', '/api/v1/ready'),
                 ('GET', '/api/v1/auth/status'), ('POST', '/api/v1/auth/login')}


def create_app(db_path: Path | None = None, model_dir: Path | None = None, monitoring_enabled: bool | None = None) -> FastAPI:
    store = Store(db_path or Path(os.environ.get('CLOUDSENTINEL_DB', ROOT / '.runtime/cloudsentinel.db')))
    model = ModelService(model_dir or store.path.parent / 'models')
    auth = AuthService(store)
    delivery = EmailDelivery()
    operations = Operations(store, delivery.enabled, os.environ.get('CLOUDSENTINEL_ALERT_MIN_SEVERITY', 'high'))
    engine = ScanEngine(store, model, operations)
    worker = MonitorWorker(operations, engine, delivery, enabled=monitoring_enabled if monitoring_enabled is not None else os.environ.get('CLOUDSENTINEL_MONITORING', '1') == '1')
    secure_cookies = os.environ.get('CLOUDSENTINEL_SECURE_COOKIES') == '1'
    allowed_hosts = [value.strip() for value in os.environ.get('CLOUDSENTINEL_ALLOWED_HOSTS', '127.0.0.1,localhost,testserver').split(',') if value.strip()]
    if not allowed_hosts or '*' in allowed_hosts:
        raise ValueError('Configure explicit allowed hosts; wildcard hosts are not supported.')

    @asynccontextmanager
    async def lifespan(app):
        await run_in_threadpool(model.ensure_default)
        if store.get_scan() is None:
            await run_in_threadpool(engine.demo, 'system', 'initial-synthetic-snapshot')
        worker.start()
        try:
            yield
        finally:
            await run_in_threadpool(worker.stop)

    app = FastAPI(title='CloudSentinel API', version='0.3.0', lifespan=lifespan,
                  description='Authenticated cloud security, activity analysis, scheduled monitoring, and alerts.',
                  docs_url=None,
                  redoc_url=None)
    app.state.store, app.state.model, app.state.auth = store, model, auth
    app.state.operations, app.state.engine, app.state.worker = operations, engine, worker
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

    def secured(response, path):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
        if secure_cookies:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000'
        if path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.middleware('http')
    async def protect_workspace(request: Request, call_next):
        path, method = request.url.path, request.method
        unsafe = method in {'POST', 'PATCH', 'DELETE', 'PUT'}
        origin = request.headers.get('origin')
        if unsafe and origin:
            allowed = {f'http://{host}:{port}' for host in ('127.0.0.1', 'localhost') for port in (5173, 8000)}
            allowed.add(f'{request.url.scheme}://{request.url.netloc}')
            if origin not in allowed:
                return secured(JSONResponse({'detail': 'Write requests must originate from this workspace.'}, status_code=403), path)
        private = path.startswith('/api/') or path in ('/docs', '/openapi.json')
        if private and (method, path) not in PUBLIC_ROUTES:
            session = await run_in_threadpool(auth.session, request.cookies.get(COOKIE_NAME))
            if session is None:
                return secured(JSONResponse({'detail': 'Sign in to access this workspace.'}, status_code=401), path)
            request.state.session = session
            role = session['user']['role']
            admin_route = path.startswith(('/api/v1/users', '/api/v1/schedules', '/api/v1/model/train')) or path == '/api/v1/audit'
            requires_admin = (admin_route and unsafe) or path in ('/api/v1/users', '/api/v1/audit')
            requires_admin = requires_admin or (unsafe and path.startswith('/api/v1/alerts/') and path.endswith('/retry'))
            if requires_admin and role != 'admin':
                return secured(JSONResponse({'detail': 'Administrator access is required.'}, status_code=403), path)
            own_account = path in ('/api/v1/auth/logout', '/api/v1/auth/password')
            if unsafe and role == 'viewer' and not own_account:
                return secured(JSONResponse({'detail': 'Your viewer role provides read-only access.'}, status_code=403), path)
            if unsafe and not hmac.compare_digest(request.headers.get('x-csrf-token', '').encode(), session['csrf_token'].encode()):
                return secured(JSONResponse({'detail': 'Session verification failed. Refresh the page and try again.'}, status_code=403), path)
        response = await call_next(request)
        return secured(response, path)

    @app.exception_handler(RequestValidationError)
    async def request_validation_error(request, exc):
        return JSONResponse({'detail': 'Invalid request. Check the supplied fields and values.'}, status_code=422)

    @app.exception_handler(AuthError)
    @app.exception_handler(OperationError)
    async def operation_error(request, exc):
        return JSONResponse({'detail': str(exc)}, status_code=exc.status)

    @app.exception_handler(BusyOperation)
    async def busy_error(request, exc):
        return JSONResponse({'detail': 'Another scan, collection, or training operation is running. Try again when it completes.'}, status_code=409)

    @app.exception_handler(CollectionError)
    async def collection_error(request, exc):
        return JSONResponse({'detail': str(exc)}, status_code=502)

    async def bounded_json(request, schema):
        if request.headers.get('content-type', '').split(';')[0].strip() != 'application/json':
            raise HTTPException(415, 'This operation requires application/json.')
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > MAX_IMPORT_BYTES:
                raise HTTPException(413, 'JSON input exceeds the 2 MB limit.')
        try:
            return schema.model_validate_json(bytes(body))
        except ValidationError as exc:
            errors = [{'field': '.'.join(str(v) for v in e['loc']), 'message': e['msg']} for e in exc.errors()]
            return JSONResponse({'detail': 'Input validation failed.', 'errors': errors[:20]}, status_code=422)

    def actor(request):
        return request.state.session['user']['username']

    @app.get('/api/v1/health')
    def health():
        return {'status': 'ok', 'version': '0.3.0', 'phase': 3, 'mode': 'local', 'model_ready': model.status()['ready']}

    if os.environ.get('CLOUDSENTINEL_DOCS', '1') == '1':
        @app.get('/docs', include_in_schema=False, response_class=HTMLResponse)
        def api_reference():
            # A local reference works offline and under the production CSP;
            # the default Swagger UI depends on CDN assets and inline scripts.
            rows = ''.join(f'<tr><td>{escape(method.upper())}</td><td><code>{escape(path)}</code></td><td>{escape(operation.get("summary", ""))}</td></tr>'
                           for path, methods in app.openapi()['paths'].items() for method, operation in methods.items())
            return '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>CloudSentinel API reference</title><style>body{font:16px system-ui;color:#253633;background:#f6f8f7;max-width:1100px;margin:40px auto;padding:0 24px}a{color:#247a64}table{width:100%;background:white;border-collapse:collapse;margin-top:24px}td,th{text-align:left;padding:12px;border-bottom:1px solid #e5eae7}code{overflow-wrap:anywhere}p{line-height:1.6}</style><h1>CloudSentinel API reference</h1><p>Private routes require a signed-in session. Writes also require the session CSRF token in <code>X-CSRF-Token</code>. Viewer, analyst, and administrator permissions are enforced by the server.</p><p><a href="/">Return to workspace</a> · <a href="/openapi.json">OpenAPI JSON schemas and request contracts</a></p><table><thead><tr><th>Method</th><th>Route</th><th>Operation</th></tr></thead><tbody>' + rows + '</tbody></table></html>'

    @app.get('/api/v1/ready')
    def ready():
        with store.connection() as conn:
            conn.execute('SELECT 1')
        state = worker.status()
        configured = not auth.setup_required()
        valid = configured and model.status()['ready'] and (not state['enabled'] or state['running'])
        return JSONResponse({'ready': valid, 'accounts_configured': configured, 'model_ready': model.status()['ready'],
                             'monitor_running': state['running']}, status_code=200 if valid else 503)

    @app.get('/api/v1/auth/status')
    def auth_status():
        return {'setup_required': auth.setup_required(), 'authentication_required': True}

    @app.post('/api/v1/auth/login')
    async def login(request: Request):
        body = await bounded_json(request, LoginRequest)
        if isinstance(body, JSONResponse):
            return body
        token, session = await run_in_threadpool(auth.login, body.username, body.password.get_secret_value(), request.client.host if request.client else 'local')
        response = JSONResponse(session)
        response.set_cookie(COOKIE_NAME, token, httponly=True, secure=secure_cookies, samesite='strict',
                            max_age=SESSION_HOURS * 3600, path='/')
        return response

    @app.get('/api/v1/auth/me')
    def me(request: Request):
        return request.state.session

    @app.post('/api/v1/auth/logout')
    def logout(request: Request):
        auth.logout(request.cookies.get(COOKIE_NAME), actor(request))
        response = JSONResponse({'signed_out': True})
        response.delete_cookie(COOKIE_NAME, path='/', secure=secure_cookies, httponly=True, samesite='strict')
        return response

    @app.post('/api/v1/auth/password')
    def change_password(request: Request, body: PasswordChange):
        auth.change_password(request.state.session['user']['id'], body.current_password.get_secret_value(), body.new_password.get_secret_value(), actor(request))
        response = JSONResponse({'changed': True, 'sign_in_required': True})
        response.delete_cookie(COOKIE_NAME, path='/')
        return response

    @app.get('/api/v1/users')
    def users():
        return auth.list_users()

    @app.post('/api/v1/users', status_code=201)
    def create_user(request: Request, body: UserCreate):
        return auth.create_user(body, actor(request))

    @app.patch('/api/v1/users/{user_id}')
    def update_user(user_id: str, request: Request, body: UserUpdate):
        return auth.update_user(user_id, body, actor(request))

    @app.get('/api/v1/scans')
    def scans():
        return store.list_scans()

    @app.get('/api/v1/scans/latest')
    def latest():
        result = store.get_scan()
        if result is None:
            raise HTTPException(404, 'No scans yet. Run a demo scan to begin.')
        return result

    @app.get('/api/v1/scans/{scan_id}')
    def scan(scan_id: str):
        result = store.get_scan(scan_id)
        if result is None:
            raise HTTPException(404, 'Scan not found.')
        return result

    @app.post('/api/v1/scans/demo', status_code=201)
    def demo_scan(request: Request):
        return engine.demo(actor(request))

    @app.post('/api/v1/scans/import', status_code=201)
    async def import_scan(request: Request):
        inventory = await bounded_json(request, Inventory)
        if isinstance(inventory, JSONResponse):
            return inventory
        return await run_in_threadpool(engine.scan, inventory, 'import', actor(request))

    @app.post('/api/v1/scans/collect', status_code=201)
    def collect_scan(request: Request, body: CollectionRequest):
        try:
            return engine.collect(body, actor(request))
        except (BusyOperation, CollectionError):
            raise
        except Exception:
            raise HTTPException(502, 'Collection failed. Check local credentials and read permissions. The previous scan was preserved.') from None

    @app.get('/api/v1/model')
    def model_status():
        return model.status()

    @app.post('/api/v1/model/train')
    async def train_model(request: Request):
        dataset = await bounded_json(request, TrainingDataset)
        if isinstance(dataset, JSONResponse):
            return dataset
        return await run_in_threadpool(engine.train, dataset, actor(request))

    @app.post('/api/v1/model/train/demo')
    def train_demo_model(request: Request):
        return engine.train(actor=actor(request))

    @app.get('/api/v1/connectors')
    def connectors():
        import shutil
        return [
            {'provider': 'aws', 'credential_source': 'Local boto3 profile or role', 'configured': bool(os.environ.get('AWS_PROFILE') or os.environ.get('AWS_ACCESS_KEY_ID') or (Path.home() / '.aws/config').exists()), 'scope': 'One AWS region plus global IAM users', 'requires': 'Local read-only AWS profile/role and a region. Configuration status does not verify credentials.'},
            {'provider': 'azure', 'credential_source': 'Local Azure CLI or mounted token file', 'configured': bool((shutil.which('az') or os.environ.get('CLOUDSENTINEL_AZURE_TOKEN_FILE')) and os.environ.get('AZURE_SUBSCRIPTION_ID')), 'scope': 'One Azure subscription', 'requires': 'Local CLI or administrator-configured token file; subscription ID via form or AZURE_SUBSCRIPTION_ID. Hints do not verify access.'},
            {'provider': 'gcp', 'credential_source': 'Local gcloud CLI or mounted token file', 'configured': bool((shutil.which('gcloud') or os.environ.get('CLOUDSENTINEL_GCP_TOKEN_FILE')) and os.environ.get('GOOGLE_CLOUD_PROJECT')), 'scope': 'One GCP project', 'requires': 'Local CLI or administrator-configured token file; project ID via form or GOOGLE_CLOUD_PROJECT. Hints do not verify access.'},
        ]

    @app.patch('/api/v1/findings/{finding_id}')
    def update_finding(finding_id: str, request: Request, body: TriageUpdate):
        result = store.triage(finding_id, body.status)
        if result is None:
            raise HTTPException(404, 'Finding not found in the latest scan.')
        with store.connection() as conn:
            audit(conn, actor(request), 'finding.' + body.status, finding_id)
        return result

    @app.get('/api/v1/findings/{finding_id}/events')
    def triage_events(finding_id: str):
        return store.events(finding_id)

    @app.get('/api/v1/rules')
    def rules():
        return [asdict(rule) for rule in RULES]

    @app.get('/api/v1/alerts')
    def alerts(limit: int = Query(default=200, ge=1, le=200), offset: int = Query(default=0, ge=0, le=1000000)):
        return operations.list_alerts(limit, offset)

    @app.post('/api/v1/alerts/{alert_id}/acknowledge')
    def acknowledge(alert_id: str, request: Request):
        operations.acknowledge(alert_id, actor(request))
        return {'acknowledged': True}

    @app.post('/api/v1/alerts/{alert_id}/retry')
    def retry_alert(alert_id: str, request: Request):
        operations.retry_delivery(alert_id, actor(request))
        return {'queued': True}

    @app.get('/api/v1/schedules')
    def schedules():
        return operations.list_schedules()

    @app.post('/api/v1/schedules', status_code=201)
    def create_schedule(request: Request, body: ScheduleCreate):
        return operations.create_schedule(body, actor(request))

    @app.patch('/api/v1/schedules/{schedule_id}')
    def update_schedule(schedule_id: str, request: Request, body: ScheduleUpdate):
        return operations.update_schedule(schedule_id, body, actor(request))

    @app.post('/api/v1/schedules/{schedule_id}/run', status_code=201)
    def run_schedule(schedule_id: str, request: Request):
        claim = operations.claim_schedule(schedule_id)
        return worker.execute(claim, actor(request))

    @app.get('/api/v1/monitor/runs')
    def monitor_runs():
        return operations.list_runs()

    @app.get('/api/v1/operations')
    def operation_status():
        return worker.status() | {'schedules': len(operations.list_schedules()), 'unread_alerts': operations.list_alerts()['unread']}

    @app.get('/api/v1/audit')
    def audit_log():
        return operations.audit_records()

    @app.get('/api/v1/export')
    def export(request: Request):
        result = store.get_scan()
        if result is None:
            raise HTTPException(404, 'No scan to export.')
        with store.connection() as conn:
            audit(conn, actor(request), 'report.exported', result['id'])
        payload = {'product': 'CloudSentinel', 'phase': result['phase'],
                   'detection_method': 'deterministic configuration baseline + Isolation Forest activity analysis' if result['phase'] >= 2 else 'deterministic configuration baseline',
                   'notice': 'Source identifies synthetic, imported, or live data. A synthetic-trained model is experimental on live activity. Team triage does not verify remediation.',
                   'triage_notice': 'Statuses reflect current user dispositions; scan evidence is immutable.', 'scan': result}
        return JSONResponse(payload, headers={'Content-Disposition': f'attachment; filename="cloudsentinel-{result["id"]}.json"'})

    dist = ROOT / 'frontend/dist'
    if dist.exists():
        app.mount('/', StaticFiles(directory=dist, html=True), name='dashboard')
    return app


app = create_app()

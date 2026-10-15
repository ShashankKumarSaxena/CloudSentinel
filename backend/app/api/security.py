"""Browser session, origin, role, CSRF, and safe error boundaries."""

import hmac

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from backend.app.api.headers import apply_headers
from backend.app.api.permissions import PUBLIC_ROUTES, ROLE_RANK, minimum_role
from backend.app.infrastructure.collectors import CollectionError
from backend.app.services.auth import AuthError, COOKIE_NAME
from backend.app.services.monitoring import BusyOperation
from backend.app.services.operations import OperationError


def install_security(app, settings, auth):
    def secured(response, path):
        return apply_headers(response, settings, path)

    @app.middleware("http")
    async def protect_workspace(request: Request, call_next):
        path, method = (request.url.path, request.method)
        unsafe = method in {"POST", "PATCH", "DELETE", "PUT"}
        origin = request.headers.get("origin")
        if unsafe and origin:
            allowed = {settings.public_url.rstrip("/")}
            if not settings.production:
                allowed.update(
                    (
                        f"http://{host}:{port}"
                        for host in ("127.0.0.1", "localhost")
                        for port in (5173, 8000)
                    )
                )
                allowed.add(f"{request.url.scheme}://{request.url.netloc}")
            if origin not in allowed:
                return secured(
                    JSONResponse(
                        {"detail": "Write requests must originate from this workspace."},
                        status_code=403,
                    ),
                    path,
                )
        private = path.startswith("/api/") or path in ("/docs", "/openapi.json")
        if private and (method, path) not in PUBLIC_ROUTES:
            session = await run_in_threadpool(auth.session, request.cookies.get(COOKIE_NAME))
            if session is None:
                return secured(
                    JSONResponse({"detail": "Sign in to access this workspace."}, status_code=401),
                    path,
                )
            request.state.session = session
            role = session["user"]["role"]
            required = minimum_role(method, path)
            if ROLE_RANK.get(role, -1) < ROLE_RANK[required]:
                detail = (
                    "Administrator access is required."
                    if required == "admin"
                    else "Your viewer role provides read-only access."
                )
                return secured(JSONResponse({"detail": detail}, status_code=403), path)
            if unsafe and (
                not hmac.compare_digest(
                    request.headers.get("x-csrf-token", "").encode(), session["csrf_token"].encode()
                )
            ):
                return secured(
                    JSONResponse(
                        {"detail": "Session verification failed. Refresh the page and try again."},
                        status_code=403,
                    ),
                    path,
                )
        response = await call_next(request)
        return secured(response, path)

    @app.exception_handler(RequestValidationError)
    async def request_validation_error(request, exc):
        return JSONResponse(
            {"detail": "Invalid request. Check the supplied fields and values."}, status_code=422
        )

    @app.exception_handler(AuthError)
    @app.exception_handler(OperationError)
    async def operation_error(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=exc.status)

    @app.exception_handler(BusyOperation)
    async def busy_error(request, exc):
        return JSONResponse(
            {
                "detail": "Another scan, collection, or training operation is running. Try again when it completes."
            },
            status_code=409,
        )

    @app.exception_handler(CollectionError)
    async def collection_error(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=502)

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from backend.app.main import create_app
from backend.app.models import UserCreate
from backend.tests.asgi_client import call

PASSWORD = 'test-only-long-password'


class SecurityApiTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = await asyncio.to_thread(create_app, Path(self.temp.name) / 'security.db', monitoring_enabled=False)
        self.lifespan = self.app.router.lifespan_context(self.app)
        await self.lifespan.__aenter__()
        self.admin = await asyncio.to_thread(self.app.state.auth.create_user, UserCreate(username='owner', display_name='Owner', password=PASSWORD, role='admin'), bootstrap=True)

    async def asyncTearDown(self):
        await self.lifespan.__aexit__(None, None, None)
        self.temp.cleanup()

    async def sign_in(self, username='owner', role=None):
        if role:
            await asyncio.to_thread(self.app.state.auth.create_user, UserCreate(username=username, display_name=username, password=PASSWORD, role=role), 'owner')
        status, session, headers = await call(self.app, 'POST', '/api/v1/auth/login', {'username': username, 'password': PASSWORD})
        self.assertEqual(status, 200)
        self.app._test_headers = {'cookie': headers['set-cookie'].split(';')[0], 'x-csrf-token': session['csrf_token']}
        return session, headers

    async def test_anonymous_cannot_read_or_modify_workspace_and_bootstrap_is_local_only(self):
        for method, path, body in [('GET', '/api/v1/scans/latest', None), ('GET', '/api/v1/alerts', None),
                                   ('GET', '/api/v1/users', None), ('GET', '/docs', None), ('POST', '/api/v1/scans/demo', None),
                                   ('POST', '/api/v1/users', {'username': 'attacker'})]:
            with self.subTest(path=path):
                status, _, headers = await call(self.app, method, path, body)
                self.assertEqual(status, 401)
                self.assertEqual(headers['x-content-type-options'], 'nosniff')
                if path.startswith('/api/'):
                    self.assertEqual(headers['cache-control'], 'no-store')
        status, body, _ = await call(self.app, 'GET', '/api/v1/auth/status')
        self.assertEqual(status, 200)
        self.assertFalse(body['setup_required'])

    async def test_cookie_flags_csrf_and_logout(self):
        session, headers = await self.sign_in()
        self.assertIn('HttpOnly', headers['set-cookie'])
        self.assertIn('SameSite=strict', headers['set-cookie'])
        status, _, _ = await call(self.app, 'POST', '/api/v1/scans/demo', headers={'x-csrf-token': ''})
        self.assertEqual(status, 403)
        status, _, _ = await call(self.app, 'POST', '/api/v1/scans/demo', headers={'x-csrf-token': 'incorrect'})
        self.assertEqual(status, 403)
        status, _, _ = await call(self.app, 'POST', '/api/v1/auth/logout')
        self.assertEqual(status, 200)
        status, _, _ = await call(self.app, 'GET', '/api/v1/auth/me')
        self.assertEqual(status, 401)

    async def test_viewer_can_inspect_but_cannot_mutate_or_read_admin_audit(self):
        await self.sign_in('viewer', 'viewer')
        for path in ('/scans/latest', '/alerts', '/schedules', '/model', '/operations'):
            status, _, _ = await call(self.app, 'GET', '/api/v1' + path)
            self.assertEqual(status, 200)
        for method, path, body in [('POST', '/scans/demo', None), ('POST', '/model/train/demo', None),
                                   ('POST', '/schedules', {'name': 'Unauthorized'}), ('GET', '/users', None), ('GET', '/audit', None)]:
            status, _, _ = await call(self.app, method, '/api/v1' + path, body)
            self.assertEqual(status, 403)

    async def test_analyst_can_scan_and_triage_but_cannot_manage_accounts_or_schedules(self):
        await self.sign_in('analyst', 'analyst')
        status, scan, _ = await call(self.app, 'POST', '/api/v1/scans/demo')
        self.assertEqual(status, 201)
        status, _, _ = await call(self.app, 'PATCH', '/api/v1/findings/' + scan['findings'][0]['id'], {'status': 'acknowledged'})
        self.assertEqual(status, 200)
        for path, body in [('/schedules', {'name': 'Unauthorized'}), ('/model/train/demo', None), ('/users', {'username': 'unauthorized'})]:
            status, _, _ = await call(self.app, 'POST', '/api/v1' + path, body)
            self.assertEqual(status, 403)

    async def test_schedule_run_alert_review_and_audit_flow(self):
        await self.sign_in()
        status, schedule, _ = await call(self.app, 'POST', '/api/v1/schedules', {'name': 'Synthetic monitor', 'interval_seconds': 60, 'enabled': False})
        self.assertEqual(status, 201)
        status, scan, _ = await call(self.app, 'POST', '/api/v1/schedules/' + schedule['id'] + '/run')
        self.assertEqual(status, 201)
        self.assertEqual(scan['phase'], 3)
        _, runs, _ = await call(self.app, 'GET', '/api/v1/monitor/runs')
        self.assertEqual(runs[0]['status'], 'succeeded')
        _, inbox, _ = await call(self.app, 'GET', '/api/v1/alerts')
        self.assertEqual(inbox['total'], 19)
        status, _, _ = await call(self.app, 'POST', '/api/v1/alerts/' + inbox['items'][0]['id'] + '/acknowledge')
        self.assertEqual(status, 200)
        _, records, _ = await call(self.app, 'GET', '/api/v1/audit')
        self.assertTrue(any(row['action'] == 'alert.acknowledged' for row in records))
        self.assertTrue(any(row['action'] == 'schedule.succeeded' for row in records))
        self.assertNotIn(PASSWORD, str(records))

    async def test_invalid_or_unscoped_live_schedule_rejected_without_cloud_calls(self):
        await self.sign_in()
        for body in ({'name': 'Bad interval', 'interval_seconds': 1}, {'name': 'Unscoped cloud', 'kind': 'live'},
                     {'name': 'Synthetic with cloud settings', 'collection': {'provider': 'aws'}}):
            status, _, _ = await call(self.app, 'POST', '/api/v1/schedules', body)
            self.assertEqual(status, 422)

    async def test_role_change_revokes_account_session_and_last_admin_is_protected(self):
        await self.sign_in()
        status, viewer, _ = await call(self.app, 'POST', '/api/v1/users', {'username': 'viewer', 'display_name': 'Viewer', 'password': PASSWORD, 'role': 'viewer'})
        self.assertEqual(status, 201)
        status, session, headers = await call(self.app, 'POST', '/api/v1/auth/login', {'username': 'viewer', 'password': PASSWORD})
        viewer_cookie = headers['set-cookie'].split(';')[0]
        status, _, _ = await call(self.app, 'PATCH', '/api/v1/users/' + viewer['id'], {'enabled': False})
        self.assertEqual(status, 200)
        status, _, _ = await call(self.app, 'GET', '/api/v1/auth/me', headers={'cookie': viewer_cookie})
        self.assertEqual(status, 401)
        status, _, _ = await call(self.app, 'PATCH', '/api/v1/users/' + self.admin['id'], {'role': 'viewer'})
        self.assertEqual(status, 409)

    async def test_private_responses_have_security_headers_and_password_change_revokes_session(self):
        await self.sign_in()
        status, _, headers = await call(self.app, 'GET', '/api/v1/scans/latest')
        self.assertEqual(headers['cache-control'], 'no-store')
        self.assertIn("frame-ancestors 'none'", headers['content-security-policy'])
        status, _, _ = await call(self.app, 'POST', '/api/v1/auth/password', {'current_password': PASSWORD, 'new_password': 'new-test-only-password'})
        self.assertEqual(status, 200)
        status, _, _ = await call(self.app, 'GET', '/api/v1/scans/latest')
        self.assertEqual(status, 401)

    async def test_alert_pagination_is_validated(self):
        await self.sign_in()
        status, first, _ = await call(self.app, 'GET', '/api/v1/alerts?limit=10')
        self.assertEqual(status, 200)
        self.assertEqual(len(first['items']), 10)
        status, second, _ = await call(self.app, 'GET', '/api/v1/alerts?limit=10&offset=10')
        self.assertEqual(len(second['items']), 9)
        self.assertEqual(status, 200)
        for query in ('offset=-1', 'limit=500'):
            status, _, _ = await call(self.app, 'GET', '/api/v1/alerts?' + query)
            self.assertEqual(status, 422)

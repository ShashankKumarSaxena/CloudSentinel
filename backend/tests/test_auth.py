from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest

from backend.app.auth import AuthService, AuthError, password_hash, verify_password, token_hash
from backend.app.models import UserCreate, UserUpdate
from backend.app.store import Store

PASSWORD = 'test-only-long-password'


class AuthTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'auth.db')
        self.auth = AuthService(self.store)
        self.admin = self.auth.create_user(UserCreate(username='owner', display_name='Owner', password=PASSWORD, role='admin'), bootstrap=True)

    def tearDown(self):
        self.temp.cleanup()

    def test_passwords_use_salted_hashes_and_are_not_exposed(self):
        first, second = password_hash(PASSWORD), password_hash(PASSWORD)
        self.assertNotEqual(first, second)
        self.assertTrue(verify_password(PASSWORD, first))
        self.assertFalse(verify_password('incorrect', first))
        self.assertNotIn(PASSWORD, first)
        self.assertNotIn('password_hash', self.auth.list_users()[0])

    def test_no_second_bootstrap_and_username_case_is_unique(self):
        with self.assertRaises(AuthError):
            self.auth.create_user(UserCreate(username='other', display_name='Other', password=PASSWORD, role='admin'), bootstrap=True)
        with self.assertRaises(AuthError):
            self.auth.create_user(UserCreate(username='OWNER', display_name='Duplicate', password=PASSWORD))

    def test_sessions_store_only_opaque_token_hashes_and_expire(self):
        token, session = self.auth.login('owner', PASSWORD)
        self.assertEqual(self.auth.session(token)['user']['id'], self.admin['id'])
        with self.store.connection() as conn:
            stored = dict(conn.execute('SELECT * FROM sessions').fetchone())
            self.assertNotIn(token, json.dumps(stored))
            self.assertEqual(stored['token_hash'], token_hash(token))
            conn.execute('UPDATE sessions SET expires_at=?', ((datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),))
        self.assertIsNone(self.auth.session(token))

    def test_idle_sessions_expire_and_logout_revokes_access(self):
        token, _ = self.auth.login('owner', PASSWORD)
        with self.store.connection() as conn:
            conn.execute('UPDATE sessions SET last_seen=?', ((datetime.now(timezone.utc) - timedelta(minutes=31)).isoformat(),))
        self.assertIsNone(self.auth.session(token))
        token, _ = self.auth.login('owner', PASSWORD)
        self.auth.logout(token, 'owner')
        self.assertIsNone(self.auth.session(token))

    def test_failed_login_is_rate_limited_without_disclosing_account(self):
        for _ in range(5):
            with self.assertRaises(AuthError) as error:
                self.auth.login('owner', 'incorrect')
            self.assertEqual(error.exception.status, 401)
        with self.assertRaises(AuthError) as error:
            self.auth.login('owner', PASSWORD)
        self.assertEqual(error.exception.status, 429)
        with self.assertRaises(AuthError) as error:
            self.auth.login('unknown-account', 'incorrect')
        self.assertEqual(str(error.exception), 'Invalid username or password.')

    def test_role_changes_revoke_sessions_and_preserve_last_administrator(self):
        with self.assertRaises(AuthError):
            self.auth.update_user(self.admin['id'], UserUpdate(enabled=False), 'owner')
        with self.assertRaises(AuthError):
            self.auth.update_user(self.admin['id'], UserUpdate(role='viewer'), 'owner')
        user = self.auth.create_user(UserCreate(username='analyst', display_name='Analyst', password=PASSWORD, role='analyst'), 'owner')
        token, _ = self.auth.login('analyst', PASSWORD)
        self.auth.update_user(user['id'], UserUpdate(role='viewer'), 'owner')
        self.assertIsNone(self.auth.session(token))

    def test_password_change_verifies_old_password_and_revokes_sessions(self):
        token, _ = self.auth.login('owner', PASSWORD)
        with self.assertRaises(AuthError):
            self.auth.change_password(self.admin['id'], 'incorrect', 'new-test-only-password', 'owner')
        self.assertIsNotNone(self.auth.session(token))
        self.auth.change_password(self.admin['id'], PASSWORD, 'new-test-only-password', 'owner')
        self.assertIsNone(self.auth.session(token))
        _, session = self.auth.login('owner', 'new-test-only-password')
        self.assertEqual(session['user']['username'], 'owner')

    def test_active_sessions_are_bounded(self):
        tokens = [self.auth.login('owner', PASSWORD)[0] for _ in range(6)]
        self.assertIsNone(self.auth.session(tokens[0]))
        with self.store.connection() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM sessions').fetchone()[0], 5)

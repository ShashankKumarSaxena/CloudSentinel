"""Local user accounts, expiring opaque sessions, and server-side authorization."""

import base64
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import hashlib
import hmac
import secrets
import threading

from backend.app.domain.schemas import UserCreate
from backend.app.repositories.store import now

COOKIE_NAME = "cloudsentinel_session"
SESSION_HOURS = 8
IDLE_MINUTES = 30
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**15, 8, 3


def password_hash(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, maxmem=64 * 1024 * 1024
    )
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def verify_password(password, encoded):
    try:
        _, salt, _ = encoded.split("$")
        return hmac.compare_digest(password_hash(password, base64.b64decode(salt)), encoded)
    except (ValueError, TypeError):
        return False


def token_hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


def public_user(row):
    return {key: row[key] for key in ("id", "username", "display_name", "role", "created_at")} | {
        "enabled": bool(row["enabled"]),
        "sso_only": bool(row["sso_only"]),
    }


def audit(conn, actor, action, target="", detail=None):
    import json

    conn.execute(
        "INSERT INTO audit_log (created_at, actor, action, target, detail) VALUES (?, ?, ?, ?, ?)",
        (now(), actor, action, target, json.dumps(detail or {})),
    )


class AuthError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


class AuthService:
    def __init__(
        self,
        store,
        session_ttl_seconds=SESSION_HOURS * 3600,
        idle_timeout_seconds=IDLE_MINUTES * 60,
    ):
        self.store = store
        self.session_ttl_seconds = session_ttl_seconds
        self.idle_timeout_seconds = idle_timeout_seconds
        self.login_lock = threading.Lock()
        self.dummy_hash = password_hash("not-a-real-account-password")

    def setup_required(self):
        with self.store.connection() as conn:
            return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0

    def create_user(self, body: UserCreate, actor="local-cli", bootstrap=False, issuer=None):
        with self.login_lock:
            return self._create_user(body, actor, bootstrap, issuer)

    def _create_user(self, body: UserCreate, actor="local-cli", bootstrap=False, issuer=None):
        if body.oidc_subject and (not issuer or bootstrap):
            raise AuthError(
                "Corporate access must be configured after local administrator setup.", 409
            )
        encoded = password_hash(
            body.password.get_secret_value() if body.password else secrets.token_urlsafe(48)
        )
        user_id = str(uuid4())
        with self.store.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            if bootstrap and count:
                raise AuthError(
                    "An administrator already exists. Use authenticated account management.", 409
                )
            if bootstrap and body.role != "admin":
                raise AuthError("The first account must be an administrator.")
            if conn.execute(
                "SELECT 1 FROM users WHERE username = ?", (body.username.lower(),)
            ).fetchone():
                raise AuthError("That username is already in use.", 409)
            conn.execute(
                "INSERT INTO users (id,username,display_name,password_hash,role,enabled,created_at,sso_only) VALUES (?, ?, ?, ?, ?, 1, ?, ?)",
                (
                    user_id,
                    body.username.lower(),
                    body.display_name,
                    encoded,
                    body.role,
                    now(),
                    int(body.oidc_subject is not None),
                ),
            )
            if body.oidc_subject:
                if conn.execute(
                    "SELECT 1 FROM external_identities WHERE issuer=? AND subject=?",
                    (issuer, body.oidc_subject),
                ).fetchone():
                    raise AuthError("That corporate identity is already assigned.", 409)
                conn.execute(
                    "INSERT INTO external_identities VALUES (?,?,?)",
                    (issuer, body.oidc_subject, user_id),
                )
            audit(conn, actor, "user.created", user_id, {"role": body.role})
            return public_user(
                conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            )

    def list_users(self):
        with self.store.connection() as conn:
            return [
                public_user(row) for row in conn.execute("SELECT * FROM users ORDER BY created_at")
            ]

    def login(self, username, password, client="local"):
        # Bound memory-heavy password checks and serialize failed-attempt updates.
        with self.login_lock:
            return self._login(username, password, client)

    def _login(self, username, password, client="local"):
        username = username.lower()
        key = token_hash(client + ":" + username)
        current = datetime.now(timezone.utc)
        cutoff = (current - timedelta(minutes=15)).isoformat()
        with self.store.connection() as conn:
            attempt = conn.execute("SELECT * FROM login_attempts WHERE key = ?", (key,)).fetchone()
            if attempt and attempt["window_start"] > cutoff and attempt["failures"] >= 5:
                raise AuthError("Too many failed attempts. Try again after 15 minutes.", 429)
            row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        valid = verify_password(password, row["password_hash"] if row else self.dummy_hash)
        if not valid or not row or not row["enabled"] or row["sso_only"]:
            with self.store.connection() as conn:
                if attempt and attempt["window_start"] > cutoff:
                    conn.execute(
                        "UPDATE login_attempts SET failures = failures + 1 WHERE key = ?", (key,)
                    )
                else:
                    conn.execute(
                        "INSERT INTO login_attempts VALUES (?, 1, ?) ON CONFLICT(key) DO UPDATE SET failures=1, window_start=excluded.window_start",
                        (key, current.isoformat()),
                    )
                audit(conn, "anonymous", "login.failed", detail={"client_key": key[:16]})
            raise AuthError("Invalid username or password.", 401)
        return self._issue_session(row, key)

    def _issue_session(self, row, key=""):
        current = datetime.now(timezone.utc)
        cutoff = (current - timedelta(minutes=15)).isoformat()
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        expires = (current + timedelta(seconds=self.session_ttl_seconds)).isoformat()
        with self.store.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            fresh = conn.execute("SELECT * FROM users WHERE id=?", (row["id"],)).fetchone()
            if (
                fresh is None
                or not fresh["enabled"]
                or fresh["password_hash"] != row["password_hash"]
                or fresh["sso_only"] != row["sso_only"]
            ):
                raise AuthError("Account access changed. Sign in again.", 401)
            row = fresh
            conn.execute(
                "DELETE FROM login_attempts WHERE key = ? OR window_start < ?", (key, cutoff)
            )
            conn.execute("DELETE FROM sessions WHERE expires_at < ?", (current.isoformat(),))
            # Bound active sessions per account.
            old = conn.execute(
                "SELECT token_hash FROM sessions WHERE user_id = ? ORDER BY last_seen DESC LIMIT 100000 OFFSET 4",
                (row["id"],),
            ).fetchall()
            conn.executemany("DELETE FROM sessions WHERE token_hash = ?", [(r[0],) for r in old])
            conn.execute(
                "INSERT INTO sessions VALUES (?, ?, ?, ?, ?)",
                (token_hash(token), row["id"], csrf, expires, current.isoformat()),
            )
            audit(conn, row["username"], "login.succeeded", row["id"])
        return token, {"user": public_user(row), "csrf_token": csrf, "expires_at": expires}

    def session(self, token):
        if not token or len(token) > 200:
            return None
        current = datetime.now(timezone.utc)
        with self.store.connection() as conn:
            row = conn.execute(
                "SELECT s.*, u.username, u.display_name, u.role, u.enabled, u.created_at, u.id, u.sso_only "
                "FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash = ?",
                (token_hash(token),),
            ).fetchone()
            if row is None:
                return None
            if (
                not row["enabled"]
                or row["expires_at"] <= current.isoformat()
                or datetime.fromisoformat(row["last_seen"])
                + timedelta(seconds=self.idle_timeout_seconds)
                <= current
            ):
                conn.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash(token),))
                return None
            conn.execute(
                "UPDATE sessions SET last_seen = ? WHERE token_hash = ?",
                (current.isoformat(), token_hash(token)),
            )
            return {
                "user": public_user(row),
                "csrf_token": row["csrf"],
                "expires_at": row["expires_at"],
            }

    def logout(self, token, actor):
        with self.store.connection() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash(token or ""),))
            audit(conn, actor, "logout")

    def update_user(self, user_id, body, actor):
        with self.store.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            if not row:
                raise AuthError("Account not found.", 404)
            role = body.role if body.role is not None else row["role"]
            enabled = body.enabled if body.enabled is not None else bool(row["enabled"])
            if row["role"] == "admin" and row["enabled"] and (role != "admin" or not enabled):
                if (
                    conn.execute(
                        "SELECT COUNT(*) FROM users WHERE role='admin' AND enabled=1"
                    ).fetchone()[0]
                    <= 1
                ):
                    raise AuthError(
                        "The last enabled administrator cannot be disabled or demoted.", 409
                    )
            if (
                row["role"] == "admin"
                and row["enabled"]
                and not row["sso_only"]
                and (role != "admin" or not enabled)
            ):
                if (
                    conn.execute(
                        "SELECT COUNT(*) FROM users WHERE role='admin' AND enabled=1 AND sso_only=0"
                    ).fetchone()[0]
                    <= 1
                ):
                    raise AuthError("Keep one enabled local administrator for recovery.", 409)
            conn.execute(
                "UPDATE users SET role=?, enabled=? WHERE id=?", (role, int(enabled), user_id)
            )
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            audit(conn, actor, "user.updated", user_id, {"role": role, "enabled": enabled})
            return public_user(
                conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            )

    def change_password(self, user_id, current_password, new_password, actor, require_current=True):
        # Scrypt is intentionally expensive; serialize all password operations
        # rather than allowing simultaneous requests to exhaust process memory.
        with self.login_lock:
            return self._change_password(
                user_id, current_password, new_password, actor, require_current
            )

    def _change_password(self, user_id, current_password, new_password, actor, require_current):
        with self.store.connection() as conn:
            row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if row is None:
            raise AuthError("Account not found.", 404)
        if row["sso_only"] and require_current:
            raise AuthError(
                "Password changes are managed by your corporate identity provider.", 403
            )
        if require_current and not verify_password(current_password, row["password_hash"]):
            raise AuthError("Current password is incorrect.", 400)
        if not 12 <= len(new_password) <= 256:
            raise AuthError("Password must contain 12–256 characters.")
        encoded = password_hash(new_password)
        with self.store.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            fresh = conn.execute(
                "SELECT password_hash FROM users WHERE id=?", (user_id,)
            ).fetchone()
            if fresh is None or fresh[0] != row["password_hash"]:
                raise AuthError(
                    "Account credentials changed. Retry with the current password.", 409
                )
            conn.execute("UPDATE users SET password_hash=? WHERE id=?", (encoded, user_id))
            conn.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
            audit(conn, actor, "password.changed", user_id)

    def link_identity(self, user_id, issuer, subject, actor):
        """Bind a pre-approved subject, never an email address or an IdP role."""
        with self.store.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
            if not row:
                raise AuthError("Account not found.", 404)
            if row["role"] == "admin" and row["enabled"] and not row["sso_only"]:
                local_admins = conn.execute(
                    "SELECT COUNT(*) FROM users WHERE role='admin' AND enabled=1 AND sso_only=0"
                ).fetchone()[0]
                if local_admins <= 1:
                    raise AuthError("Keep an enabled local administrator for recovery.", 409)
            existing = conn.execute(
                "SELECT user_id FROM external_identities WHERE issuer=? AND subject=?",
                (issuer, subject),
            ).fetchone()
            if existing and existing["user_id"] != user_id:
                raise AuthError("That external subject is already assigned.", 409)
            conn.execute(
                "INSERT INTO external_identities VALUES (?,?,?) ON CONFLICT(issuer,subject) DO NOTHING",
                (issuer, subject, user_id),
            )
            conn.execute("UPDATE users SET sso_only=1 WHERE id=?", (user_id,))
            conn.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
            audit(conn, actor, "user.identity.linked", user_id, {"issuer": issuer})

    def login_external(self, issuer, subject):
        with self.store.connection() as conn:
            row = conn.execute(
                "SELECT u.* FROM users u JOIN external_identities e ON e.user_id=u.id WHERE e.issuer=? AND e.subject=?",
                (issuer, subject),
            ).fetchone()
        if not row or not row["enabled"] or not row["sso_only"]:
            raise AuthError("This corporate identity is not approved for workspace access.", 403)
        return self._issue_session(row)

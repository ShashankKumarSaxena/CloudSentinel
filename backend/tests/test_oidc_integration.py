"""Real Authlib/HTTPX protocol tests against an in-memory RSA-signing issuer.

These require production dependencies and never contact a live identity provider.
"""

import asyncio
import base64
from importlib.util import find_spec
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse
import json
import tempfile
import time
import unittest

from pydantic import SecretStr

from backend.app.api.oidc import install_oidc
from backend.app.application import create_app
from backend.app.core.config import Settings
from backend.app.domain.schemas import UserCreate
from backend.app.repositories.store import Store

AVAILABLE = all(find_spec(package) for package in ("authlib", "httpx", "cryptography"))


def encoded(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


@unittest.skipUnless(
    AVAILABLE, "Install production requirements to verify the OIDC protocol integration."
)
class OidcIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import httpx
        from cryptography.hazmat.primitives.asymmetric import rsa

        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.issuer = "https://identity.example.test/company"
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.nonce = ""
        self.challenge = ""
        self.audience = "cloudsentinel"
        self.code_used = False
        (root / "client_secret").write_text("test-only-client-secret")
        (root / "state_secret").write_text("test-only-state-secret-" + "x" * 32)
        (root / "accounts.json").write_text('{"schema_version":"1","accounts":[]}')
        settings = Settings(
            mode="production",
            public_url="https://testserver",
            allowed_hosts=("testserver",),
            embedded_worker=False,
            secure_cookies=True,
            model_dir=root / "models",
            accounts_file=root / "accounts.json",
            database_path=root / "workspace.db",
            database_url=SecretStr("postgresql://unused/unused"),
            oidc_issuer=self.issuer,
            oidc_client_id="cloudsentinel",
            oidc_client_secret_file=root / "client_secret",
            oidc_state_secret_file=root / "state_secret",
        )
        transport = httpx.MockTransport(self.identity_provider)
        with (
            patch("backend.app.application.Store", side_effect=lambda path, url: Store(path)),
            patch(
                "backend.app.application.install_oidc",
                side_effect=lambda app, config, auth: install_oidc(
                    app, config, auth, transport=transport
                ),
            ),
            patch("backend.app.api.observability.logger"),
        ):
            self.app = await asyncio.to_thread(create_app, settings=settings)
        self.lifespan = self.app.router.lifespan_context(self.app)
        await self.lifespan.__aenter__()
        await asyncio.to_thread(
            self.app.state.auth.create_user,
            UserCreate(
                username="owner",
                display_name="Owner",
                password="test-only-long-password",
                role="admin",
            ),
            bootstrap=True,
        )
        await asyncio.to_thread(
            self.app.state.auth.create_user,
            UserCreate(
                username="analyst",
                display_name="Corporate analyst",
                oidc_subject="approved-subject",
                role="analyst",
            ),
            "owner",
            issuer=self.issuer,
        )
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="https://testserver",
            follow_redirects=False,
        )

    async def asyncTearDown(self):
        await self.client.aclose()
        await self.lifespan.__aexit__(None, None, None)
        self.temp.cleanup()

    def identity_provider(self, request):
        import httpx
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.primitives import hashes
        import hashlib

        if request.url.path.endswith("/.well-known/openid-configuration"):
            return httpx.Response(
                200,
                json={
                    "issuer": self.issuer,
                    "authorization_endpoint": self.issuer + "/authorize",
                    "token_endpoint": self.issuer + "/token",
                    "jwks_uri": self.issuer + "/jwks",
                    "id_token_signing_alg_values_supported": ["RS256"],
                    "token_endpoint_auth_methods_supported": ["client_secret_basic"],
                },
            )
        if request.url.path.endswith("/jwks"):
            public = self.key.public_key().public_numbers()
            key = {
                "kty": "RSA",
                "kid": "test-key",
                "use": "sig",
                "alg": "RS256",
                "n": encoded(public.n.to_bytes((public.n.bit_length() + 7) // 8, "big")),
                "e": encoded(public.e.to_bytes((public.e.bit_length() + 7) // 8, "big")),
            }
            return httpx.Response(200, json={"keys": [key]})
        if request.url.path.endswith("/token"):
            body = parse_qs(request.content.decode())
            verifier = body.get("code_verifier", [""])[0]
            if (
                self.code_used
                or encoded(hashlib.sha256(verifier.encode()).digest()) != self.challenge
            ):
                return httpx.Response(400, json={"error": "invalid_grant"})
            self.code_used = True
            now = int(time.time())
            claims = {
                "iss": self.issuer,
                "sub": "approved-subject",
                "aud": self.audience,
                "iat": now,
                "exp": now + 120,
                "nonce": self.nonce,
                "role": "admin",
            }
            token = (
                encoded(json.dumps({"alg": "RS256", "kid": "test-key"}).encode())
                + "."
                + encoded(json.dumps(claims).encode())
            )
            signature = self.key.sign(token.encode(), padding.PKCS1v15(), hashes.SHA256())
            return httpx.Response(
                200,
                json={
                    "access_token": "test-only-access-token",
                    "token_type": "Bearer",
                    "id_token": token + "." + encoded(signature),
                },
            )
        raise AssertionError("An unexpected identity-provider destination was requested.")

    async def authorization(self):
        response = await self.client.get("/api/v1/auth/oidc/start")
        self.assertEqual(response.status_code, 302)
        parameters = parse_qs(urlparse(response.headers["location"]).query)
        self.assertEqual(parameters["code_challenge_method"], ["S256"])
        self.nonce = parameters["nonce"][0]
        self.challenge = parameters["code_challenge"][0]
        return {"code": "test-authorization-code", "state": parameters["state"][0]}

    async def test_verified_token_pkce_and_preapproved_subject_create_only_local_role_session(self):
        parameters = await self.authorization()
        response = await self.client.get("/api/v1/auth/oidc/callback", params=parameters)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/")
        identity = await self.client.get("/api/v1/auth/me")
        self.assertEqual(identity.status_code, 200)
        self.assertEqual(identity.json()["user"]["role"], "analyst")
        self.assertTrue(identity.json()["user"]["sso_only"])
        self.assertNotIn("test-only-access-token", identity.text)
        replay = await self.client.get("/api/v1/auth/oidc/callback", params=parameters)
        self.assertIn("login_error=corporate", replay.headers["location"])

    async def test_wrong_token_audience_is_rejected_without_a_workspace_session(self):
        parameters = await self.authorization()
        self.audience = "another-application"
        response = await self.client.get("/api/v1/auth/oidc/callback", params=parameters)
        self.assertIn("login_error=corporate", response.headers["location"])
        self.assertEqual((await self.client.get("/api/v1/auth/me")).status_code, 401)

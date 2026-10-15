"""Optional corporate sign-in with Authlib's verified OIDC/PKCE integration."""

from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse
from starlette.concurrency import run_in_threadpool

from backend.app.services.auth import COOKIE_NAME, audit


def install_oidc(app, settings, auth, transport=None):
    if not settings.oidc_issuer:
        return
    try:
        from authlib.integrations.starlette_client import OAuth
        from starlette.middleware.sessions import SessionMiddleware
    except ImportError:
        raise RuntimeError(
            "Install production requirements before enabling corporate sign-in."
        ) from None

    state_secret = settings.oidc_state_secret_file.read_text().strip()
    client_secret = settings.oidc_client_secret_file.read_text().strip()
    if len(state_secret) < 32 or not client_secret:
        raise ValueError(
            "OIDC needs a private random state secret of at least 32 characters and a client secret."
        )
    app.add_middleware(
        SessionMiddleware,
        secret_key=state_secret,
        session_cookie="cloudsentinel_oidc",
        https_only=settings.secure_cookies,
        same_site="lax",
        max_age=600,
    )
    oauth = OAuth()
    client_options = {
        "scope": "openid profile email",
        "code_challenge_method": "S256",
        "timeout": 10.0,
    }
    if transport is not None:
        client_options["transport"] = transport
    oauth.register(
        "corporate",
        client_id=settings.oidc_client_id,
        client_secret=client_secret,
        server_metadata_url=settings.oidc_issuer.rstrip("/") + "/.well-known/openid-configuration",
        client_kwargs=client_options,
        authorize_params={"response_type": "code"},
    )
    client = oauth.create_client("corporate")
    callback = settings.public_url.rstrip("/") + "/api/v1/auth/oidc/callback"

    @app.get("/api/v1/auth/oidc/start", include_in_schema=False)
    async def start(request: Request):
        if await run_in_threadpool(auth.setup_required):
            raise HTTPException(
                409, "Create the first local administrator before configuring corporate access."
            )
        try:
            return await client.authorize_redirect(request, callback)
        except Exception:
            raise HTTPException(
                503, "Corporate sign-in is unavailable. Contact your workspace administrator."
            ) from None

    @app.get("/api/v1/auth/oidc/callback", include_in_schema=False)
    async def complete(request: Request):
        try:
            # Authlib checks the signed ID token, issuer, audience, expiry, nonce,
            # authorization state and PKCE verifier. Tokens never reach the UI.
            token = await client.authorize_access_token(request)
            identity = token.get("userinfo")
            if (
                not identity
                or identity.get("iss") != settings.oidc_issuer
                or not identity.get("sub")
            ):
                raise ValueError("OIDC identity did not match the configured issuer.")
            session_token, _ = await run_in_threadpool(
                auth.login_external, settings.oidc_issuer, identity["sub"]
            )
        except Exception:
            request.session.clear()
            with auth.store.connection() as connection:
                audit(connection, "anonymous", "oidc.failed")
            return RedirectResponse("/?login_error=corporate", status_code=303)
        request.session.clear()
        response = RedirectResponse("/", status_code=303)
        response.set_cookie(
            COOKIE_NAME,
            session_token,
            httponly=True,
            secure=settings.secure_cookies,
            samesite="strict",
            max_age=auth.session_ttl_seconds,
            path="/",
        )
        return response

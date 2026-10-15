"""Authentication HTTP routes; business logic stays in services."""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from backend.app.api.body import bounded_json
from backend.app.api.contracts import SessionView, UserView
from backend.app.api.dependencies import actor, get_services
from backend.app.domain.schemas import (
    IdentityLink,
    LoginRequest,
    PasswordChange,
    UserCreate,
    UserUpdate,
)
from backend.app.services.auth import COOKIE_NAME

router = APIRouter()


@router.get("/api/v1/auth/status")
def auth_status(request: Request):
    services = get_services(request)
    return {
        "setup_required": services.auth.setup_required(),
        "authentication_required": True,
        "mode": services.settings.mode,
        "oidc_enabled": bool(services.settings.oidc_issuer),
    }


@router.post("/api/v1/auth/login")
async def login(request: Request):
    services = get_services(request)
    body = await bounded_json(request, LoginRequest)
    if isinstance(body, JSONResponse):
        return body
    token, session = await run_in_threadpool(
        services.auth.login,
        body.username,
        body.password.get_secret_value(),
        request.client.host if request.client else "local",
    )
    response = JSONResponse(session)
    response.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        secure=services.settings.secure_cookies,
        samesite="strict",
        max_age=services.auth.session_ttl_seconds,
        path="/",
    )
    return response


@router.get("/api/v1/auth/me", response_model=SessionView)
def me(request: Request):
    services = get_services(request)
    return request.state.session


@router.post("/api/v1/auth/logout")
def logout(request: Request):
    services = get_services(request)
    services.auth.logout(request.cookies.get(COOKIE_NAME), actor(request))
    response = JSONResponse({"signed_out": True})
    response.delete_cookie(
        COOKIE_NAME,
        path="/",
        secure=services.settings.secure_cookies,
        httponly=True,
        samesite="strict",
    )
    return response


@router.post("/api/v1/auth/password")
def change_password(request: Request, body: PasswordChange):
    services = get_services(request)
    services.auth.change_password(
        request.state.session["user"]["id"],
        body.current_password.get_secret_value(),
        body.new_password.get_secret_value(),
        actor(request),
    )
    response = JSONResponse({"changed": True, "sign_in_required": True})
    response.delete_cookie(COOKIE_NAME, path="/")
    return response


@router.get("/api/v1/users", response_model=list[UserView])
def users(request: Request):
    services = get_services(request)
    return services.auth.list_users()


@router.post("/api/v1/users", status_code=201, response_model=UserView)
def create_user(request: Request, body: UserCreate):
    services = get_services(request)
    return services.auth.create_user(body, actor(request), issuer=services.settings.oidc_issuer)


@router.patch("/api/v1/users/{user_id}", response_model=UserView)
def update_user(user_id: str, request: Request, body: UserUpdate):
    services = get_services(request)
    return services.auth.update_user(user_id, body, actor(request))


@router.post("/api/v1/users/{user_id}/identity")
def link_identity(user_id: str, body: IdentityLink, request: Request):
    services = get_services(request)
    if not services.settings.oidc_issuer:
        raise HTTPException(409, "Corporate sign-in is not configured.")
    services.auth.link_identity(
        user_id, services.settings.oidc_issuer, body.subject, actor(request)
    )
    return {"linked": True}

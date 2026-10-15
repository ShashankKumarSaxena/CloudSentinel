"""Public response contracts intentionally exclude internal credentials and hashes."""

from typing import Literal

from pydantic import BaseModel

from backend.app.domain.schemas import CollectionRequest, Provider, Role


class UserView(BaseModel):
    id: str
    username: str
    display_name: str
    role: Role
    enabled: bool
    sso_only: bool
    created_at: str


class SessionView(BaseModel):
    user: UserView
    csrf_token: str
    expires_at: str


class CloudAccountView(BaseModel):
    id: str
    name: str
    provider: Provider
    account: str
    regions: list[str]
    enabled: bool
    auth: str


class CollectionJobView(BaseModel):
    id: str
    created_at: str
    created_by: str
    status: Literal["pending", "running", "succeeded", "failed", "cancelled"]
    started_at: str | None
    finished_at: str | None
    scan_id: str | None
    error: str | None
    attempts: int
    request: CollectionRequest


class JobPageView(BaseModel):
    items: list[CollectionJobView]
    total: int


class SnapshotView(BaseModel):
    connection_id: str
    region: str
    scan_id: str
    updated_at: str

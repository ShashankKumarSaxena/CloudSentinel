"""Explicit request dependencies shared by small, feature-focused routers."""

from dataclasses import dataclass

from fastapi import Request

from backend.app.core.config import Settings
from backend.app.infrastructure.connections import Connections
from backend.app.repositories.store import Store
from backend.app.services.auth import AuthService
from backend.app.services.engine import ScanEngine
from backend.app.services.jobs import CollectionJobs
from backend.app.services.model import ModelService
from backend.app.services.monitoring import MonitorWorker
from backend.app.services.operations import Operations


@dataclass(frozen=True)
class Services:
    settings: Settings
    store: Store
    model: ModelService
    auth: AuthService
    operations: Operations
    engine: ScanEngine
    worker: MonitorWorker
    connections: Connections
    jobs: CollectionJobs


def get_services(request: Request) -> Services:
    return request.app.state.services


def actor(request: Request) -> str:
    return request.state.session["user"]["username"]

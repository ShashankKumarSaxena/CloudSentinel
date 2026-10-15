"""Stable ASGI entry point. Application composition lives in application.py."""

from backend.app.application import create_app

app = create_app()

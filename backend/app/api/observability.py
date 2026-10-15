"""Structured request metadata without query strings, bodies, or credentials."""

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import json
import logging
import re
import time
import traceback

from fastapi import Request
from fastapi.responses import JSONResponse

from backend.app.api.headers import apply_headers

logger = logging.getLogger("cloudsentinel")


def install_observability(app, enabled=False):
    if enabled and not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False

    @app.middleware("http")
    async def observe(request: Request, call_next):
        supplied = request.headers.get("x-request-id", "")
        request_id = supplied if re.fullmatch(r"[a-zA-Z0-9-]{8,64}", supplied) else str(uuid4())
        request.state.request_id = request_id
        started = time.monotonic()
        failure = {}
        try:
            response = await call_next(request)
        except Exception as exc:
            frame = traceback.extract_tb(exc.__traceback__)[-1]
            failure = {
                "error_type": type(exc).__name__,
                "component": Path(frame.filename).name,
                "line": frame.lineno,
            }
            # Provider/SQL exception text may contain credentials or account data.
            # Return an opaque request ID and let operators correlate safe events.
            response = JSONResponse(
                {
                    "detail": "Workspace operation failed. Contact the administrator with the request ID.",
                    "request_id": request_id,
                },
                status_code=500,
            )
        response = apply_headers(response, request.app.state.settings, request.url.path)
        response.headers["X-Request-ID"] = request_id
        if enabled:
            logger.info(
                json.dumps(
                    {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "event": "http.request",
                        "request_id": request_id,
                        "method": request.method,
                        "route": getattr(request.scope.get("route"), "path", "unmatched"),
                        "status": response.status_code,
                        "duration_ms": round((time.monotonic() - started) * 1000, 2),
                        **failure,
                    }
                )
            )
        return response

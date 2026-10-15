"""Bound streamed JSON before validation; never echo secret field inputs."""

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from pydantic import ValidationError

MAX_IMPORT_BYTES = 2 * 1024 * 1024


async def bounded_json(request, schema):
    if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
        raise HTTPException(415, "This operation requires application/json.")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_IMPORT_BYTES:
            raise HTTPException(413, "JSON input exceeds the 2 MB limit.")
    try:
        return schema.model_validate_json(bytes(body))
    except ValidationError as exc:
        errors = [
            {"field": ".".join((str(v) for v in e["loc"])), "message": e["msg"]}
            for e in exc.errors()
        ]
        return JSONResponse(
            {"detail": "Input validation failed.", "errors": errors[:20]}, status_code=422
        )

"""Small dependency-free ASGI test transport; no ports or live cloud calls."""
import asyncio
import json
from urllib.parse import urlsplit


async def call(app, method, path, body=None, raw=None, headers=None):
    parsed = urlsplit(path)
    payload = raw if raw is not None else json.dumps(body).encode() if body is not None else b""
    request_headers = [(b"host", b"testserver"), (b"content-type", b"application/json")]
    if headers:
        request_headers = [(k, v) for k, v in request_headers if k.decode() not in headers]
        request_headers += [(key.encode(), value.encode()) for key, value in headers.items()]
    session_headers = getattr(app, '_test_headers', {})
    request_headers += [(key.encode(), value.encode()) for key, value in session_headers.items() if key not in (headers or {})]
    sent = False
    complete = asyncio.Event()
    messages = []

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": payload, "more_body": False}
        await complete.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        messages.append(message)
        if message["type"] == "http.response.body" and not message.get("more_body", False):
            complete.set()

    scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"}, "http_version": "1.1",
             "method": method, "scheme": "http", "path": parsed.path, "raw_path": parsed.path.encode(),
             "query_string": parsed.query.encode(), "headers": request_headers,
             "client": ("127.0.0.1", 12345), "server": ("testserver", 80), "root_path": ""}
    await asyncio.wait_for(app(scope, receive, send), timeout=10)
    start = next(m for m in messages if m["type"] == "http.response.start")
    response_body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    response_headers = {k.decode(): v.decode() for k, v in start["headers"]}
    data = json.loads(response_body) if response_body and "application/json" in response_headers.get("content-type", "") else response_body
    return start["status"], data, response_headers

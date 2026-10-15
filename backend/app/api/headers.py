"""Apply the same browser policy to success, authorization, and error responses."""

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; "
    "frame-ancestors 'none'; form-action 'self'"
)


def apply_headers(response, settings, path):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = CSP
    if settings.secure_cookies:
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    if path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response

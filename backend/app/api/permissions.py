"""One server policy shared by middleware and the generated API contract."""

PUBLIC_ROUTES = {
    ("GET", "/api/v1/health"),
    ("GET", "/api/v1/ready"),
    ("GET", "/api/v1/auth/status"),
    ("POST", "/api/v1/auth/login"),
    ("GET", "/api/v1/auth/oidc/start"),
    ("GET", "/api/v1/auth/oidc/callback"),
}
ROLE_RANK = {"viewer": 0, "analyst": 1, "admin": 2}


def minimum_role(method: str, path: str):
    unsafe = method in {"POST", "PUT", "PATCH", "DELETE"}
    if path in ("/api/v1/users", "/api/v1/audit"):
        return "admin"
    if not unsafe or path in ("/api/v1/auth/logout", "/api/v1/auth/password"):
        return "viewer"
    if path.startswith(("/api/v1/users", "/api/v1/schedules", "/api/v1/model/train")):
        return "admin"
    if path.startswith("/api/v1/alerts/") and path.endswith("/retry"):
        return "admin"
    return "analyst"

"""Create hosted-demo accounts from secret environment values on a fresh demo database.

Hosted demo platforms such as Render have no interactive shell and reset local
storage on restart, so the interactive `manage_users.py` cannot be used there.
This command runs only in demo mode, never prints passwords, and leaves existing
accounts untouched.
"""

import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.core.config import Settings
from backend.app.domain.schemas import UserCreate
from backend.app.repositories.store import Store
from backend.app.services.auth import AuthError, AuthService
from pydantic import ValidationError

ACCOUNTS = (
    ("admin", "CLOUDSENTINEL_DEMO_ADMIN_USERNAME", "admin", "CLOUDSENTINEL_DEMO_ADMIN_PASSWORD"),
    (
        "viewer",
        "CLOUDSENTINEL_DEMO_VIEWER_USERNAME",
        "viewer",
        "CLOUDSENTINEL_DEMO_VIEWER_PASSWORD",
    ),
)


def bootstrap(auth: AuthService, environ=os.environ) -> list[str]:
    """Return the roles created. The administrator is required; the viewer is optional."""
    created = []
    existing = {user["username"] for user in auth.list_users()}
    for role, username_key, default_username, password_key in ACCOUNTS:
        username = environ.get(username_key, default_username).strip().lower()
        password = environ.get(password_key, "")
        if not password:
            if role == "admin" and auth.setup_required():
                raise SystemExit(f"{password_key} is required to create the demo administrator.")
            continue
        if username in existing:
            continue
        try:
            auth.create_user(
                UserCreate(username=username, display_name=username, password=password, role=role),
                actor="hosted-demo-bootstrap",
                bootstrap=role == "admin" and auth.setup_required(),
            )
        except (AuthError, ValidationError):
            raise SystemExit(
                f"Could not create the demo {role}. Use a valid username and a 12–256 character password."
            ) from None
        created.append(role)
    return created


def main():
    settings = Settings.from_env()
    if settings.mode != "demo":
        raise SystemExit("Hosted-demo bootstrap is available only in demo mode.")
    auth = AuthService(Store(settings.database_path))
    try:
        created = bootstrap(auth)
    finally:
        auth.store.database.close()
    print(f"Hosted demo accounts ready ({', '.join(created) or 'already present'}).")


if __name__ == "__main__":
    main()

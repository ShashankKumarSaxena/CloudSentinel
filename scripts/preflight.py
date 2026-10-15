"""Validate configuration and installed dependencies without contacting a cloud."""

from importlib.util import find_spec
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.core.config import Settings
from backend.app.infrastructure.connections import Connections


def inspect(settings: Settings):
    accounts = Connections(settings.accounts_file, required=settings.production).read().accounts
    packages = {"fastapi", "uvicorn", "pydantic", "boto3", "sklearn"}
    if settings.production:
        packages.update({"psycopg", "psycopg_pool"})
    if settings.oidc_issuer:
        packages.update({"authlib", "httpx", "itsdangerous"})
        for file in (settings.oidc_client_secret_file, settings.oidc_state_secret_file):
            if not file.is_file():
                raise ValueError("A corporate sign-in secret file is missing.")
        if len(settings.oidc_state_secret_file.read_text().strip()) < 32:
            raise ValueError("OIDC state secret must contain at least 32 random characters.")
    for account in accounts:
        if account.enabled and account.provider == "azure":
            packages.add("azure.identity")
        if account.enabled and account.provider == "gcp":
            packages.add("google.auth")
    missing = []
    for name in sorted(packages):
        try:
            if find_spec(name) is None:
                missing.append(name)
        except ModuleNotFoundError:
            missing.append(name)
    return {
        "mode": settings.mode,
        "database": "PostgreSQL" if settings.database_url else "SQLite",
        "approved_accounts": sum(account.enabled for account in accounts),
        "oidc_enabled": bool(settings.oidc_issuer),
        "missing_dependencies": missing,
        "ready_for_runtime_verification": not missing,
        "notice": "Configuration-only check. No database, identity-provider, SMTP, or cloud connectivity was verified.",
    }


def main():
    try:
        result = inspect(Settings.from_env())
    except Exception:
        raise SystemExit(
            "Preflight failed: review deployment settings, registry, and private secret paths."
        ) from None
    print(json.dumps(result, indent=2))
    if result["missing_dependencies"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

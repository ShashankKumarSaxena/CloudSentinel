"""Validated deployment settings; production fails closed instead of guessing."""

from pathlib import Path
from typing import Literal
from urllib.parse import urlparse
import os

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

from backend.app.core.paths import PROJECT_ROOT

VERSION = "1.0.0"


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)

    mode: Literal["demo", "production"] = "demo"
    database_path: Path = PROJECT_ROOT / ".runtime/cloudsentinel.db"
    database_url: SecretStr | None = None
    model_dir: Path | None = None
    accounts_file: Path | None = None
    public_url: str = "http://127.0.0.1:8000"
    allowed_hosts: tuple[str, ...] = ("127.0.0.1", "localhost", "testserver")
    secure_cookies: bool = False
    embedded_worker: bool = True
    docs_enabled: bool = True
    live_ml_enabled: bool = False
    allow_live_in_demo: bool = False
    session_ttl_seconds: int = Field(
        default_factory=lambda data: 3600 if data.get("mode", "demo") == "production" else 28800,
        ge=300,
        le=28800,
    )
    idle_timeout_seconds: int = Field(
        default_factory=lambda data: 900 if data.get("mode", "demo") == "production" else 1800,
        ge=60,
        le=1800,
    )
    max_pending_jobs: int = Field(default=500, ge=1, le=10000)
    worker_stale_seconds: int = Field(default=240, ge=150, le=3600)
    oidc_issuer: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret_file: Path | None = None
    oidc_state_secret_file: Path | None = None

    @property
    def production(self) -> bool:
        return self.mode == "production"

    @model_validator(mode="after")
    def validate_deployment(self):
        if not self.allowed_hosts or any("*" in host for host in self.allowed_hosts):
            raise ValueError("Explicit allowed hosts are required; wildcards are forbidden.")
        origin = urlparse(self.public_url)
        if (
            origin.username
            or origin.password
            or origin.query
            or origin.fragment
            or origin.path not in ("", "/")
        ):
            raise ValueError("Public URL must be a single origin without credentials or a path.")
        if origin.scheme not in ("http", "https") or origin.hostname not in self.allowed_hosts:
            raise ValueError("Public URL must use HTTP(S) and an explicitly allowed host.")
        if not self.production and self.database_url is not None:
            raise ValueError("Demo mode uses SQLite and cannot connect to a production database.")
        if self.production:
            if origin.scheme != "https" or not self.secure_cookies:
                raise ValueError("Production requires HTTPS and secure cookies.")
            if not self.database_url or not self.database_url.get_secret_value().startswith(
                ("postgresql://", "postgres://")
            ):
                raise ValueError("Production requires a PostgreSQL database URL from a secret.")
            if self.accounts_file is None or self.model_dir is None:
                raise ValueError(
                    "Production requires explicit account registry and model directory paths."
                )
            if self.embedded_worker:
                raise ValueError("Production runs a dedicated worker; disable the embedded worker.")
        oidc_fields = (
            self.oidc_issuer,
            self.oidc_client_id,
            self.oidc_client_secret_file,
            self.oidc_state_secret_file,
        )
        if any(oidc_fields) and not all(oidc_fields):
            raise ValueError(
                "OIDC requires issuer, client ID, client-secret file and state-secret file."
            )
        if self.oidc_issuer and urlparse(self.oidc_issuer).scheme != "https":
            raise ValueError("OIDC issuer must use HTTPS.")
        return self

    @classmethod
    def from_env(cls, **overrides):
        def flag(name, default):
            value = os.environ.get("CLOUDSENTINEL_" + name, "1" if default else "0")
            if value not in ("0", "1"):
                raise ValueError(f"CLOUDSENTINEL_{name} must be 0 or 1.")
            return value == "1"

        mode = os.environ.get("CLOUDSENTINEL_MODE", "demo")
        production = mode == "production"
        url_file = os.environ.get("CLOUDSENTINEL_DATABASE_URL_FILE")
        url = (
            Path(url_file).read_text().strip()
            if url_file
            else os.environ.get("CLOUDSENTINEL_DATABASE_URL")
        )
        values = {
            "mode": mode,
            "database_path": os.environ.get(
                "CLOUDSENTINEL_DB", PROJECT_ROOT / ".runtime/cloudsentinel.db"
            ),
            "database_url": SecretStr(url) if url else None,
            "model_dir": os.environ.get("CLOUDSENTINEL_MODEL_DIR"),
            "accounts_file": os.environ.get("CLOUDSENTINEL_ACCOUNTS_FILE"),
            "public_url": os.environ.get("CLOUDSENTINEL_PUBLIC_URL", "http://127.0.0.1:8000"),
            "allowed_hosts": tuple(
                v.strip()
                for v in os.environ.get(
                    "CLOUDSENTINEL_ALLOWED_HOSTS", "127.0.0.1,localhost,testserver"
                ).split(",")
                if v.strip()
            ),
            "secure_cookies": flag("SECURE_COOKIES", production),
            "embedded_worker": flag("MONITORING", not production),
            "docs_enabled": flag("DOCS", not production),
            "live_ml_enabled": flag("LIVE_ML_ENABLED", False),
            "session_ttl_seconds": os.environ.get(
                "CLOUDSENTINEL_SESSION_TTL_SECONDS", 3600 if production else 28800
            ),
            "idle_timeout_seconds": os.environ.get(
                "CLOUDSENTINEL_IDLE_TIMEOUT_SECONDS", 900 if production else 1800
            ),
            "allow_live_in_demo": flag("ALLOW_LIVE_IN_DEMO", False),
            "max_pending_jobs": os.environ.get("CLOUDSENTINEL_MAX_PENDING_JOBS", 500),
            "worker_stale_seconds": os.environ.get("CLOUDSENTINEL_WORKER_STALE_SECONDS", 240),
            "oidc_issuer": os.environ.get("CLOUDSENTINEL_OIDC_ISSUER"),
            "oidc_client_id": os.environ.get("CLOUDSENTINEL_OIDC_CLIENT_ID"),
            "oidc_client_secret_file": os.environ.get("CLOUDSENTINEL_OIDC_CLIENT_SECRET_FILE"),
            "oidc_state_secret_file": os.environ.get("CLOUDSENTINEL_OIDC_STATE_SECRET_FILE"),
        }
        values.update({key: value for key, value in overrides.items() if value is not None})
        return cls(**values)

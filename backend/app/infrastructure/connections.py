"""Resolve only operator-approved account scopes before obtaining credentials."""

from pathlib import Path

from backend.app.domain.cloud import AccountRegistry
from backend.app.domain.schemas import CollectionRequest
from backend.app.infrastructure.collectors.base import CollectionError


class Connections:
    def __init__(self, filename: Path | None, required: bool = False):
        self.filename = filename
        self.required = required
        self.read()  # Reject a malformed mounted registry before accepting traffic.

    def read(self) -> AccountRegistry:
        if self.filename is None:
            if self.required:
                raise ValueError("An approved cloud account registry is required.")
            return AccountRegistry()
        try:
            if self.filename.stat().st_size > 1024 * 1024:
                raise ValueError("Registry exceeds 1 MB.")
            return AccountRegistry.model_validate_json(self.filename.read_text())
        except Exception:
            raise ValueError(
                "Cloud account registry is unavailable or invalid; review its local configuration."
            ) from None

    def list(self):
        return [account.public() for account in self.read().accounts]

    def resolve(self, request: CollectionRequest):
        # Resolve again at execution, so disabling/removing an account also blocks
        # previously queued jobs. Browser callers cannot choose credentials/roles.
        try:
            account = next(
                account for account in self.read().accounts if account.id == request.connection_id
            )
        except (StopIteration, ValueError):
            raise CollectionError("Select an available approved cloud account.") from None
        if not account.enabled or account.provider != request.provider:
            raise CollectionError("This cloud account is disabled or does not match the provider.")
        if request.region not in account.regions:
            raise CollectionError("The selected region is not approved for this account.")
        if request.account and request.account != account.account:
            raise CollectionError("The requested account does not match the approved connection.")
        return account, request.model_copy(update={"account": account.account})

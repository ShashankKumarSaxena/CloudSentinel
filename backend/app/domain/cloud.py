"""Approved account metadata; configuration contains references, never cloud keys."""

from typing import Literal
import re

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.domain.schemas import Provider


class CloudAccount(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,63}$")
    name: str = Field(min_length=1, max_length=100)
    provider: Provider
    account: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9-]+$")
    regions: tuple[str, ...]
    enabled: bool = False
    auth: Literal["default", "assume_role", "managed_identity", "workload_identity", "adc"]
    aws_role_arn: str | None = None
    aws_external_id: str | None = Field(default=None, min_length=2, max_length=1224)
    azure_client_id: str | None = None
    azure_tenant_id: str | None = None
    gcp_service_account: str | None = None

    @model_validator(mode="after")
    def validate_scope(self):
        allowed = {
            "aws": {"default", "assume_role"},
            "azure": {"managed_identity", "workload_identity"},
            "gcp": {"adc"},
        }
        if self.auth not in allowed[self.provider]:
            raise ValueError("Credential method is not supported for this provider.")
        if not self.regions or any(
            not re.fullmatch(r"[a-z0-9-]{1,60}", region) for region in self.regions
        ):
            raise ValueError("Configure at least one explicit valid region.")
        if self.provider == "aws" and not re.fullmatch(r"\d{12}", self.account):
            raise ValueError("AWS account must contain exactly 12 digits.")
        if self.provider != "aws" and self.regions != ("global",):
            raise ValueError(
                "Azure subscriptions and GCP projects currently require global collection scope."
            )
        if self.provider == "azure" and not re.fullmatch(
            r"[a-fA-F0-9]{8}(?:-[a-fA-F0-9]{4}){3}-[a-fA-F0-9]{12}", self.account
        ):
            raise ValueError("Use a valid Azure subscription UUID.")
        if self.provider == "gcp" and not re.fullmatch(
            r"(?:[a-z][a-z0-9-]{4,28}[a-z0-9]|[0-9]{6,20})", self.account
        ):
            raise ValueError("Use a valid GCP project ID or project number.")
        if self.auth == "assume_role":
            arn = re.fullmatch(r"arn:aws:iam::(\d{12}):role/[\w+=,.@/-]+", self.aws_role_arn or "")
            if not arn or arn.group(1) != self.account or not self.aws_external_id:
                raise ValueError("Assumed roles require a matching account ARN and external ID.")
        if self.auth == "workload_identity" and not (self.azure_client_id and self.azure_tenant_id):
            raise ValueError("Workload identity requires explicit tenant and client IDs.")
        return self

    def public(self):
        return {
            key: getattr(self, key)
            for key in ("id", "name", "provider", "account", "regions", "enabled", "auth")
        }


class AccountRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1"] = "1"
    accounts: list[CloudAccount] = Field(default_factory=list, max_length=500)

    @model_validator(mode="after")
    def unique_ids(self):
        if len({account.id for account in self.accounts}) != len(self.accounts):
            raise ValueError("Cloud connection IDs must be unique.")
        return self

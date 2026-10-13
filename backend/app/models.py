"""Validated, provider-neutral configuration contracts for Phase 1."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Provider = Literal["aws", "azure", "gcp"]
ResourceType = Literal["storage", "identity", "firewall", "audit"]
Disposition = Literal["open", "acknowledged", "resolved"]


class Configuration(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    public_access: bool | None = None
    encrypted: bool | None = None
    permissions: list[str] | None = Field(default=None, max_length=100)
    admin: bool | None = None
    mfa_enabled: bool | None = None
    ingress_cidrs: list[str] | None = Field(default=None, max_length=100)
    ports: list[int] | None = Field(default=None, max_length=100)
    logging_enabled: bool | None = None

    @model_validator(mode="after")
    def validate_network(self):
        import ipaddress
        for cidr in self.ingress_cidrs or []:
            ipaddress.ip_network(cidr, strict=False)
        for port in self.ports or []:
            if not 0 <= port <= 65535:
                raise ValueError("Ports must be between 0 (all ports) and 65535")
        return self


class Resource(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str = Field(min_length=1, max_length=180, pattern=r"^[a-zA-Z0-9:/_.@-]+$")
    name: str = Field(min_length=1, max_length=120)
    provider: Provider
    type: ResourceType
    region: str = Field(min_length=1, max_length=80)
    account: str = Field(min_length=1, max_length=80)
    config: Configuration


class Inventory(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal["1.0"]
    name: str = Field(min_length=1, max_length=100)
    resources: list[Resource] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def unique_resources(self):
        ids = [(r.provider, r.id) for r in self.resources]
        if len(ids) != len(set(ids)):
            raise ValueError("Resource IDs must be unique within each provider")
        return self


class TriageUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Disposition

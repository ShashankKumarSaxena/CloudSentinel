"""Validated, provider-neutral configuration and activity contracts."""

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

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
    events: list["ActivityEvent"] = Field(default_factory=list, max_length=10000)

    @model_validator(mode="after")
    def unique_resources(self):
        ids = [(r.provider, r.account, r.id) for r in self.resources]
        if len(ids) != len(set(ids)):
            raise ValueError("Resource IDs must be unique within each provider and account")
        event_ids = [(e.provider, e.account, e.id) for e in self.events]
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("Event IDs must be unique within each provider and account")
        return self


class TriageUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Disposition
    scan_id: str | None = Field(default=None, pattern=r"^[a-f0-9-]{36}$")


class ActivityEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str = Field(min_length=1, max_length=180)
    provider: Provider
    account: str = Field(min_length=1, max_length=80)
    principal: str = Field(min_length=1, max_length=180)
    timestamp: str = Field(min_length=1, max_length=40)
    action: str = Field(min_length=1, max_length=180)
    region: str = Field(default="global", min_length=1, max_length=80)
    source_ip: str | None = Field(default=None, max_length=80)
    success: bool | None = None
    sensitive: bool | None = None

    @model_validator(mode="after")
    def valid_timestamp(self):
        parsed = datetime.fromisoformat(self.timestamp.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("Activity timestamps must include a UTC offset")
        self.timestamp = parsed.astimezone(timezone.utc).isoformat()
        return self


class ActivityFeatures(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    event_count: int = Field(ge=1, le=100000)
    failure_rate: float | None = Field(default=None, ge=0, le=1)
    distinct_ips: int | None = Field(default=None, ge=1, le=100000)
    distinct_regions: int = Field(ge=1, le=1000)
    off_hours_rate: float = Field(ge=0, le=1)
    sensitive_rate: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def feasible_counts(self):
        if self.distinct_regions > self.event_count or (self.distinct_ips or 0) > self.event_count:
            raise ValueError("Distinct counts cannot exceed the event count")
        return self


class TrainingSample(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str = Field(min_length=1, max_length=180)
    features: ActivityFeatures
    label: Literal["normal", "anomaly"]
    scenario: str = Field(min_length=1, max_length=80)


class TrainingDataset(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    name: str = Field(min_length=1, max_length=100)
    provenance: Literal["synthetic", "user_labeled"]
    train: list[TrainingSample] = Field(min_length=100, max_length=5000)
    calibration: list[TrainingSample] = Field(min_length=50, max_length=5000)
    evaluation: list[TrainingSample] = Field(min_length=50, max_length=5000)

    @model_validator(mode="after")
    def independent_splits(self):
        import json

        ids, fingerprints = set(), set()
        for split_name in ("train", "calibration", "evaluation"):
            for sample in getattr(self, split_name):
                if sample.id in ids:
                    raise ValueError("Sample IDs must be unique across all splits")
                ids.add(sample.id)
                fingerprint = json.dumps(sample.features.model_dump(), sort_keys=True)
                if fingerprint in fingerprints:
                    raise ValueError(
                        "Duplicate feature rows across or within splits are not allowed"
                    )
                fingerprints.add(fingerprint)
                if any(value is None for value in sample.features.model_dump().values()):
                    raise ValueError("Training datasets must contain complete feature rows")
                if split_name != "evaluation" and sample.label != "normal":
                    raise ValueError(
                        "Training and calibration must contain reviewed normal samples only"
                    )
        if {sample.label for sample in self.evaluation} != {"normal", "anomaly"}:
            raise ValueError("Evaluation requires both normal and anomalous labels")
        return self


class CollectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    provider: Provider
    connection_id: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9-]{1,63}$")
    region: str = Field(default="ap-south-1", min_length=1, max_length=60, pattern=r"^[a-z0-9-]+$")
    account: str | None = Field(default=None, max_length=80, pattern=r"^[a-zA-Z0-9-]+$")
    lookback_hours: int = Field(default=24, ge=1, le=168)


Inventory.model_rebuild()

Role = Literal["admin", "analyst", "viewer"]


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=80)
    password: SecretStr = Field(min_length=1, max_length=256)


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    username: str = Field(min_length=3, max_length=60, pattern=r"^[a-zA-Z0-9_.-]+$")
    display_name: str = Field(min_length=1, max_length=80)
    password: SecretStr | None = Field(default=None, min_length=12, max_length=256)
    oidc_subject: str | None = Field(default=None, min_length=1, max_length=255)
    role: Role = "viewer"

    @model_validator(mode="after")
    def authentication_method(self):
        if self.password is None and self.oidc_subject is None:
            raise ValueError("Choose a local password or an approved corporate subject.")
        return self


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    role: Role | None = None
    enabled: bool | None = None


class PasswordChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: SecretStr = Field(min_length=1, max_length=256)
    new_password: SecretStr = Field(min_length=12, max_length=256)


class ScheduleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    name: str = Field(min_length=1, max_length=100)
    kind: Literal["demo", "live"] = "demo"
    interval_seconds: int = Field(default=3600, ge=60, le=604800)
    enabled: bool = True
    collection: CollectionRequest | None = None

    @model_validator(mode="after")
    def collection_scope(self):
        if self.kind == "live" and self.collection is None:
            raise ValueError("Live schedules require an explicit cloud collection scope")
        if self.kind == "demo" and self.collection is not None:
            raise ValueError(
                "Synthetic schedules cannot include cloud credentials or collection settings"
            )
        return self


class ScheduleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    enabled: bool | None = None
    interval_seconds: int | None = Field(default=None, ge=60, le=604800)


class IdentityLink(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    subject: str = Field(min_length=1, max_length=255)

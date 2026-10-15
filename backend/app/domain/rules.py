"""Deterministic baseline checks. This module does not implement ML."""

from dataclasses import dataclass
import hashlib
import ipaddress

from backend.app.domain.schemas import Resource


@dataclass(frozen=True)
class Rule:
    id: str
    title: str
    type: str
    severity: str
    category: str
    fields: tuple[str, ...]
    description: str
    remediation: str


RULES = (
    Rule(
        "STO-001",
        "Storage exposed to the public",
        "storage",
        "critical",
        "Storage security",
        ("public_access",),
        "Anonymous access can expose stored data to anyone on the internet.",
        "Disable anonymous access. Enable the provider's public access prevention controls, then verify access with an unauthenticated request.",
    ),
    Rule(
        "STO-002",
        "Storage encryption is disabled",
        "storage",
        "medium",
        "Data protection",
        ("encrypted",),
        "The imported configuration reports no encryption at rest.",
        "Enable encryption at rest using a provider-managed or customer-managed key. Verify that existing objects are covered by the selected policy.",
    ),
    Rule(
        "IAM-001",
        "Identity has wildcard permissions",
        "identity",
        "high",
        "Identity & access",
        ("permissions",),
        "An identity has an unrestricted permission marker in its normalized configuration.",
        "Replace wildcard grants with the specific actions and resources the workload needs. Review the policy with the cloud provider's access analysis tools.",
    ),
    Rule(
        "IAM-002",
        "Privileged identity has no MFA",
        "identity",
        "high",
        "Identity & access",
        ("admin", "mfa_enabled"),
        "A privileged human identity is reported without multifactor authentication.",
        "Require MFA for this privileged human identity and verify enforcement through the identity provider. Use workload identities rather than human credentials for services.",
    ),
    Rule(
        "NET-001",
        "Management ports open to the internet",
        "firewall",
        "high",
        "Network security",
        ("ingress_cidrs", "ports"),
        "The configuration permits a world-accessible range to reach SSH, RDP, or all ports.",
        "Restrict SSH (22) and RDP (3389) to approved ranges. Prefer a private bastion or a managed session service. Review IPv4 and IPv6 rules.",
    ),
    Rule(
        "LOG-001",
        "Audit logging is disabled",
        "audit",
        "medium",
        "Monitoring",
        ("logging_enabled",),
        "Disabled audit logging reduces visibility into account activity.",
        "Enable the provider's audit logging, send logs to a protected destination, and define an appropriate retention policy.",
    ),
)


def evaluate(rule: Rule, resource: Resource) -> tuple[str, dict]:
    config = resource.config.model_dump()
    evidence = {key: config[key] for key in rule.fields}
    # MFA does not apply to non-admin identities, even if its flag is unknown.
    if rule.id == "IAM-002" and config["admin"] is False:
        return "pass", evidence
    if any(evidence[key] is None for key in rule.fields):
        return "unknown", evidence
    failed = {
        "STO-001": lambda: config["public_access"] is True,
        "STO-002": lambda: config["encrypted"] is False,
        "IAM-001": lambda: any("*" in permission for permission in config["permissions"]),
        "IAM-002": lambda: config["admin"] is True and config["mfa_enabled"] is False,
        "NET-001": lambda: any(
            ipaddress.ip_network(cidr, strict=False).prefixlen == 0
            for cidr in config["ingress_cidrs"]
        )
        and bool({0, 22, 3389}.intersection(config["ports"])),
        "LOG-001": lambda: config["logging_enabled"] is False,
    }[rule.id]()
    return ("fail" if failed else "pass"), evidence


def finding_identifier(provider: str, account: str, resource_id: str, rule_id: str) -> str:
    """An account is part of resource identity, even when providers reuse IDs."""
    return hashlib.sha256(f"v2:{provider}:{account}:{resource_id}:{rule_id}".encode()).hexdigest()[
        :24
    ]


def scan_resources(resources: list[Resource]) -> dict:
    checks, findings = [], []
    for resource in resources:
        for rule in RULES:
            if resource.type != rule.type:
                continue
            outcome, evidence = evaluate(rule, resource)
            checks.append(
                {
                    "rule_id": rule.id,
                    "resource_id": resource.id,
                    "provider": resource.provider,
                    "account": resource.account,
                    "outcome": outcome,
                    "evidence": evidence,
                }
            )
            if outcome != "fail":
                continue
            fingerprint = finding_identifier(
                resource.provider, resource.account, resource.id, rule.id
            )
            findings.append(
                {
                    "id": fingerprint,
                    "rule_id": rule.id,
                    "title": rule.title,
                    "severity": rule.severity,
                    "category": rule.category,
                    "resource_id": resource.id,
                    "resource_name": resource.name,
                    "resource_type": resource.type,
                    "provider": resource.provider,
                    "region": resource.region,
                    "account": resource.account,
                    "description": rule.description,
                    "remediation": rule.remediation,
                    "evidence": evidence,
                }
            )
    counts = {
        state: sum(c["outcome"] == state for c in checks) for state in ("pass", "fail", "unknown")
    }
    known = counts["pass"] + counts["fail"]
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    findings.sort(key=lambda f: (severity_order[f["severity"]], f["provider"], f["resource_name"]))
    return {
        "checks": checks,
        "findings": findings,
        "summary": {
            "resources": len(resources),
            "total_checks": len(checks),
            "passed": counts["pass"],
            "failed": counts["fail"],
            "unknown": counts["unknown"],
            "posture_score": round(counts["pass"] / known * 100) if known else None,
        },
    }

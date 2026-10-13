"""Hourly provider/account/principal windows shared by imports and collectors."""
from collections import defaultdict
from datetime import datetime
import hashlib

from .models import ActivityEvent, ActivityFeatures

FEATURE_NAMES = ("event_count", "failure_rate", "distinct_ips", "distinct_regions", "off_hours_rate", "sensitive_rate")


def sensitive_action(action: str) -> bool:
    value = action.lower()
    return any(marker in value for marker in (
        "delete", "remove", "putbucketpolicy", "putrolepolicy", "attachuserpolicy",
        "attachrolepolicy", "createaccesskey", "setiampolicy", "roleassignments/write",
        "securityrules/write", "firewalls.insert", "firewalls.patch", "updatepolicy"))


def aggregate(events: list[ActivityEvent]) -> list[dict]:
    groups = defaultdict(list)
    for event in events:
        timestamp = datetime.fromisoformat(event.timestamp).replace(minute=0, second=0, microsecond=0)
        groups[(event.provider, event.account, event.principal, timestamp.isoformat())].append(event)
    windows = []
    for (provider, account, principal, start), entries in sorted(groups.items()):
        count = len(entries)
        features = ActivityFeatures(
            event_count=count,
            failure_rate=sum(e.success is False for e in entries) / count if all(e.success is not None for e in entries) else None,
            distinct_ips=len({e.source_ip for e in entries}) if all(e.source_ip for e in entries) else None,
            distinct_regions=len({e.region for e in entries}),
            off_hours_rate=sum(datetime.fromisoformat(e.timestamp).hour < 6 or datetime.fromisoformat(e.timestamp).hour >= 22 for e in entries) / count,
            sensitive_rate=sum(e.sensitive is True for e in entries) / count if all(e.sensitive is not None for e in entries) else None,
        )
        identity = f"{provider}:{account}:{principal}:{start}"
        windows.append({"id": hashlib.sha256(identity.encode()).hexdigest()[:24], "provider": provider,
                        "account": account, "principal": principal, "window_start": start,
                        "features": features.model_dump(), "actions": sorted({e.action for e in entries})[:10]})
    return windows

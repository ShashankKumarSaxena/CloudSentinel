from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler

from ..activity import sensitive_action
from ..models import ActivityEvent, Inventory, Resource

MAX_RESOURCES = 1000
MAX_EVENTS = 10000
MAX_PAGES = 30
MAX_RESPONSE = 8 * 1024 * 1024


class CollectionError(Exception):
    """Safe, action-oriented error. Never include provider response bodies."""


@dataclass
class CollectionResult:
    provider: str
    account: str
    resources: list[Resource] = field(default_factory=list)
    events: list[ActivityEvent] = field(default_factory=list)
    coverage: list[dict] = field(default_factory=list)
    started: float = field(default_factory=time.monotonic)

    def check_budget(self):
        if time.monotonic() - self.started > 120:
            raise CollectionError("Collection reached its two-minute request budget. Narrow the scope and try again.")

    def attempt(self, scope, operation):
        self.check_budget()
        try:
            result = operation()
            self.coverage.append({"scope": scope, "status": "collected"})
            return result
        except Exception:
            self.coverage.append({"scope": scope, "status": "unavailable", "message": "Could not read this scope. Check read permissions, account configuration, and network access."})
            return None

    def add_resource(self, **data):
        self.check_budget()
        if len(self.resources) >= MAX_RESOURCES:
            raise CollectionError("Resource limit reached. Narrow the collection scope.")
        self.resources.append(Resource.model_validate(data | {"provider": self.provider, "account": self.account}))

    def add_event(self, **data):
        self.check_budget()
        if len(self.events) >= MAX_EVENTS:
            raise CollectionError("Activity event limit reached. Reduce the lookback window.")
        if not data.get("principal") or not data.get("timestamp"):
            self.coverage.append({"scope": "activity event normalization", "status": "unavailable", "message": "An event without a principal or timestamp was excluded."})
            return
        self.events.append(ActivityEvent.model_validate(data | {"provider": self.provider, "account": self.account}))

    def finish(self):
        if not self.resources:
            raise CollectionError("No supported resources were collected. Check account scope and read permissions; the latest scan was preserved.")
        # API pagination can repeat events at page boundaries.
        self.events = list({(e.provider, e.id): e for e in self.events}.values())
        inventory = Inventory(schema_version="1.0", name=f"{self.provider.upper()} read-only collection", resources=self.resources, events=self.events)
        metadata = {"provider": self.provider, "account": self.account, "read_only": True,
                    "coverage": self.coverage, "partial": any(c["status"] != "collected" for c in self.coverage),
                    "event_count": len(self.events), "resource_count": len(self.resources)}
        return inventory, metadata


def bounds(hours):
    end = datetime.now(timezone.utc)
    return end - timedelta(hours=hours), end


def identifier(value):
    cleaned = re.sub(r"[^a-zA-Z0-9:/_.@-]", "_", str(value))
    return cleaned if len(cleaned) <= 180 else cleaned[:140] + "-" + hashlib.sha256(cleaned.encode()).hexdigest()[:20]


def cli_token(command):
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=20, check=True)
        token = completed.stdout.strip()
        if not token or "\n" in token:
            raise CollectionError("The local cloud CLI returned an invalid credential response.")
        return token
    except (OSError, subprocess.SubprocessError):
        raise CollectionError("The provider CLI is unavailable or signed out. Configure it locally before collection.") from None


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise CollectionError("Cloud API redirect rejected to protect local credentials.")


class RestClient:
    def __init__(self, token, hosts):
        self.token = token
        self.hosts = set(hosts)
        self.opener = build_opener(NoRedirect())

    def request(self, url, body=None):
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in self.hosts or parsed.username or parsed.password or parsed.port not in (None, 443):
            raise CollectionError("Unexpected cloud API pagination destination rejected.")
        payload = json.dumps(body).encode() if body is not None else None
        req = Request(url, data=payload, headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"})
        for attempt in range(3):
            try:
                with self.opener.open(req, timeout=10) as response:
                    content = response.read(MAX_RESPONSE + 1)
                if len(content) > MAX_RESPONSE:
                    raise CollectionError("Cloud API response exceeded the supported size.")
                return json.loads(content)
            except HTTPError as error:
                if error.code in (429, 500, 502, 503) and attempt < 2:
                    time.sleep(.25 * (attempt + 1))
                    continue
                raise CollectionError(f"Cloud API request failed (HTTP {error.code}). Check permissions and account scope.") from None
            except (URLError, TimeoutError, OSError, ValueError):
                raise CollectionError("Cloud API is unreachable or returned an invalid response.") from None

    def azure_pages(self, url):
        seen = set()
        for _ in range(MAX_PAGES):
            if url in seen:
                raise CollectionError("Cloud API returned a repeated pagination link.")
            seen.add(url)
            result = self.request(url)
            yield from result.get("value", [])
            url = result.get("nextLink")
            if not url:
                return
        raise CollectionError("Pagination limit reached. Narrow the account scope.")

    def google_pages(self, url, key="items", body=None):
        from urllib.parse import urlencode
        original = url
        seen = set()
        for _ in range(MAX_PAGES):
            result = self.request(url, body)
            yield from result.get(key, [])
            token = result.get("nextPageToken")
            if not token:
                return
            if token in seen:
                raise CollectionError("Cloud API returned a repeated page token.")
            seen.add(token)
            if body is not None:
                body = body | {"pageToken": token}
            else:
                url = original + ("&" if "?" in original else "?") + urlencode({"pageToken": token})
        raise CollectionError("Pagination limit reached. Narrow the account scope.")


def activity_fields(action, success, principal, timestamp, event_id, region="global", source_ip=None):
    return {"id": identifier(event_id), "principal": str(principal)[:180] if principal else "",
            "timestamp": timestamp, "action": str(action)[:180], "region": str(region or "global")[:80],
            "source_ip": str(source_ip)[:80] if source_ip else None, "success": success,
            "sensitive": sensitive_action(str(action))}

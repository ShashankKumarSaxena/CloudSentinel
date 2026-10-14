"""GCP read APIs using a token from the local gcloud credential chain."""
import os
from urllib.parse import quote, urlencode

from .base import CollectionError, CollectionResult, RestClient, activity_fields, bounds, local_token, identifier


def public_bucket(bucket, policy):
    iam = bucket.get("iamConfiguration", {})
    if iam.get("publicAccessPrevention") == "enforced":
        return False
    public_bindings = [b for b in (policy or {}).get("bindings", []) if "allUsers" in b.get("members", []) or "allAuthenticatedUsers" in b.get("members", [])]
    if public_bindings and any(b.get("condition") for b in public_bindings):
        return None
    if public_bindings and iam.get("publicAccessPrevention") == "inherited":
        return None
    if public_bindings:
        return True
    if policy is not None and iam.get("uniformBucketLevelAccess", {}).get("enabled") is True:
        return False
    return None  # Legacy object ACLs or inherited access have not been evaluated.


def firewall_ports(rule):
    ports = []
    for allowed in rule.get("allowed", []):
        if allowed.get("IPProtocol") == "all":
            return [0]
        if allowed.get("IPProtocol") not in ("tcp", "6"):
            continue
        if not allowed.get("ports"):
            return [0]
        for value in allowed["ports"]:
            low, high = map(int, value.split("-")) if "-" in value else (int(value), int(value))
            ports += [p for p in (22, 3389) if low <= p <= high]
    return sorted(set(ports))


def collect_gcp(request, rest=None):
    account = request.account or os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not account:
        raise CollectionError("Set GOOGLE_CLOUD_PROJECT locally or select a project ID before collection.")
    if rest is None:
        token = local_token("CLOUDSENTINEL_GCP_TOKEN_FILE", ["gcloud", "auth", "print-access-token"])
        rest = RestClient(token, {"storage.googleapis.com", "compute.googleapis.com", "logging.googleapis.com"})
    result = CollectionResult("gcp", account)
    project = quote(account, safe="")

    def storage():
        for bucket in rest.google_pages("https://storage.googleapis.com/storage/v1/b?" + urlencode({"project": account, "maxResults": 100})):
            result.check_budget()
            policy = result.attempt(f"Bucket IAM: {bucket['name']}", lambda: rest.request(
                f"https://storage.googleapis.com/storage/v1/b/{quote(bucket['name'], safe='')}/iam"))
            result.add_resource(id=f"gcp:storage/{bucket['name']}", name=bucket["name"], type="storage", region=bucket.get("location", "global").lower(),
                                config={"public_access": public_bucket(bucket, policy), "encrypted": True})
    result.attempt("Cloud Storage buckets and IAM", storage)

    def network():
        rules = list(rest.google_pages(f"https://compute.googleapis.com/compute/v1/projects/{project}/global/firewalls?maxResults=100"))
        for rule in rules:
            if rule.get("disabled") or rule.get("direction", "INGRESS") != "INGRESS" or not rule.get("allowed"):
                continue
            overridden = any(other.get("denied") and not other.get("disabled") and other.get("network") == rule.get("network")
                             and other.get("direction", "INGRESS") == "INGRESS" and other.get("priority", 1000) <= rule.get("priority", 1000) for other in rules)
            result.add_resource(id=f"gcp:firewall/{rule['name']}", name=rule["name"], type="firewall", region="global",
                                config={"ingress_cidrs": None if overridden else rule.get("sourceRanges") or (None if rule.get("sourceTags") or rule.get("sourceServiceAccounts") else ["0.0.0.0/0"]),
                                        "ports": firewall_ports(rule)})
    result.attempt("VPC ingress firewall rules; policy limitations apply", network)

    def activity():
        start, end = bounds(request.lookback_hours)
        body = {"resourceNames": [f"projects/{account}"], "filter": f'timestamp >= "{start.isoformat()}" AND timestamp <= "{end.isoformat()}" AND protoPayload.@type="type.googleapis.com/google.cloud.audit.AuditLog"',
                "orderBy": "timestamp desc", "pageSize": 100}
        for event in rest.google_pages("https://logging.googleapis.com/v2/entries:list", "entries", body):
            payload = event.get("protoPayload", {})
            principal = payload.get("authenticationInfo", {}).get("principalEmail")
            success = not bool(payload.get("status", {}).get("code", 0))
            resource_labels = event.get("resource", {}).get("labels", {})
            eid = event.get("insertId") or identifier(str(event.get("logName", "")) + str(event.get("timestamp", "")) + str(principal))
            result.add_event(**activity_fields(payload.get("methodName", "Unknown"), success, principal, event.get("timestamp"),
                eid, resource_labels.get("location", resource_labels.get("region", "global")), payload.get("requestMetadata", {}).get("callerIp")))
    result.attempt("Cloud Audit Logs visible to the selected principal", activity)
    result.coverage.append({"scope": "Effective project IAM, inherited firewall policies, and audit retention", "status": "unsupported", "message": "Not fully evaluated; no safe configuration flags are inferred."})
    return result.finish()

"""Read-only regional AWS collection using the standard boto3 credential chain."""
import json

from botocore.config import Config

from .base import CollectionError, CollectionResult, MAX_PAGES, activity_fields, bounds, identifier


def pages(client, operation, result_key, **kwargs):
    token = None
    token_key = "ContinuationToken" if operation == "list_buckets" else "NextToken"
    for _ in range(MAX_PAGES):
        payload = client.__getattribute__(operation)(**kwargs, **({token_key: token} if token else {}))
        yield from payload.get(result_key, [])
        following = payload.get(token_key)
        if not following:
            return
        if following == token:
            raise CollectionError("AWS returned a repeated pagination token.")
        token = following
    raise CollectionError("AWS pagination limit reached. Narrow the collection scope.")


def public_storage(block, policy, acl):
    if block and all(block.get(k) is True for k in ("BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy", "RestrictPublicBuckets")):
        return False
    if policy and policy.get("IsPublic") is True and not (block or {}).get("RestrictPublicBuckets", False):
        return True
    if acl and not (block or {}).get("IgnorePublicAcls", False):
        if any(g.get("Grantee", {}).get("URI", "").endswith(("/AllUsers", "/AuthenticatedUsers")) for g in acl.get("Grants", [])):
            return True
    # Absence of a public bucket grant does not prove every object is private.
    return None


def collect_aws(request, session=None):
    if session is None:
        import boto3
        session = boto3.Session(region_name=request.region)
    config = Config(connect_timeout=5, read_timeout=10, retries={"max_attempts": 2, "mode": "standard"})
    client = lambda service: session.client(service, region_name=request.region, config=config)
    try:
        account = client("sts").get_caller_identity()["Account"]
    except Exception:
        raise CollectionError("AWS authentication failed. Configure a read-only local profile or role before collection.") from None
    if request.account and request.account != account:
        raise CollectionError("The active AWS account does not match the requested account.")
    result = CollectionResult("aws", account)
    s3 = client("s3")
    s3control = client("s3control")
    account_block = result.attempt("S3 account public-access settings", lambda: s3control.get_public_access_block(AccountId=account))
    account_block = (account_block or {}).get("PublicAccessBlockConfiguration", {})

    def storage():
        for bucket in pages(s3, "list_buckets", "Buckets", MaxBuckets=100):
            result.check_budget()
            name = bucket["Name"]
            location = result.attempt(f"S3 region: {name}", lambda: s3.get_bucket_location(Bucket=name))
            region = (location or {}).get("LocationConstraint") or ("us-east-1" if location is not None else "unknown")
            if region == "EU":
                region = "eu-west-1"
            if region != request.region:
                if region == "unknown":
                    result.coverage.append({"scope": f"S3 bucket: {name}", "status": "unavailable", "message": "Bucket region could not be established; bucket excluded from the regional scope."})
                continue
            block = result.attempt(f"S3 access block: {name}", lambda: s3.get_public_access_block(Bucket=name))
            policy = result.attempt(f"S3 policy status: {name}", lambda: s3.get_bucket_policy_status(Bucket=name))
            acl = result.attempt(f"S3 ACL: {name}", lambda: s3.get_bucket_acl(Bucket=name))
            encryption = result.attempt(f"S3 encryption: {name}", lambda: s3.get_bucket_encryption(Bucket=name))
            merged = {k: account_block.get(k, False) or (block or {}).get("PublicAccessBlockConfiguration", {}).get(k, False)
                      for k in ("BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy", "RestrictPublicBuckets")}
            result.add_resource(id=f"arn:aws:s3:::{name}", name=name, type="storage", region=region,
                                config={"public_access": public_storage(merged, (policy or {}).get("PolicyStatus"), acl),
                                        "encrypted": bool(encryption.get("ServerSideEncryptionConfiguration", {}).get("Rules")) if encryption is not None else None})
    result.attempt("S3 buckets in selected region", storage)

    def network():
        ec2 = client("ec2")
        for group in pages(ec2, "describe_security_groups", "SecurityGroups", MaxResults=100):
            for index, permission in enumerate(group.get("IpPermissions", [])):
                if permission.get("IpProtocol") not in ("-1", "tcp", "6"):
                    continue
                cidrs = [r["CidrIp"] for r in permission.get("IpRanges", [])] + [r["CidrIpv6"] for r in permission.get("Ipv6Ranges", [])]
                if not cidrs:
                    continue
                ports = [0] if permission["IpProtocol"] == "-1" else [p for p in (22, 3389) if permission.get("FromPort", 65536) <= p <= permission.get("ToPort", -1)]
                result.add_resource(id=f"{group['GroupId']}/ingress/{index}", name=f"{group.get('GroupName', group['GroupId'])} ingress {index}",
                                    type="firewall", region=request.region, config={"ingress_cidrs": cidrs, "ports": ports})
    result.attempt("EC2 security-group ingress", network)

    def audit():
        trail = client("cloudtrail")
        for item in trail.describe_trails(includeShadowTrails=False).get("trailList", []):
            status = result.attempt(f"CloudTrail status: {item['Name']}", lambda: trail.get_trail_status(Name=item["TrailARN"]))
            result.add_resource(id=identifier(item["TrailARN"]), name=item["Name"], type="audit", region=request.region,
                                config={"logging_enabled": status.get("IsLogging") if status is not None else None})
    result.attempt("CloudTrail trails", audit)

    def identities():
        iam = client("iam")
        marker = None
        for _ in range(MAX_PAGES):
            users = iam.list_users(MaxItems=100, **({"Marker": marker} if marker else {}))
            for user in users.get("Users", []):
                devices = result.attempt(f"IAM MFA: {user['UserName']}", lambda: iam.list_mfa_devices(UserName=user["UserName"]))
                result.add_resource(id=user["Arn"], name=user["UserName"], type="identity", region="global",
                                    config={"permissions": None, "admin": None,
                                            "mfa_enabled": bool(devices.get("MFADevices")) if devices is not None else None})
            if not users.get("IsTruncated"):
                return
            following = users.get("Marker")
            if not following or following == marker:
                raise CollectionError("AWS IAM pagination could not be completed.")
            marker = following
        raise CollectionError("AWS IAM pagination limit reached.")
    result.attempt("IAM users; effective permissions remain unknown", identities)

    def activity():
        start, end = bounds(request.lookback_hours)
        for entry in pages(client("cloudtrail"), "lookup_events", "Events", StartTime=start, EndTime=end, MaxResults=50):
            raw = json.loads(entry.get("CloudTrailEvent", "{}"))
            identity = raw.get("userIdentity", {})
            success = not bool(raw.get("errorCode"))
            if raw.get("eventName") == "ConsoleLogin":
                response = raw.get("responseElements") or {}
                success = response.get("ConsoleLogin") == "Success" if "ConsoleLogin" in response else None
            result.add_event(**activity_fields(raw.get("eventName", entry.get("EventName", "Unknown")), success,
                identity.get("arn") or identity.get("principalId") or entry.get("Username"),
                raw.get("eventTime") or entry["EventTime"].isoformat(), entry["EventId"], raw.get("awsRegion", request.region), raw.get("sourceIPAddress")))
    result.attempt("CloudTrail management-event history", activity)
    result.coverage.append({"scope": "Effective IAM policies, object ACLs, and organization-level audit coverage", "status": "unsupported", "message": "Not fully evaluated; related missing flags remain unknown."})
    return result.finish()

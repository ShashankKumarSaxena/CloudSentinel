"""Azure Resource Manager reads, authenticated by the user's local Azure CLI."""
import os
from urllib.parse import urlencode

from .base import CollectionError, CollectionResult, RestClient, activity_fields, bounds, local_token, identifier


def public_container(account_properties, container_properties):
    if account_properties.get("allowBlobPublicAccess") is False:
        return False
    access = container_properties.get("publicAccess")
    if access == "None":
        return False
    if access in ("Blob", "Container") and account_properties.get("allowBlobPublicAccess") is True:
        return True
    return None


def rule_ports(rule):
    if str(rule.get("protocol", "")).lower() not in ("tcp", "*"):
        return []
    ranges = rule.get("destinationPortRanges") or [rule.get("destinationPortRange")]
    ports = []
    for value in ranges:
        if value == "*":
            return [0]
        if value is None:
            continue
        try:
            low, high = map(int, value.split("-")) if "-" in value else (int(value), int(value))
            ports += [p for p in (22, 3389) if low <= p <= high]
        except ValueError:
            return None
    return sorted(set(ports))


def collect_azure(request, rest=None):
    account = request.account or os.environ.get("AZURE_SUBSCRIPTION_ID")
    if not account:
        raise CollectionError("Set AZURE_SUBSCRIPTION_ID locally or select a subscription ID before collection.")
    if rest is None:
        token = local_token("CLOUDSENTINEL_AZURE_TOKEN_FILE", ["az", "account", "get-access-token", "--subscription", account, "--resource", "https://management.azure.com/", "--query", "accessToken", "--output", "tsv"])
        rest = RestClient(token, {"management.azure.com"})
    result = CollectionResult("azure", account)
    base = f"https://management.azure.com/subscriptions/{account}"

    def storage():
        for item in rest.azure_pages(base + "/providers/Microsoft.Storage/storageAccounts?api-version=2024-01-01"):
            result.check_budget()
            props = item.get("properties", {})
            containers = result.attempt(f"Storage containers: {item['name']}", lambda: list(rest.azure_pages(
                "https://management.azure.com" + item["id"] + "/blobServices/default/containers?api-version=2024-01-01")))
            encryption = props.get("encryption", {}).get("services", {}).get("blob", {}).get("enabled")
            if not containers:
                result.add_resource(id=identifier(item["id"]), name=item["name"], type="storage", region=item.get("location", "global"),
                                    config={"public_access": False if props.get("allowBlobPublicAccess") is False else None, "encrypted": encryption})
            for container in containers or []:
                result.add_resource(id=identifier(container["id"]), name=f"{item['name']}/{container['name']}", type="storage",
                                    region=item.get("location", "global"), config={"public_access": public_container(props, container.get("properties", {})), "encrypted": encryption})
    result.attempt("Blob storage accounts and containers", storage)

    def network():
        for item in rest.azure_pages(base + "/providers/Microsoft.Network/networkSecurityGroups?api-version=2024-05-01"):
            # Rules are represented individually; NSG priority/deny interactions remain unknown.
            all_rules = item.get("properties", {}).get("securityRules", [])
            for rule in all_rules:
                props = rule.get("properties", {})
                if props.get("direction") != "Inbound" or props.get("access") != "Allow":
                    continue
                sources = props.get("sourceAddressPrefixes") or [props.get("sourceAddressPrefix")]
                cidrs = []
                for source in sources:
                    if source in ("*", "Internet"):
                        cidrs.extend(["0.0.0.0/0", "::/0"])
                    elif source and "/" in source:
                        cidrs.append(source)
                    elif source and source.replace(".", "").isdigit():
                        cidrs.append(source + "/32")
                # A deny can override an allow by priority. Never flatten that to an exposure claim.
                overridden = any(r.get("properties", {}).get("direction") == "Inbound" and
                                 r.get("properties", {}).get("access") == "Deny" and
                                 r.get("properties", {}).get("priority", 65536) < props.get("priority", 65536) for r in all_rules)
                result.add_resource(id=identifier(rule.get("id", item["id"] + "/" + rule["name"])), name=rule["name"], type="firewall",
                                    region=item.get("location", "global"), config={"ingress_cidrs": None if overridden or not cidrs else cidrs,
                                        "ports": rule_ports(props) if props.get("protocol") else None})
    result.attempt("Network security-group ingress; priority limitations apply", network)

    def activity():
        start, end = bounds(request.lookback_hours)
        query = urlencode({"api-version": "2015-04-01", "$filter": f"eventTimestamp ge '{start.isoformat()}' and eventTimestamp le '{end.isoformat()}'"})
        for event in rest.azure_pages(base + "/providers/microsoft.insights/eventtypes/management/values?" + query):
            status = event.get("status", {}).get("value", "").lower()
            success = True if status in ("succeeded", "success") else False if status in ("failed", "failure") else None
            principal = event.get("caller")
            result.add_event(**activity_fields(event.get("operationName", {}).get("value", "Unknown"), success, principal,
                event.get("eventTimestamp"), event.get("eventDataId", identifier(str(event.get("id", "")))), "global",
                event.get("httpRequest", {}).get("clientIpAddress")))
    result.attempt("Azure Activity Log management events", activity)
    result.coverage.append({"scope": "Effective IAM and organization audit retention", "status": "unsupported", "message": "Not collected by this adapter; no safe configuration flags are inferred."})
    return result.finish()

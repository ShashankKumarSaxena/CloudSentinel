# Inventory import contract

Import a UTF-8 JSON file through Cloud inventory → Import inventory. The API
also accepts `POST /api/v1/scans/import` with `Content-Type: application/json`.
The maximum body is 2 MB, containing 1–1,000 resources. Successful validation
creates an atomic scan, becomes the latest inventory, and preserves prior scans.

```json
{
  "schema_version": "1.0",
  "name": "Training sandbox",
  "resources": [
    {
      "id": "training/storage/example",
      "name": "Example bucket",
      "provider": "aws",
      "type": "storage",
      "region": "ap-south-1",
      "account": "training-account",
      "config": {
        "public_access": true,
        "encrypted": true
      }
    }
  ]
}
```

`data/demo_inventory.json` is the full cross-cloud example. Do not include keys,
tokens, passwords, personal information, or other secrets in an inventory.
The schema rejects extra fields.

## Resource fields

| Field | Contract |
| --- | --- |
| `id` | 1–180 characters; letters, digits, `: / _ . @ -`; unique within a provider |
| `name` | Display name, 1–120 characters |
| `provider` | `aws`, `azure`, or `gcp` |
| `type` | `storage`, `identity`, `firewall`, or `audit` |
| `region` | Display region, 1–80 characters |
| `account` | Display account label, 1–80 characters |
| `config` | Object with normalized configuration fields below |

## Configuration fields and meanings

| Resource type | Fields | Meaning |
| --- | --- | --- |
| storage | `public_access`, `encrypted` | Booleans indicating effective anonymous access and encryption at rest |
| identity | `permissions`, `admin`, `mfa_enabled` | Permission markers; privileged human identity flag; enforced MFA flag |
| firewall | `ingress_cidrs`, `ports` | Effective allowed ingress ranges and TCP management ports; port `0` means all ports |
| audit | `logging_enabled` | Boolean indicating enabled account audit logging |

All configuration fields are optional and may be null. Missing fields required
by a check produce unknown, not pass. Permissions and CIDRs are lists of strings;
ports are integers between 0 and 65535. Lists are limited to 100 entries.
The schema is deliberately simplified: protocol distinctions, conditional IAM
grants, explicit deny rules, object ACL interactions, provider-wide settings,
and activity features need richer mapping in later phases.

String booleans such as `"false"` are rejected. Invalid CIDRs, duplicate resource
IDs within a provider, extra fields, empty inventories, and unsupported versions
are rejected with useful field-level validation messages. A failed import does
not replace the latest valid snapshot.

## Response semantics

Each scan includes resources, check outcomes, findings, a summary, UTC timestamp,
source (`demo` or `import`), duration, and ID. Check outcomes are `pass`, `fail`,
or `unknown`. Each failed check produces one finding.

Posture excludes unknown checks from the denominator and is null if no check
has enough data. It can be high even when coverage is low; always show it
alongside unknown counts. Dispositions (`open`, `acknowledged`, `resolved`) are
team decisions and are not verification of remediation.

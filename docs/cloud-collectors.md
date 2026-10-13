# Read-only cloud collectors

Collection starts only when a user submits Cloud connections. Startup, training,
demo scans, and status checks do not contact real accounts. Credentials stay in
local SDK/CLI credential chains. AWS SDK stubs and mocked REST responses validate
mapping and failure behavior; no live-account verification is claimed.

## Authentication and access

| Provider | Local authentication | Implemented reads |
| --- | --- | --- |
| AWS | boto3 profile/environment/SSO/role chain | STS identity; regional S3 metadata; security groups; IAM users/MFA; CloudTrail trails/status/history |
| Azure | Azure CLI Resource Manager token | Storage account/containers; network security groups; Activity Log |
| GCP | gcloud access token | Bucket list/IAM; firewall list; visible audit-log entries |

AWS actions used: `sts:GetCallerIdentity`, `s3:ListAllMyBuckets`,
`s3:GetBucketLocation`, `s3:GetBucketPublicAccessBlock`,
`s3:GetAccountPublicAccessBlock`, `s3:GetBucketPolicyStatus`, `s3:GetBucketAcl`,
`s3:GetEncryptionConfiguration`, `ec2:DescribeSecurityGroups`, `iam:ListUsers`,
`iam:ListMFADevices`, `cloudtrail:DescribeTrails`, `cloudtrail:GetTrailStatus`,
and `cloudtrail:LookupEvents`. Scope permissions to the relevant resources;
the application never creates roles or attaches policies.

Azure read permissions cover `Microsoft.Storage/storageAccounts/read`,
`Microsoft.Storage/storageAccounts/blobServices/containers/read`,
`Microsoft.Network/networkSecurityGroups/read`, and
`Microsoft.Insights/eventtypes/values/read` at the selected scope.

GCP permissions include `storage.buckets.list`, `storage.buckets.getIamPolicy`,
`compute.firewalls.list`, and logging-entry read permissions for the selected log
types. Private Data Access logs may require additional read access.

The form accepts identifiers only: expected AWS account and region, Azure
subscription, or GCP project. Azure/GCP also support `AZURE_SUBSCRIPTION_ID` and
`GOOGLE_CLOUD_PROJECT`. AWS can verify the expected account through STS.
The API never accepts access keys, passwords, tokens, or service-account files.

## Mapping limits

**AWS:** Buckets are filtered to the requested region. Account and bucket access
blocks are merged. All four blocks enforced imply no public bucket exposure;
an unrestricted public policy/ACL is flagged. Other cases remain unknown because
object ACLs and broader policies are not fully evaluated. Encryption comes from
the encryption configuration read. TCP/all-protocol security-group permissions
are independent records to preserve CIDR/port pairing. IAM users have observed
MFA but unknown effective permissions/admin flags. CloudTrail management history
is regional and does not represent complete data access or organization logging.

**Azure:** Account anonymous-access denial overrides container public flags.
Blob/Container grants are public only when the account explicitly allows them;
missing flags stay unknown. Encryption comes from the blob property. Ingress
allows remain separate; preceding denies produce uncertainty. Complex priority,
service-tag, inherited-policy, and effective IAM semantics are not fully resolved.
Activity Log is management-plane coverage, not complete data-plane activity.

**GCP:** Explicit public-access prevention blocks public access. Unconditional
public IAM grants are flagged when prevention is neither inherited nor enforced.
Conditional public grants and inherited prevention remain unknown. No public
grants is private only with uniform bucket-level access; legacy ACLs stay unknown.
Cloud Storage encrypts data at rest, so encryption is true. VPC ingress allows
are separate records; potential prior denies cause unknown CIDRs. Hierarchical
policies and effective project IAM are unsupported. Audit logs include only
entries visible to the authenticated identity.

## Bounds and failures

Limits: 1,000 resources; 10,000 events; 30 pages per API listing; 1–168 hour
lookback; approximately two minutes plus any in-flight request timeout. REST
responses are limited to 8 MB, with request timeouts and bounded transient retries.
Repeated pagination links/tokens are rejected.

Only fixed HTTPS provider hosts are accepted. Redirects and unrelated pagination
destinations are rejected to protect bearer tokens. Provider response bodies,
exception strings, and CLI stdout/stderr are never returned as errors.

Unavailable/unsupported scopes are saved in coverage. Partial results are not a
clean-account verdict. No supported resources means collection fails and the
latest valid scan is preserved. One scan/collection/training mutation runs at a
time in the local process. No mutation or remediation cloud API is called.

## API references

- [AWS CloudTrail lookup](https://docs.aws.amazon.com/boto3/latest/reference/services/cloudtrail/client/lookup_events.html)
- [AWS S3 bucket pagination](https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/list_buckets.html)
- [Azure blob containers](https://learn.microsoft.com/en-us/rest/api/storagerp/blob-containers/list?view=rest-storagerp-2024-01-01)
- [Azure Activity Log](https://learn.microsoft.com/en-us/rest/api/monitor/activity-logs/list?view=rest-monitor-2015-04-01)
- [GCP audit log entries](https://docs.cloud.google.com/logging/docs/reference/v2/rest/v2/entries/list)
- [GCP firewalls](https://docs.cloud.google.com/compute/docs/reference/rest/v1/firewalls/list)
- [GCP public access prevention](https://docs.cloud.google.com/storage/docs/public-access-prevention)
- [GCP encryption](https://docs.cloud.google.com/storage/docs/encryption)

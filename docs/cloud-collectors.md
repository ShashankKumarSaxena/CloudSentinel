# Read-only cloud collection

Production collection requires operator-approved accounts in the read-only JSON
registry. Startup/status checks do not contact clouds. An analyst selects an
approved connection and region; a dedicated worker acquires credentials, collects
bounded evidence, and records coverage. There is no key/token form in the UI.
No cloud resources, IAM bindings, or policies are modified by the application.

## Approval and identity

Copy `config/accounts.example.json` to ignored `config/accounts.local.json`.
Examples are disabled. Configure an explicit unique connection ID, provider,
account, regions, credential method, and enabled flag. The registry allows up to
500 accounts and rejects unknown fields/duplicate IDs. API and worker re-read it
for submissions/execution; edit it with an operator-controlled process and verify
both containers see the same version. If a host-side atomic file replacement
leaves an old Docker bind mount, recreate both containers to apply it.

| Provider | Production identity | Scope |
| --- | --- | --- |
| AWS | boto3 default workload chain, or AssumeRole with exact account ARN and required external ID | Explicit region plus global IAM user observations |
| Azure | Explicit ManagedIdentityCredential or WorkloadIdentityCredential; tenant/client IDs for federation | Subscription-wide; `regions: ["global"]` |
| GCP | Workload identity/ADC, optionally impersonating a service account | Project-wide; `regions: ["global"]` |

AWS verifies the account using STS. Assumed roles request 900-second credentials;
the source identity needs permission to assume the target role. Bind its trust
policy to the source principal and unique external ID. Review the
[AWS external-ID guidance](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_common-scenarios_third-party.html).

Azure uses provider-supported refreshable credentials chosen explicitly, without
a production fallback to the developer CLI. System-assigned identity is suitable
on a configured Azure host; federation requires a rotated local subject-token
file and matching identity trust. See
[Azure managed identity](https://learn.microsoft.com/en-us/azure/developer/python/sdk/authentication/system-assigned-managed-identity).

GCP uses refreshable ADC/federation and can request short-lived impersonated
credentials. Private service-account keys and developer authorized-user
credentials are rejected on the approved path. External-account configurations
and rotating subject tokens must be mounted only on the worker. See
[application default credentials](https://docs.cloud.google.com/docs/authentication/application-default-credentials)
and [workload identity federation](https://docs.cloud.google.com/iam/docs/workload-identity-federation).

`deploy/production/` contains worker-only federation mount examples. The operator
or platform must issue and rotate tokens; Compose and CloudSentinel do not do so.
The worker closes SDK clients/transports after a collection. Credential or provider
exceptions become safe errors rather than token-bearing response text.

## Permissions

Start with `config/policies/aws-readonly.json`, `aws-trust.example.json`,
`azure-readonly.example.json`, and `gcp-readonly.yaml`. These are reviewable
starting templates, not policies automatically installed by the app. Restrict
principal/resource/subscription/project scopes and test the supported reads with
your cloud administrator. Some list APIs require wildcard resource scope. GCP
private Data Access logs may require additional explicit permissions.

AWS reads identity, S3 public-access/encryption metadata, EC2 security groups,
IAM users/MFA, and CloudTrail trail status/management history. Azure reads storage
accounts/containers, network security groups, and Activity Log. GCP reads bucket
list/IAM, firewall rules, and visible audit-log entries. None provides exhaustive
effective-permission evaluation or complete organization-wide activity coverage.

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

Limits are 1,000 resources, 10,000 events, 30 pages per listing, and a 1–168-hour
lookback. The collection budget is approximately two minutes plus an in-flight
request; network requests/retries and response sizes are bounded. REST responses
are capped at 8 MB. Repeated pagination links/tokens and unexpected HTTPS
hosts/redirects are rejected. A stuck dedicated worker exits after its heartbeat
watchdog expires; interrupted job recovery is bounded.

Unavailable scopes are saved as partial coverage. No supported resources means
the collection fails and the previous valid account snapshot is preserved.
Resources/events are checked against the approved account/provider before commit.
Do not interpret a partial scan, missing activity, or an unknown check as safe.
Real provider permissions/identity/network behavior still require local validation;
current provider mapping evidence uses SDK stubs and mocked responses.

## Local collector development

Demo mode is offline by default. Legacy CLI/token-file adapters remain for
explicit local development and mapping tests. To test approved jobs locally,
configure a registry and deliberately set `CLOUDSENTINEL_ALLOW_LIVE_IN_DEMO=1`.
The old synchronous `/scans/collect` route is demo-only; production directs
clients to `/cloud/jobs`. Avoid using the demo workspace for organization evidence.

## API references

- [AWS CloudTrail lookup](https://docs.aws.amazon.com/boto3/latest/reference/services/cloudtrail/client/lookup_events.html)
- [AWS S3 bucket pagination](https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/list_buckets.html)
- [Azure blob containers](https://learn.microsoft.com/en-us/rest/api/storagerp/blob-containers/list?view=rest-storagerp-2024-01-01)
- [Azure Activity Log](https://learn.microsoft.com/en-us/rest/api/monitor/activity-logs/list?view=rest-monitor-2015-04-01)
- [GCP audit log entries](https://docs.cloud.google.com/logging/docs/reference/v2/rest/v2/entries/list)
- [GCP firewalls](https://docs.cloud.google.com/compute/docs/reference/rest/v1/firewalls/list)
- [GCP public access prevention](https://docs.cloud.google.com/storage/docs/public-access-prevention)
- [GCP encryption](https://docs.cloud.google.com/storage/docs/encryption)

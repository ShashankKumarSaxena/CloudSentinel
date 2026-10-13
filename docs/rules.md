# Configuration baseline

The baseline is a project-defined set of six explainable checks on normalized
snapshot assertions. It does not evaluate full IAM, network, or storage policy
semantics, and it is not a compliance scanner. Severity indicates prioritization
within this prototype rather than a standardized vulnerability score.

| Rule | Failure condition | Severity | Required configuration |
| --- | --- | --- | --- |
| STO-001 | Effective anonymous storage access is true | Critical | `public_access` |
| STO-002 | Encryption at rest is false | Medium | `encrypted` |
| IAM-001 | A normalized permission marker contains `*` | High | `permissions` |
| IAM-002 | Privileged human identity is admin and MFA is false | High | `admin`, `mfa_enabled` |
| NET-001 | World CIDR (`0.0.0.0/0` or `::/0`) with port 22, 3389, or all ports | High | `ingress_cidrs`, `ports` |
| LOG-001 | Account audit logging is false | Medium | `logging_enabled` |

Missing required fields yield unknown. For an identity explicitly marked
`admin: false`, IAM-002 passes regardless of its MFA field because this rule
targets privileged humans. Secure HTTPS ingress alone does not fail NET-001.
All findings include the exact checked configuration fields as evidence.

## Interpretation limits

Public storage may be intentionally public. A wildcard policy may be bounded by
conditions or deny policies not represented in the simplified schema. Logging
may be configured at an organization scope the current collectors cannot fully evaluate.
Encryption defaults and identity enforcement differ between providers. Imported
flags must describe effective behavior, not simply one raw API setting.

Review findings in context. The project does not claim false-positive reduction
or cloud-wide coverage. Phase 2 adds provider collectors and an activity model
with separate evidence and measured evaluation. See `docs/cloud-collectors.md`
for mapping limits and `docs/model.md` for model evaluation.

## Reference material

The public-storage check and guidance follow the general direction of
[Amazon S3 security best practices](https://docs.aws.amazon.com/AmazonS3/latest/userguide/security-best-practices.html),
[Azure guidance for preventing anonymous blob access](https://learn.microsoft.com/en-us/azure/storage/blobs/anonymous-read-access-prevent),
and [Google Cloud Storage public access prevention](https://docs.cloud.google.com/storage/docs/public-access-prevention).
These references support the security rationale; this prototype does not claim
an exact implementation of provider controls or their certification standards.

The frontend runtime requirement follows the
[Vite 8 getting started guide](https://v8.vite.dev/guide/).

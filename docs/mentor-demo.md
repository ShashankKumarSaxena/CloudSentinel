# Mentor demonstration

We have completed the Phase 1 configuration prototype of the proposed
multi-cloud vulnerability detector. The demonstration shows a functioning data
pipeline and dashboard using labeled synthetic inventory. The final ML-based
system is the project direction; the current engine uses explainable rules.

## Prepare before the meeting

Run `bash scripts/setup.sh` once, then `bash scripts/demo.sh`. Open
http://127.0.0.1:8000 and run `make smoke` in another terminal. Internet is not
needed after dependencies are installed. Keep the server terminal open.

If you previously imported a different inventory, click Run demo scan. Review
finding dispositions; use the Open control to reopen any findings you intend to
show. Running another scan preserves dispositions deliberately.

## Suggested five-minute walkthrough

| Time | Action | Explanation |
| --- | --- | --- |
| 0:00–0:45 | Open Overview | Different cloud security models need one common view. The prototype shows synthetic inventory from three providers. |
| 0:45–1:30 | Run demo scan | The backend evaluates 18 resources with 30 applicable checks and persists a scan. Counts and severity come from actual rule output. |
| 1:30–2:30 | Inspect a critical finding | Show the public-access field, affected resource, severity, and remediation. Explain that configuration evidence makes the finding reviewable. |
| 2:30–3:00 | Acknowledge the finding | Show durable team triage and its audit trail. This records review; it does not change cloud infrastructure or the baseline score. |
| 3:00–3:45 | Inspect Cloud inventory and Scan history | Show one normalized resource and its check results, then show the saved snapshot. |
| 3:45–4:15 | Export report | Download the JSON report containing provenance, evidence, findings, and current triage status. |
| 4:15–5:00 | Open Project brief | Show delivered scope, architecture, and the proposed next step: live collectors and evaluated ML anomaly detection. |

## Evidence to show

The unchanged abstract is in the repository root. `docs/phase-1.md` maps the
abstract to this phase. `docs/architecture.md` explains the pipeline.
`docs/validation.md` records verification results. The backend test suite checks
unsafe and safe configurations, incomplete data, invalid inputs, persistence,
and the API flow.

## Likely mentor questions

**Where is the AI?** It is proposed for the next phase. We first established the
normalization, storage, UI, and explainable baseline necessary to evaluate an
anomaly model honestly. We have not claimed ML accuracy or reduced false positives.

**Is this connected to real AWS, Azure, and GCP accounts?** No. Phase 1 runs on
synthetic or imported snapshots. Real API collection and credential management
are planned separately.

**What does 47% mean?** Fourteen of 30 evaluated baseline checks pass; the rounded
pass rate is 47%. Unknown checks are excluded and reported separately. This is
not a compliance certification or probability of a breach.

**Does marking a finding resolved fix it?** No. It records a team disposition.
Scan evidence and the score remain unchanged. A future collector can verify
actual configuration changes.

**What happens if the configuration data is incomplete?** Missing fields produce
unknown checks. The system never silently treats them as safe.

**What comes next?** Review the normalized schema with the mentor, implement
read-only cloud collectors, collect activity features, and evaluate an anomaly
model against labeled scenarios and the existing rule baseline.

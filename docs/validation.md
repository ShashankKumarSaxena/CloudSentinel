# Phase 2 validation evidence

The Phase 2 backend, collectors, model pipeline, and dashboard pass automated
checks. Cloud access was validated with synthetic data and mocked API responses
as requested; no live-account scan is claimed. Phase 1 behavior remains covered.

## Verified results

| Check | Result | Evidence |
| --- | --- | --- |
| Backend/API/model/provider suite | Passed | 53 tests using temporary SQLite databases, local models, ASGI transport, AWS SDK Stubber, and mocked REST clients |
| TypeScript | Passed | `npm --prefix frontend run check` |
| Production frontend | Passed | `npm --prefix frontend run build` |
| Synthetic combined scan | Passed | 18 resources; 30 configuration checks; 330 events; six activity windows; 16 rule findings and three ML findings |
| Model training/evaluation | Passed | 600 fitting rows, 200 calibration rows, 480 holdout rows; persisted model and evaluation report |
| Configuration compatibility | Passed | Existing rules, missing-field semantics, persistence, and configuration-only import tests |
| Provider mapping | Passed with mocks | AWS regional storage/security-group/event mapping; Azure container/activity mapping; GCP permission-failure handling |
| API workflows | Passed | Demo/import, training/retraining, source labels, collection metadata, reports, and failed-operation preservation |
| Bounded transport | Passed | Repeated page tokens and unexpected credential destinations rejected |

The model evaluation is synthetic and reports its limitations: 78.95% precision,
25% recall, 2.22% false-positive rate, and 90 missed anomalies out of 120. The fixed
activity comparator has higher recall on this holdout. No real-world advantage
or accuracy improvement is claimed.

## Meaningful test coverage

- UTC hourly aggregation separates accounts and principals.
- Missing activity features and tiny windows are not scored.
- IDs/feature rows cannot leak between train, calibration, and evaluation.
- Threshold calibration is checked independently of evaluation labels.
- Model artifacts reload with identical scores; malformed pointers are not loaded.
- Demo normal windows remain normal; all three unusual windows generate ML findings.
- Old configuration-only JSON remains valid and missing flags stay unknown.
- AWS mock responses are validated against the actual SDK service models.
- CIDR/port pairs remain attached to individual ingress rules.
- Permission failures produce unknown values and explicit partial coverage.
- Collection errors do not disclose provider secrets or replace valid snapshots.
- Status checks do not call cloud APIs or return credentials.
- Reports and immutable snapshots include the model version and distinct methods.
- Legacy Phase 1 rows read compatibly without rewriting their stored evidence.
- Concurrent scan and training requests return 409 while collection is active.
- Batched scoring preserves individual-window results.

## Verification limits

The shell environment previously blocked registry access and localhost sockets.
The required Python libraries and frontend dependencies were available locally,
so training, tests, and builds were executed without new registry access. API
checks use real in-process routing/middleware/persistence rather than live ports.

Automated browser connection tools failed during Phase 1. Its original overview
was user-confirmed. The new Phase 2 pages have build/type checks but do not yet
have screenshot, mobile viewport, console, or browser click-through verification.
No new user display confirmation is assumed.

Azure/gcloud CLIs and cloud accounts are not configured here. Their REST mapping
and failure behavior were tested with mocks. The real credential chain, provider
permissions, account-specific coverage, and network behavior need a configured
account to verify end to end.

Git is now initialized and an origin is configured. Phase 2 changes are left
for review; this session did not commit, push, deploy, or execute hosted CI.

## Manual runtime checklist

- [ ] Install updated requirements and restart the local server.
- [ ] Run demo scan to create a Phase 2 snapshot while retaining older scans.
- [ ] Open Activity analysis and inspect normal, anomaly, and feature evidence.
- [ ] Open Model lab and compare model/comparator metrics and scenario misses.
- [ ] Retrain the synthetic model and run another scan to see its new version.
- [ ] Import configuration-only and activity inventories.
- [ ] Inspect and triage an ML finding; verify its status survives reopening.
- [ ] Export a report and verify source, method, model, and coverage fields.
- [ ] Test navigation, dialogs, and filters at a narrow viewport.
- [ ] Run `make smoke` against the running local server.

Live collection is optional and must be initiated from a configured local account.

# Phase 1 validation evidence

The implementation passes its backend and API tests, TypeScript checking, and
production build. The user started the production demo server from a normal
terminal and confirmed that the overview displays correctly with the green
sidebar and 18 resources. Automated browser interaction remains unverified
because the available browser and desktop connection tools failed to initialize.

## Verified checks

| Check | Result | Evidence |
| --- | --- | --- |
| Backend and API suite | Passed | 25 tests using temporary SQLite databases and in-process ASGI requests, including static dashboard serving after the frontend build |
| TypeScript | Passed | `npm --prefix frontend run check` |
| Production dashboard | Passed | `npm --prefix frontend run build` produces HTML, CSS, and JavaScript |
| Clean dependency install | Passed on this Mac | `npm ci` succeeded using an isolated cache populated from already cached package tarballs |
| Shell and Python syntax | Passed | `bash -n` for setup/demo/dev/Git scripts; Python compilation |
| Shipped baseline | Passed | 18 resources; 30 checks; 14 pass; 16 fail; 0 unknown; 47% posture |
| Provider coverage | Passed | All three providers evaluated by the same schema and applicable rules |
| Validation and atomic import | Passed | Invalid input rejected without replacing the latest valid scan |
| Persistence and triage | Passed | Reopening the store preserves scans and statuses; evidence and score remain fixed |
| Browser display | User-confirmed | User reported that http://127.0.0.1:8000 displays the overview correctly |

## Important test scenarios

- Safe configurations produce no findings and a 100% baseline pass rate.
- Missing required fields produce unknown and cannot inflate passed-check counts.
- All-unknown inventories produce a null score.
- IPv6 world access and all-port ingress detect exposed management access.
- HTTPS-only public ingress does not fail the management-port rule.
- Privileged humans without MFA are detected; non-admin workload identities are
  not incorrectly subjected to a human MFA requirement.
- Finding IDs are deterministic and distinct across providers.
- Duplicate IDs, invalid CIDRs and ports, string booleans, extra fields,
  malformed JSON, unsupported versions, and oversized imports are rejected.
- Cross-origin writes and untrusted host headers are rejected.
- First startup seeds one demo scan; subsequent startups do not add another seed.
- Scan, triage, audit-event, report export, and historical retrieval flows work.

## Session limits and honest status

This session could not access the npm registry or bind/connect to local service
ports from shell tools. Cached dependencies enabled installation, type checking,
and builds without registry access. In-process ASGI tests exercised real routing,
validation, middleware, SQLite, and static-file responses without opening ports.

The Browser runtime failed during initialization, and the desktop fallback also
required unavailable service configuration. No automated screenshot, mobile
viewport, browser console, or click-through verification is claimed. The user's
display confirmation is recorded separately from automated verification.

Writing `.git` is prohibited by this workspace's permission profile, so `git init`
failed. A normal-terminal initialization script is included. The GitHub CLI token
was invalid and the user chose to connect GitHub later. No commit, remote push,
hosted deployment, or executed GitHub Actions result is claimed.

## Manual verification checklist

- [x] Production overview displays on the user's machine.
- [ ] Run a demo scan and see a new row in Scan history.
- [ ] Filter findings by provider and severity; clear filters.
- [ ] Open a finding, inspect evidence, acknowledge it, and reopen it.
- [ ] Confirm dialog Escape and Tab behavior in the browser.
- [ ] Inspect a resource and a historical scan.
- [ ] Export a JSON report and verify its source label.
- [ ] Import an inventory and verify the source changes to Imported snapshot.
- [ ] Restore the bundled dataset with Run demo scan.
- [ ] Check the navigation on a narrow/mobile viewport.
- [ ] Run `make smoke` against the already running production demo.
- [ ] Initialize Git locally and connect GitHub when ready.

These checklist items cover runtime behavior and usability. The implementation
and automated tests are complete for Phase 1.

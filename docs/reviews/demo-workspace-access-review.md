# Independent review: opt-in synthetic demo workspace access

21 October 2026. Reviewer: independent `review_plan_offset` worker; author of none of the reviewed implementation paths.

**Accepted for the bounded development repair after three independently reproduced findings were fixed and rechecked. No actionable findings remain against the final frozen candidate.** This accepts integration of the demo provisioning repair, not production deployment or completion of the product's 40 features.

## Exact reviewed candidate

Base: `bc32b1dbc3239e065708e4f5fcd20fc7639c66e7`, branch `codex/demo-workspace-access`, plus these final frozen files:

| Path | SHA-256 |
| --- | --- |
| `backend/spesped/cli.py` | `a8588abad4e98eb86513235a23fd9184ece1e9f93bfb4077e3391b2e62f82ce7` |
| `backend/spesped/demo_access.py` | `ce1453732301fce374a14813a8e3e53885a7faa210a998992d120d441edafee8` |
| `backend/tests/test_demo_workspace_access.py` | `f67aa6eaedaf1fabada7fde6cd6efc7fa87d05fb8cf49530966b27bdd02c6bf0` |

Extracted the base using Git archive into `var/review-demo-workspace-access/archive`, then copied only those three frozen files after verifying their hashes. Rechecked both archive and current candidate hashes after independent execution. Used Python 3.12.13 and absolute archive `backend:backend/tests` PYTHONPATH entries. Read the repository's AGENTS.md and docs/10 policy and inspected the native CLI, authorization, identity audit/outbox, support-case service and router contracts. No implementation edits, commits or pushes were made by this reviewer.

## Behavior and boundaries

The CLI adds `spesped demo-access --confirm-synthetic`, calling `upgrade_demo_access(db, *, environment, confirm_synthetic)` inside a caller-owned transaction. It requires the literal development environment and explicit synthetic confirmation before database work. The original demo/bootstrap implementation remains unchanged. The helper neither requests nor changes passwords and does not delete or reset records.

Preflight verifies the exact built-in two-school, six-account, three-pupil fixture, original memberships/enrollments/teaching assignments, creation timing, bootstrap audit records, unique synthetic-fixture provenance and effective baseline leader grants. Changed, incomplete, inactive or replaced fixture identities are refused. Pending staged caller changes are rejected. Existing domain work is allowed without relaxing the identity fingerprint.

The initial intact fixture receives 63 grants: 26 explicit practitioner actions for each of A/B, school `evidence.intake`, and five exact case actions for each of two native synthetic educational cases. Only the original first-school leader receives them. Each inserted grant has audit and identity-outbox evidence; native case creation retains its own audit/outbox/receipt behavior. Upgrade and case markers preserve recheck identity. The surrounding transaction rolls back grants, cases and their audit/outbox effects on an injected late failure.

Other-school C, teacher, assistant, guardian and technical accounts retain their prior scope. Protected or otherwise unrelated cases are excluded. Native source, decision, qualification, template, AI-processing, recipient and disclosure checks remain authoritative. No provider, guardian relationship, dispatch/disclosure permission or protected-case grant is created.

A later native educational case created by the demo leader still initially lacks independent case-read rights. Explicitly rerunning the helper can provision only an eligible A/B case with matching leader ownership and native creation provenance. Runtime creation does not gain an implicit authorization bypass. The root-owned Norwegian guide now explains this rerun step.

## Findings and independent closure

The early unfrozen implementation had three reproducible issues, reported promptly to the orchestrator and author:

1. **Inactive covering authority could be restored through narrower grants.** A revoked or expired school-wide `documents.read` grant was ignored by exact-scope matching; the upgrade then granted A/B access. Four reviewer SQLite/PostgreSQL cases reproduced it. Final preflight refuses an inactive overlapping grant before mutation. All four independent adverse cases now pass, and unchanged counts are asserted after refusal.
2. **Concurrent SQLite upgrades could duplicate grants.** SQLite ignored `SELECT FOR UPDATE`. Synchronizing two clean callers immediately before their first grant flush produced two successful results of 63 added grants. The final helper reserves the SQLite writer with `BEGIN IMMEDIATE` before provenance reads and refuses an already active SQLite transaction. The final reviewer probe holds the first caller inside preflight and confirms a second caller cannot enter preflight until release, then verifies results 0/63 and no duplicate grant coordinates. The author concurrency case also passes on both dialects. PostgreSQL retains school-row serialization.
3. **A clean retained Session could hide persisted revocation.** A cached active baseline grant survived an external committed revocation and passed preflight. Reviewer SQLite/PostgreSQL cases reproduced success where refusal was required. Final code expires clean cached identities before inspection; both independent cases now refuse. The frozen suite additionally checks cached membership and previously provisioned-grant revocations.

Pre-fix evidence remains in `var/review-demo-workspace-access/early-adverse.txt`, `early-cache.txt` and `test_early_adverse.py`. The pre-fix two-writer barrier is intentionally replaced in the final probe: correct serialization prevents two callers reaching their first write together. Final code also records provisioned-case markers and refuses moving/removing previous case scope, rather than interpreting that mutation as permission to replenish it.

## Independent execution

Command run from the frozen archive:

```sh
SPESPED_TEST_POSTGRES_URL='postgresql+psycopg://spesped_test:synthetic-development-only@127.0.0.1:55432/spesped_test' \
PYTHONPATH='/Users/lauritz/Programming/SpesPed/var/review-demo-workspace-access/archive/backend:/Users/lauritz/Programming/SpesPed/var/review-demo-workspace-access/archive/backend/tests' \
/Users/lauritz/Programming/SpesPed/backend/.venv/bin/python -m pytest \
  backend/tests/test_demo_workspace_access.py backend/tests/test_foundation.py \
  /Users/lauritz/Programming/SpesPed/var/review-demo-workspace-access/test_final_adverse.py \
  -q --junitxml=/Users/lauritz/Programming/SpesPed/var/review-demo-workspace-access/final.xml
```

**Result: 104 passed, four expected skips, two existing warnings in 118.03 seconds.** Breakdown:

- All 57 frozen demo-access cases passed: native before/after workspace reads, evidence/profile/plan/teaching/case/decision/document commands, scope preservation, fixture refusal, explicit confirmation/environment checks, CLI password preservation, atomic rollback, sequential/concurrent idempotence, fresh-case rerun, expired/revoked/removed/moved scope, and cached-revocation checks.
- Foundation: 40 passed; three SQLite-only PostgreSQL concurrency probes skipped, with their actual PostgreSQL variants executed.
- Reviewer adverse probes: seven passed; one PostgreSQL skip for the SQLite-specific reservation schedule.

Evidence: `var/review-demo-workspace-access/{frozen-hashes.json,final.txt,final.xml,test_final_adverse.py}`. Existing dependency/schema warnings remain visible in the log. `git diff --check` passed. PostgreSQL tests used isolated UUID schemas with fixture-owned cleanup. Existing demo databases, unrelated schemas, running servers and other agents' files were not modified by this reviewer.

## Root-owned CLI/browser corroboration

Inspected `var/demo-access-browser/final-cli.json`: all three hashes match the reviewed candidate; frozen CLI reruns report zero added grants; password hashes are unchanged. The first frozen run adds two new case audit/outbox markers to the earlier successful browser fixture, and the second has identical recorded counts. This is distinct from a fresh upgrade, which the independent native tests exercise.

Inspected root browser evidence: `before.json` completed 22 steps with 40 HTTP 403s and no JavaScript errors; the final `after.json` completed 24 steps, including both A/B educational case opens, with zero HTTP 403s and zero JavaScript errors. Root reports the actual compiled frontend and native `create_app` were used without mocked permissions or routes; `final-browser.txt` records the repeat. Browser execution and backend/README.md plus docs/11-local-development.no.md updates remain root-owned verification. This reviewer did not run or modify that browser/server fixture.

## Remaining limits

The command intentionally refuses nonstandard or damaged identity fixtures and withdrawn scope; it is not a general access-management or data-repair tool. SQLite callers must use a fresh transaction. New native cases require another explicit helper invocation for exact case access. Unconfigured AI, scanning, professional qualifications, reviewed legal/template requirements, guardian relationships and disclosure remain separate visible gates. A functioning synthetic development workspace does not establish production readiness or whole-feature acceptance.

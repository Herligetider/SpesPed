# J05 independent backend review

Reviewed 21 October 2026. Candidate: **ac4eea27bdbb38421fe48465269d950f4d37d634**. Verdict: **changes required** for the bounded manual backend candidate. Three findings below remain open. This is not acceptance of full J05/F08.

## Scope and isolation

Reviewed all 14 candidate files: `backend/spesped/contexts/entitlements/**`, `backend/spesped/contexts/plans/**`, `backend/migrations/versions/j05_plans.py`, `backend/tests/test_plans.py`, and `backend/tests/plans_fixtures.py`. Read `AGENTS.md`, the full F02/F07/F08 entries in `docs/features.json`, `docs/04-domain-model.en.md`, and `docs/09-domain-implementation.en.md`.

All line references below identify the exact candidate, archived at `/Users/lauritz/Programming/SpesPed/var/review-j05/pinned`. The shared checkout contains unrelated, evolving J04/platform/assembly and other agent changes; those were neither reviewed as this candidate nor modified. The archive has the accepted prior J04 core and **no** `j04_structuring.py`. Tests explicitly upgraded `j05_plans`; the fixture's conditional parallel migration did not execute. Python import paths for `spesped`, `entitlements.service`, and `plans.service` were printed and verified under the archive, overriding the virtual environment's shared-tree editable installation.

Only this review is a tracked reviewer change. Supplemental probes and logs are under ignored `var/review-j05/`. No implementation edits, commits, pushes, or subagents were used.

## Open findings

### J05-R1 — P1: Source-bound review and clarification prose escapes current-source filtering

**Locations:** `backend/spesped/contexts/plans/service.py:103-104`; `backend/spesped/contexts/plans/router.py:138-145`; `backend/spesped/contexts/entitlements/service.py:327-329`; `backend/spesped/contexts/entitlements/router.py:239-253`.

The source filtering on primary content is incomplete across auxiliary prose and retry responses:

1. Confirm a sourced profile statement with sensitive source details in its review reason. Correct its evidence association from pupil A to pupil B using the public evidence-correction endpoint. Sign in as an A-only teacher who cannot read B's evidence. The normal profile correctly nulls statement content and source, but still returns the full `review_reason`. The statement `/history` endpoint independently returns the full `ProfileReview.reason` with HTTP 200. The teacher did not author this reason, and direct evidence retrieval returns 403.
2. Create a sourced case clarification, then remove the actor's `evidence.read`/`evidence.write` assignments while preserving current case permissions. GET clarifications correctly nulls its description/source. Replaying the original creation POST returns HTTP 201 with the complete raw description/source because the replay exits before `source_binding`, and the router uses unfiltered `row_view`.
3. Resolve a sourced clarification with details from its original evidence. After the same evidence-access removal, GET clarifications nulls description/source and reports `review_required`, but still returns the full `resolution` prose.

**Independent evidence:** `test_profile_history_does_not_release_review_prose_after_source_access_loss`, `test_clarification_retry_does_not_release_source_after_evidence_access_loss`, and `test_clarification_resolution_does_not_release_prose_after_source_access_loss` in `var/review-j05/test_review_probes.py`. All reproduced on SQLite and PostgreSQL. The stronger public wrong-pupil correction reproduction, including the leaked normal-profile `review_reason`, is preserved in `var/review-j05/probe-profile-reassignment.log`.

**Impact:** Source correction or access revocation does not reliably retract derivative pupil prose. An A-only teacher can retrieve review details whose source has been corrected to B; retries and resolved-issue views also bypass the filtering used elsewhere. This violates the current-source and pupil-scope retrieval boundaries. Apply a common authorized projection to all affected response paths, including all free-text fields and replays; preserve history internally without granting unrelated source access.

### J05-R2 — P2: Successful replay skips the command's current signing authority

**Locations:** `backend/spesped/contexts/plans/service.py:253-267`; `backend/spesped/contexts/entitlements/service.py:260-265`. The same ordering exists for actual referral submission in `entitlements/service.py:162-175`.

Approve a plan, retaining the exact command and request key. Revoke that actor's `plans.approve` grant while preserving `plans.write`/`plans.read`. Replaying the successful approval returns HTTP 200 and approved content because `lifecycle` returns at line 258 before `require_authority` at line 267. Similarly, confirming a decision, revoking `education_decision.confirm`, and replaying the confirmation returns HTTP 200: the replay exit at line 263 precedes the specialized check at line 265. Both were independently reproduced on both databases. The referral submission variant is identified by inspection, not claimed as a separate executed probe.

**Independent evidence:** `test_approval_replay_rechecks_revoked_signing_authority` and `test_decision_confirmation_replay_rechecks_revoked_authority`; results in `var/review-j05/probes-final.log`.

**Impact:** A request key becomes a way to obtain successful approval/confirmation responses after the actor loses permission to perform that action. The database does not create a second approval, but the command boundary no longer honors current authorization, contrary to the explicit retry requirement. Recheck the operation's specialized authority before returning a replay; apply the same rule to submission and other commands with checks below their replay exit. Keep valid historical approvals intact.

### J05-R3 — P2: Concurrent revision and lifecycle commands take locks in opposite order

**Locations:** `backend/spesped/contexts/plans/service.py:189-197` and `253-255`; error handling in `backend/spesped/contexts/entitlements/common.py:25-40`.

`save_plan` locks the pupil before locking the plan. `lifecycle` locks the plan before locking the pupil. Two concurrent requests can therefore form a database deadlock: review holds the plan and waits for the pupil; revision holds the pupil and waits for the plan. The PostgreSQL probe coordinates only these existing lock boundaries, without modifying implementation code. One transaction commits and the other raises raw `sqlalchemy.exc.OperationalError` wrapping `psycopg.errors.DeadlockDetected`. `mutate` rolls it back but reraises it; there is no translation to a safe retry conflict.

**Independent evidence:** `test_postgres_revise_and_review_have_consistent_lock_order`; actual deadlock output in `var/review-j05/probes-extra.log` and `var/review-j05/probes-final.log`. SQLite is deliberately skipped for this probe.

**Impact:** Normal simultaneous editing/review produces an internal server error and no defined retry response. Use one lock order for these operations, including replacement activation, and translate relevant PostgreSQL retryable transaction failures to the documented safe conflict/retry behavior. Preserve the existing rollback guarantee.

## Verification evidence

Archive preparation from `/Users/lauritz/Programming/SpesPed`:

```sh
mkdir -p var/review-j05/pinned
git archive ac4eea27bdbb38421fe48465269d950f4d37d634 | tar -x -C var/review-j05/pinned
```

Supplied candidate tests, run from the archive:

```sh
PYTHONPATH=/Users/lauritz/Programming/SpesPed/var/review-j05/pinned/backend \
SPESPED_TEST_POSTGRES_URL=postgresql+psycopg://spesped_test:synthetic-development-only@127.0.0.1:55432/spesped_test \
/Users/lauritz/Programming/SpesPed/backend/.venv/bin/python -m pytest backend/tests/test_plans.py -q
```

**Result:** 33 passed, 1 skipped in 34.07 seconds. The skip is the PostgreSQL-only contention test's SQLite parameter. PostgreSQL parameter ran successfully. The fixture uses unique `j05_<uuid>` schemas with teardown and forbids `spesped_demo`.

Supplemental probes, run from the shared repository but importing only the archive:

```sh
PYTHONPATH=/Users/lauritz/Programming/SpesPed/var/review-j05/pinned/backend:/Users/lauritz/Programming/SpesPed/var/review-j05/pinned/backend/tests \
SPESPED_TEST_POSTGRES_URL=postgresql+psycopg://spesped_test:synthetic-development-only@127.0.0.1:55432/spesped_test \
backend/.venv/bin/python -m pytest var/review-j05/test_review_probes.py -q --tb=short
```

**Result:** `probes-final.log`: 11 failures demonstrating the findings, 6 passes, 1 PostgreSQL-probe SQLite skip, 16.97 seconds. The profile-history probe was subsequently strengthened to use public wrong-pupil reassignment and an independent A-only teacher; its isolated rerun reproduced 2 failures (one per database), with output in `probe-profile-reassignment.log`. Probe assertions describe the desired protected behavior, so these failures are intentional review evidence, not a claim that the implementation tests pass.

The 6 passing supplemental cases establish, on both databases:

- A teacher limited to pupil A is denied an IEP whose sole decision source is reassigned to pupil B. The suspected indirect cross-pupil plan-content leak was **not** reproduced and is not a finding.
- A newly uploaded original-source revision, without changing the existing confirmed evidence revision, hides the full profile/plan content, blocks pending approval with `source_changed`, and suppresses the assistant brief. The assistant remains unable to read evidence.
- A deliberately injected late command failure rolls back plan/goal/revision rows, command receipt, audit and outbox together.

The supplied full-workflow tests additionally exercise sourced profile categories, dispute/replacement/history and minimal assistant output; independent case creation versus dossier permissions; educational consent versus processing ground and disclosure permission/revocation; actual referral review, submission record, receipt and planned follow-up without transmission; separate expert recommendations and typed ITO/assistance/physical provisions; exact decision/provision references and quantity separation; authored/imported IEP provenance; stable goal hierarchy, contributions/disagreement, exact approval and dated replacement; immutable historical goals; decision-change impacts; cross-school/pupil checks, stale versions, deduplication, migration downgrade/upgrade and PostgreSQL retry contention. Those checks passed in the immutable archive. They do not cover the adverse paths identified above.

After probe teardown, a read-only query confirmed database `spesped_test` and zero remaining `j05_%` schemas. No demo database or external service was used. The only warning was the existing FastAPI/Starlette test-client deprecation.

## Boundaries and remaining required work

The brief's direct evidence metadata queries (`plans/service.py:91-96`) and newest-source check (`entitlements/common.py:70-72`) work for the exercised correction/revision cases without granting the assistant `evidence.read`. Public evidence-port encapsulation remains an architecture concern under the domain contract, not an independently reproduced authorization defect. Do not widen permissions to hide that coupling.

The candidate is a manual backend slice. Actual AI-generated IEP/goals and proposal review/apply are absent and remain required J05/F08 follow-on work. Root-owned application/model/goal-validator registration is outside this candidate; the fixtures explicitly install the routers and validator. Full J07 UI, J06 downstream consumers, J18 external connectors, and real transmission are separate work. The ordinary referral endpoint records an actual externally performed contact with proof/reference; it does not send it.

Synthetic fixtures and protocol behavior do not establish school-specific legal correctness, practitioner acceptance, external-system readiness, or production readiness. The September legal register was not reverified in this review. Repair J05-R1–R3 and pin the repair for independent recheck before accepting this manual slice; acceptance must not mark all J05/F08 complete.

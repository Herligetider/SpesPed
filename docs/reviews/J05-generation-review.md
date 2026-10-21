# J05 generated IEP consumer — independent review

Reviewed 21 October 2026. Exact candidate: **2ccc30e499d87efba020068528c70f7e5a382a9a**. **Verdict: changes required.** Two metadata-contract findings remain open. This report concerns the generated IEP consumer; it does not replace the accepted manual-core history in `J05-review.md`.

## Scope and isolation

Reviewed the nine candidate files: plans `generation.py`, `models.py`, `projections.py`, `router.py`, `schemas.py`, `service.py`; forward `j05_plan_generation.py` migration; `plan_generation_fixtures.py`; and `test_plan_generation.py`. Read relevant gateway/runtime source ports to assess the consumer integration. Root's typed gateway implementation and runtime-binding review remain separate. Uncommitted teaching repairs, main registration and joined tests in the shared checkout were excluded.

Archived the exact commit at `/Users/lauritz/Programming/SpesPed/var/review-j05-generation/pinned`. Printed and verified resolved imports for `spesped`, `plan_generation_fixtures`, `plans.generation` and `plans.projections`, all inside this archive. Every test explicitly used absolute archive backend/tests paths in `PYTHONPATH` to override the shared virtual environment's editable installation. Only this new report and ignored probes/logs were written; no production edits, commits, pushes or subagents.

The scope was explicitly extended by the root reviewer to include the complete directly used `goal_binding_is_current` path, because its behavior can defeat the newly added generated-lineage guard. The inherited location is identified below; this is not a broad reopening of unrelated teaching work or the earlier manual-core acceptance.

## Findings

### J05-GEN-R1 — P2: Full generated-goal metadata check flushes pending caller changes before reaching its guard

**Exact-pin location:** `backend/spesped/contexts/plans/projections.py:28-38`, specifically the ORM queries beginning at line 32. The outer queries predate this consumer; the new lineage call at lines 37–38 makes the unsafe outer path part of the generated-goal integration.

Independent reproduction on SQLite and PostgreSQL:

1. Generate a proposal, explicitly apply its existing-goal suggestion, and activate the resulting revision through separate human review/approval/activation.
2. Obtain its authorized `teaching_goal_basis` and verify the metadata predicate is initially true.
3. In a caller-owned session, load the selected `ExpertAssessment` and stage `state = 'disputed'`, without flushing.
4. Attach a `before_flush` observer and invoke `goal_binding_is_current`.

Observed on both databases: the predicate returns **False**, but a flush has already occurred (`before_flush` count **1**) and the assessment is **no longer dirty**. The first ORM query triggers autoflush before `generation_bindings_are_current` can enter `db.no_autoflush` or inspect pending dependency changes.

**Impact:** A supposedly metadata-only read issues caller-owned assessment writes without the caller choosing to flush. The new guard's pending-change protection is reached too late. This can alter transaction behavior and causes the metadata integration to violate its no-implicit-flush contract. This reproduction did **not** return stale pupil prose or prove a source-permission bypass; its concrete failure is the write side effect and consumed pending state.

**Required repair:** Protect the entire directly used predicate from autoflush, and fail closed for relevant pending new/dirty/deleted dependencies without flushing, refreshing away, or erasing caller changes. Keep ordinary unrelated pending transaction state intact.

**Evidence:** `var/review-j05-generation/test_independent.py::test_full_generated_goal_metadata_port_keeps_pending_assessment_change_unflushed`; `independent.log`: two reproduced failures, one per database. Captured output: `metadata result False flush count 1 still dirty False`.

### J05-GEN-R2 — P2: New generated-lineage guard treats a pending source-link revocation as current

**Exact-pin location:** `backend/spesped/contexts/plans/projections.py:78-96`, especially the pending-model guard at line 85.

The new `generation_bindings_are_current` helper encloses its reads in `no_autoflush`, but its pending-change guard covers plan/basis/goal/profile/expert rows only. It does not account for the source-link changes on which the same lineage depends.

Independent reproduction on SQLite and PostgreSQL:

1. Apply an explicitly selected generated-goal proposal and retain its generation lineage.
2. Load the selected expert/profile source's `SourceSubjectLink` in the caller session and stage `revoked_at = utcnow()` without flushing.
3. Call the new `generation_bindings_are_current` helper directly.

Observed on both databases: **True**, with **zero flushes** and the revoked link **still dirty**. Its subsequent metadata query sees the old committed source-link state. The explicit pending guard does not reject that staged dependency revocation.

**Impact:** Even after repairing the outer autoflush, the generated-lineage helper can report currency while its caller has already staged revocation of a source required by that lineage. A curated projection relying on this predicate receives an incorrect positive currency result for the pending transaction state. The helper returns only a boolean; this test does not establish an unrelated source-prose permission bypass.

**Required repair:** Include relevant pending source/dependency changes in the fail-closed currency decision through owning-context metadata checks or an equivalent narrow guard. Preserve the pending revocation and avoid using flush as the means to notice it.

**Evidence:** `var/review-j05-generation/test_independent.py::test_new_generation_metadata_guard_denies_pending_source_link_revocation_without_flushing`; `independent-pending-source.log`: two reproduced failures. Captured output: `metadata result True flushes 0 still dirty True`.

## Verification

Archive preparation, from `/Users/lauritz/Programming/SpesPed`:

```sh
mkdir -p var/review-j05-generation/pinned
git archive 2ccc30e499d87efba020068528c70f7e5a382a9a | tar -x -C var/review-j05-generation/pinned
```

All commands used:

```sh
PYTHONPATH=/Users/lauritz/Programming/SpesPed/var/review-j05-generation/pinned/backend:/Users/lauritz/Programming/SpesPed/var/review-j05-generation/pinned/backend/tests
SPESPED_TEST_POSTGRES_URL=postgresql+psycopg://spesped_test:synthetic-development-only@127.0.0.1:55432/spesped_test
```

With those variables supplied, from the archive:

```sh
/Users/lauritz/Programming/SpesPed/backend/.venv/bin/python -m pytest backend/tests/test_plan_generation.py -q --tb=short
```

**Result:** **32 passed** in 122.37 seconds; `var/review-j05-generation/baseline.log`. Both SQLite and real PostgreSQL parameters ran. The fixture uses unique `j05_<uuid>` schemas and cleanup, rejects the demo database, and exercises an actual loopback model protocol with synthetic sources. This verifies the pinned code rather than the evolving shared checkout.

Additional independent probes, run from the repository with the same explicit environment:

```sh
backend/.venv/bin/python -m pytest var/review-j05-generation/test_independent.py -q --tb=short
```

The file was built and exercised in targeted runs:

- Initial full-goal metadata probe and PostgreSQL concurrent apply: **2 failed, 1 passed, 1 SQLite skip** in 15.45 seconds (`independent.log`). The failures are J05-GEN-R1.
- `-k 'not full_generated_goal_metadata'`, before adding the pending-source probe: **9 passed, 1 SQLite skip** in 36.00 seconds (`independent-extra.log`). This reran the PostgreSQL contention case and covered all additional source/replay/selection/lineage branches below.
- `-k pending_source_link`: **2 failed** in 7.00 seconds (`independent-pending-source.log`). These are J05-GEN-R2.

Assertions in the two failing probes express the desired metadata contract; failures are reproducible review evidence. The only warning is the existing FastAPI/Starlette test-client deprecation.

### Independently verified behavior outside the findings

The 32 reproduced author tests cover real local proposal execution; exact field and goal selection; manually selected dates/curriculum for new goals; rejection/discard without a revision; stale plan/basis conflicts; unsupported output, unknown sources and foreign goal targets; processing recall and source correction; rollback of revision/review/audit/outbox/derivatives after a late failure; imported-plan provenance; regeneration retaining the active revision; transitive ancestor lineage; and forward migration preserving populated manual revision hashes, checks and plan-model metadata on both databases.

Additional independent probes established:

- Two concurrent PostgreSQL applications of the identical logical selection produce one new revision, one review, one outer command receipt, one review audit and one review outbox event. Both retries return the same result.
- An assessment from another case of the same pupil is rejected as generation basis; a confirmed profile statement from another pupil is also rejected. Neither request invokes generation beyond the fixture's prior synthetic release evaluation.
- Revoking exact case-read authority after application blocks generated plan prose, generation-basis reads and apply replay; review history retains its metadata but nulls its reason.
- Reusing an applied selection's request key with a different outcome returns `idempotency_conflict`; the original replay remains idempotent with one review.
- All six generated goal-field lineage paths survive an ordinary human edit. Explicit independent replacement of each field severs that lineage; after model-release recall the independently authored goal remains readable while derived historical revisions are hidden.

Inspection confirms the consumer starts from a human-authored IEP with exact confirmed decision provisions. Typed output is limited to proposed pedagogical text. Human-owned dates, decision references/quantities, participation, curriculum references and approval are preserved or separately supplied; application creates a draft, and activation remains separate. Source and case checks are repeated for proposal retrieval/application/replay, and lineage is retained through later edits/regeneration. No additional source/case/selection/replay defect was reproduced in this review. The metadata findings must be repaired before acceptance.

## Boundaries

Root's gateway/runtime-binding review, known older teaching findings, final assembly and shared joined tests are separate. Standalone adaptation generation and curriculum integration are visibly unavailable; UI and full F08 remain incomplete. Synthetic protocol verification does not establish school-specific legal correctness, practitioner acceptance, external-service readiness or production readiness. The earlier accepted manual-core review remains intact.

After all probes, a read-only query confirmed database `spesped_test` and **zero remaining `j05_%` schemas**. `git diff --check -- docs/reviews/J05-generation-review.md` passed.

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

## Metadata repair recheck — exact 2e305db6db62b306ca13a1d1d1265f1b84204257

Rechecked 21 October 2026. **Verdict: changes still required. Original J05-GEN-R1 and J05-GEN-R2 are resolved on this pin; two adjacent exact-dependency cases below remain open as J05-GEN-R3/R4.** The earlier candidate report is preserved above. No manual-core acceptance is changed.

Archived the repair at `/Users/lauritz/Programming/SpesPed/var/review-j05-generation/recheck-pinned`. Printed imports for `spesped`, `plan_generation_fixtures` and `plans.projections`; all resolve inside this new archive. Inspected the two repair files, `plans/projections.py` and `test_plan_generation.py`. Included root composition remains separately reviewed; uncommitted teaching interval/migration repairs were not used. No production files were edited.

### Original findings resolved; transaction/read properties verified

The full goal predicate now runs within `no_autoflush`. The guard checks exact pending source/link/item/revision, entitlement/case/provision, assessment/recommendation/profile, plan/goal and gateway bindings, inspecting identity/history rather than loading expired object attributes. The unchanged original assessment-autoflush and pending-source-link reproductions pass on SQLite and PostgreSQL. The committed expanded metadata tests also pass, preserving new/dirty/deleted object sets and values across the covered dependency classes, including unknown or expired owner state and unrelated pending work.

Independent additional evidence confirms:

- A staged source-link revocation is denied without flushing, remains dirty, and survives the caller's later explicit commit. The committed revocation is still denied in a fresh session.
- On clean valid metadata, the predicates return true with an unrelated pending audit row while performing only SELECTs, without invoking `Session.refresh` or the source resolver. SQL observation detects no selected generated output, basis content, plan/goal titles, expert issuer, recommendation content, evidence prose/excerpt or source storage key. Expired expert prose and link excerpt remain unloaded, and the audit remains pending.
- A staged recommendation deletion remains in `db.deleted`, causes false without flush, and can later be explicitly committed. Its post-commit currency is the remaining defect below; the metadata read itself correctly preserves the deletion.

### J05-GEN-R3 — P2: Committed recommendation removal is absent from immutable metadata dependency checks

**Repair-pin locations:** `backend/spesped/contexts/plans/generation.py:82` (dependency manifest); `backend/spesped/contexts/plans/projections.py:152-167` (pending recommendation guard versus committed metadata checks).

Independent reproduction on SQLite and PostgreSQL:

1. Apply an explicitly selected generated goal and activate it; retain its authorized goal binding.
2. Stage deletion of the original `Recommendation` from the selected expert assessment. Both predicates correctly deny it while pending, without flushing or removing it from the caller's deletion set.
3. Explicitly commit that deletion, then open a fresh session and check the same derived goal.

The full metadata predicate now returns **True**. The dependency manifest retains assessment identity/version/case/confirmation and source bindings but no exact recommendation membership descriptor. Once `db.deleted` is empty, only the assessment header is checked; its unchanged version and still-current source bindings do not reveal the removed recommendation.

The same reproduction reads the plan through its actor-aware HTTP endpoint: it correctly returns `source_status: review_required` and omits goal prose because recollecting the exact basis detects the missing recommendation. Captured output on both databases is `goal currency: True actor-aware plan source_status: review_required`.

**Impact:** The curated metadata path and owning-context source-aware read disagree after a committed dependency removal. A caller using the metadata predicate receives a positive currency result for generated material whose original expert recommendation basis no longer matches. This is an application-service/ORM deletion probe; no public recommendation-delete HTTP endpoint is claimed. It directly exercises the requested behavior after the caller explicitly commits a preserved deletion.

**Required repair:** Persist and compare exact immutable recommendation membership using metadata only. If an existing/legacy dependency descriptor cannot establish that membership, fail closed rather than retrieving source prose or assuming the unchanged assessment header is sufficient.

**Evidence:** `var/review-j05-generation/test_metadata_recheck.py::test_recommendation_deletion_survives_metadata_and_is_still_stale_after_explicit_commit`; `recheck-adverse.log` and strengthened confirmation `recheck-deletion-and-reads.log`, one failure per database.

### J05-GEN-R4 — P2: An explicit no-replacement profile proposal is treated as unknown dependency ownership

**Repair-pin locations:** `backend/spesped/contexts/plans/projections.py:42` and `105-111`.

In a valid generated-goal session, stage a separate new `ProfileStatement` with a distinct known ID, an explicit profile ID, and **`replaces_id=None`**. Its state is proposed; it does not change the exact confirmed statement selected for the generation basis. The full goal predicate returns **False** on both databases, without flushing.

`profile_bindings_are_current` tests pending statements using `replaces_id` as the owner relationship. `_pending_metadata` treats a present, explicit optional `None` the same as absent/unloaded ownership, so a known proposal that replaces no statement invalidates every selected profile dependency in that session.

**Impact:** Legitimate unrelated pending profile work makes an unchanged exact selected goal appear stale. The conservative behavior required for genuinely unknown/expired ownership must remain distinct from the known absence of this optional replacement relationship.

**Required repair:** Treat an explicitly known null replacement as no replacement, while keeping missing/unloaded owner information fail-closed and preserving pending objects.

**Evidence:** `var/review-j05-generation/test_metadata_recheck.py::test_known_unrelated_new_profile_statement_does_not_invalidate_exact_selected_profile`; `recheck-adverse.log`, one failure per database. The probe uses a separate statement in the same profile to establish that the exact confirmed selection itself is unchanged.

### Exact focused commands and results

Preparation from `/Users/lauritz/Programming/SpesPed`:

```sh
mkdir -p var/review-j05-generation/recheck-pinned
git archive 2e305db6db62b306ca13a1d1d1265f1b84204257 | tar -x -C var/review-j05-generation/recheck-pinned
```

All commands explicitly supplied:

```sh
PYTHONPATH=/Users/lauritz/Programming/SpesPed/var/review-j05-generation/recheck-pinned/backend:/Users/lauritz/Programming/SpesPed/var/review-j05-generation/recheck-pinned/backend/tests
SPESPED_TEST_POSTGRES_URL=postgresql+psycopg://spesped_test:synthetic-development-only@127.0.0.1:55432/spesped_test
```

From the archive, with those environment variables:

```sh
/Users/lauritz/Programming/SpesPed/backend/.venv/bin/python -m pytest \
  backend/tests/test_plan_generation.py \
  /Users/lauritz/Programming/SpesPed/var/review-j05-generation/test_independent.py \
  -q --tb=short -k 'full_generated_goal_metadata or pending_source_link or complete_goal_metadata or keeps_unrelated_pending'
```

**Result:** **8 passed, 42 deselected** in 40.50 seconds (`recheck-focused.log`). This includes all four unchanged original desired-behavior reproductions and both new author tests on each database. The full 32-test baseline was not unnecessarily repeated for the two-file repair.

Additional independent file, from the repository with the same explicit environment:

```sh
backend/.venv/bin/python -m pytest var/review-j05-generation/test_metadata_recheck.py -q --tb=short
```

Initial cases: **4 failed, 2 passed** in 27.28 seconds (`recheck-adverse.log`). Failures establish R3/R4; passes establish pending-link preservation and later explicit commit. After adding the clean SQL/refresh/resolver probe and strengthening the deletion check with the actor-aware HTTP comparison, `-k 'recommendation_deletion or clean_metadata'` produced **2 failed, 2 passed** in 20.43 seconds (`recheck-deletion-and-reads.log`). Failures reconfirm R3; clean read-only probes pass on both databases. The only warning remains the existing test-client deprecation.

Source-authority, standalone adaptation/curriculum, full F08/UI, final assembly and production-readiness limitations remain as stated in the original report. No additional source permission issue is inferred from these metadata results.

All reviewer fixture teardowns completed without errors. A final read-only query confirmed database `spesped_test`; one `j05_%` schema was present while other regression work was running. No schema outside the review fixtures was modified or removed, and no claim of global zero schemas is made for this concurrent recheck. `git diff --check -- docs/reviews/J05-generation-review.md` passed.

## Second metadata repair recheck — exact 54f40085911bb56f3fa2b3b38253db7e43d72c00

Rechecked 21 October 2026. **Bounded verdict: accept the reviewed generated-IEP consumer/backend slice on this exact pin. J05-GEN-R1–R4 are closed.** No remaining concrete defect was reproduced within this review scope. Earlier reports and their original-pin evidence remain preserved above; this acceptance applies to the repaired consumer only, not full F08/UI or separate root/teaching work.

### Isolation and inspected changes

Created another immutable archive at `/Users/lauritz/Programming/SpesPed/var/review-j05-generation/recheck2-pinned`. Printed and verified imports for `spesped`, `plan_generation_fixtures`, `plans.generation` and `plans.projections`, all resolving inside the new archive. Every command explicitly set absolute archive backend/tests paths before any helper-test path in `PYTHONPATH`, overriding the editable backend installation.

Inspected the three-file repair: `plans/generation.py`, `plans/projections.py`, and `test_plan_generation.py`. The generation basis now stores the sorted exact `recommendation_ids` for each selected assessment. Metadata currency requires that descriptor and compares it with the current recommendation identities; neither an unchanged count nor an unchanged assessment header can substitute for exact membership. Existing descriptors that lack membership fail closed without reconstructing it from pupil/model prose. The dependency digest covers the new descriptor.

The pending-owner helper now permits explicitly known null ownership only for the optional profile `replaces_id` relationship. Missing/unloaded ownership still fails closed; a staged change away from a formerly selected owner still matches its retained history and is denied. This does not relax source/case permissions or implicit-write restrictions.

No production files were changed by the reviewer. The earlier manual-core acceptance and separately reviewed composition/runtime/teaching scopes remain unchanged.

### Findings verified closed

- **R1/R2 remain resolved:** unchanged original autoflush/pending-source probes pass. The complete predicate preserves pending modifications/deletions and performs no implicit flush, refresh or source resolution. Existing clean metadata checks, expired-prose checks and unrelated pending-audit behavior pass.
- **R3 resolved:** the preserved independent committed-recommendation-deletion probe now returns false after explicit commit and agrees with the actor-aware plan view. Author add/delete tests pass on both databases. An additional independent test replaces the original recommendation with a new identity while preserving its fields and total count; the pending and committed exact-membership checks both return false. A legacy descriptor with membership removed and its digest recomputed also returns false through both metadata entry points, while resolver/refresh traps and SQL observation verify no generated output, stored basis prose, recommendation content or evidence excerpt is read to fill the gap.
- **R4 resolved:** the preserved independent explicit-None profile proposal now leaves the selected goal current without flushing. The focused author cases verify explicit known None remains distinct from missing owner state, expired ownership and a staged detachment from a formerly selected statement; pending sets and object dictionaries remain intact in all cases.

The repaired membership checks remain metadata-only. They do not invent confirmation, alter human-selected goals, rewrite stored historical content or grant source access. The deliberate fail-closed behavior for older incomplete metadata is preserved.

### Exact commands and completed results

Preparation from `/Users/lauritz/Programming/SpesPed`:

```sh
mkdir -p var/review-j05-generation/recheck2-pinned
git archive 54f40085911bb56f3fa2b3b38253db7e43d72c00 | tar -x -C var/review-j05-generation/recheck2-pinned
```

Both test runs explicitly supplied:

```sh
PYTHONPATH=/Users/lauritz/Programming/SpesPed/var/review-j05-generation/recheck2-pinned/backend:/Users/lauritz/Programming/SpesPed/var/review-j05-generation/recheck2-pinned/backend/tests
SPESPED_TEST_POSTGRES_URL=postgresql+psycopg://spesped_test:synthetic-development-only@127.0.0.1:55432/spesped_test
```

From the archive:

```sh
/Users/lauritz/Programming/SpesPed/backend/.venv/bin/python -m pytest \
  /Users/lauritz/Programming/SpesPed/var/review-j05-generation/test_metadata_recheck.py \
  /Users/lauritz/Programming/SpesPed/var/review-j05-generation/test_independent.py \
  backend/tests/test_plan_generation.py -q --tb=short \
  -k 'metadata or pending_source_link or recommendation_membership or unrelated_profile'
```

**Completed result:** **24 passed, 42 deselected** in 104.95 seconds; `var/review-j05-generation/recheck2-focused.log`. The preserved independent files were unchanged. Both SQLite and real PostgreSQL parameters ran; there were no skips or failures in the selection.

Additional independent exact-substitution/legacy probes and explicit owner-state cases, from the repository:

```sh
backend/.venv/bin/python -m pytest \
  var/review-j05-generation/test_metadata_recheck2.py \
  var/review-j05-generation/recheck2-pinned/backend/tests/test_plan_generation.py \
  -q --tb=short -k 'substitution or legacy_missing_membership or optional_profile'
```

For this second run only, the ignored helper-test directory `/Users/lauritz/Programming/SpesPed/var/review-j05-generation` was appended after both archive paths in `PYTHONPATH` to import the preserved independent test helpers. **Completed result:** **6 passed, 42 deselected** in 26.60 seconds; `recheck2-membership.log`. These cover same-count identity substitution, missing legacy membership with a valid digest and no prose fallback, and the null/missing/expired/former-owner distinction on both databases.

Both processes were awaited to exit code 0, and their complete logs were saved before this verdict. All reviewer fixture teardowns completed without errors and used fresh unique synthetic test schemas; no unrelated schema was modified. The only warning remains the existing FastAPI/Starlette test-client deprecation.

### Acceptance boundary

This closes the four consumer findings and accepts the bounded reviewed IEP proposal/selection/lineage backend behavior with its repaired metadata integration. The original 32-test consumer run and additional source/case/replay/concurrency evidence remain documented above; the full baseline was not unnecessarily repeated for this narrow three-file repair. Standalone adaptation generation, curriculum integration, UI/full F08, final assembly and separately reviewed gateway/teaching changes remain outside this acceptance. Source authority, practitioner validation and school/production-readiness limitations remain in force.

Final read-only cleanup observation: database `spesped_test`, one `j05_%` schema present during concurrent work. Reviewer fixture teardowns reported no errors; no unrelated schema was removed and global zero schemas is not claimed. `git diff --check -- docs/reviews/J05-generation-review.md` passed.

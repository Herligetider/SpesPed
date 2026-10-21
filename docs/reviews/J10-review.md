# J10 independent BC09 backend and application review

- Reviewer: `/root/review_j09`, independent of `/root/j10_assessment` and the application-composition author `/root`.
- Reviewed commit: `673a0ebe078a31191a529e0947560dd03f6f872e`.
- Review date: 21 October 2026.
- Verdict: **changes required** for the bounded BC09 backend/application job. J10-R1 and J10-R2 require repair and independent recheck.
- Scope: all 15 candidate files: the assessment package, static `j10_assessment` migration and metadata registration, actual application router registration, fixtures and four assessment/composition test files.
- Contracts read: `AGENTS.md`; complete F11/F17/F19 entries; relevant BC09/shared event contracts in `docs/04-domain-model.en.md`; authorization, revision, transaction and read-only assessment-input contracts in `docs/09-domain-implementation.en.md`. The separately accepted native `a0bc` projections are inputs to this review, not proof of assessment-consumer correctness.

## Findings

### J10-R1 — P2: Late evidence is dropped when a confirmed progress review becomes a downstream source

Location: `backend/spesped/contexts/assessment/service.py:259–266`, especially the source acceptance condition at line 265. Progress currentness is calculated at lines 331–344; statement finalization consumes that source through `statement_basis` and `statement_view`.

A confirmed progress review correctly reports `review_required=true` after a new observation occurs within its frozen review interval. However, for late evidence alone it retains `source_status=current`. `resolve_reference` tests that status and the confirmed revision, but ignores `review_required` and omits the late-evidence/review markers from its returned source value. Consequently, the downstream source digest remains unchanged. An existing subject statement using that review as explicit `iop_context` continues reporting current sources and can finalize without reviewing the new contradictory evidence. The problem also applies to other downstream consumers of `resolve_reference`.

Independent HTTP reproduction on SQLite and PostgreSQL: create a live goal and observation, create and human-confirm a progress review, create a subject statement with separate valid subject-competence evidence plus that review as IOP context, then enter a contradictory observation dated inside the original progress interval. The progress detail reports review required and names the new revision. The statement still reports `source_status=current`, lacks the late-evidence warning, and finalizes with the deliberately synthetic exact authority fixture. This fixture demonstrates the consumer gate; it does not establish production professional authority.

Evidence: `var/review-j10/test_independent.py::test_late_progress_evidence_is_not_propagated_to_statement_or_reference`; markers `PROBE_LATE_PROGRESS_SOURCE_STILL_FINALIZABLE True current` in `var/review-j10/independent.log`.

Required correction: preserve the confirmed historical review and its immutable judgement, but prevent a review-required progress record from silently remaining a current downstream source. Propagate the source/review state and invalidate/block downstream source review or finalization until the professional explicitly handles the new basis. Verify existing and newly created downstream references, replay and finalized historical records. This is a BC09 consumer-freshness correction, not a request to implement the absent J19 authority adapter.

### J10-R2 — P2: Persisted assessment events omit the shared event envelope

Location: `backend/spesped/contexts/assessment/models.py:151–159`, `service.py:38–41`, and the corresponding `assessment_outbox` definition in `backend/migrations/versions/j10_assessment.py`.

The event table stores the inherited ID/creation timestamp plus school, aggregate, version, actor, event type, payload, causation key and processing timestamp. It has no `occurred_at`, `recorded_at`, `correlation_id` or `schema_version`. The emitter does not supply equivalents. The shared contract at `docs/04-domain-model.en.md:237` explicitly requires occurrence and recording times, correlation and schema version in addition to the other envelope fields. One creation timestamp and a causation key do not supply those four distinct semantics. Atomic persistence alone does not satisfy the consumer event contract.

Independent reproduction on both databases: emit a normal instrument event through the HTTP workflow, inspect the migrated `assessment_outbox` columns and the persisted row, and confirm all four fields are absent. Evidence: `test_persisted_outbox_lacks_required_shared_envelope` and markers `PROBE_PERSISTED_OUTBOX_MISSING_ENVELOPE ['correlation_id', 'occurred_at', 'recorded_at', 'schema_version']` in the independent log.

Required correction: add and populate the complete shared event envelope in the model, emitter and assigned migration strategy. Verify aware occurrence/recording timestamps, nonempty correlation, explicit schema version and causation, while preserving atomic business/audit/outbox/receipt rollback and metadata/migration alignment. Avoid duplicating source or assessment prose in the event payload.

## Verification

All executed candidate evidence used a new frozen `git archive` extraction at `var/review-j10/frozen`. Absolute `PYTHONPATH` selected that archive's backend and tests over the shared editable virtualenv installation. `var/review-j10/pin.log` verifies all 15 candidate files byte-for-byte against the commit and records the frozen application and assessment service module paths. No production or shared source files were edited.

Python runtime: existing backend Python 3.12 virtualenv. PostgreSQL tests used fresh unique schemas in the assigned synthetic `spesped_test` database; SQLite used temporary files. Fixture teardown was restricted to each fixture's own schema. No demo database, global cleanup, real pupils, external messages, external model calls or other agents' processes were used.

Set `SPESPED_TEST_POSTGRES_URL` to the assigned isolated synthetic database URL:

```sh
# Working directory: /Users/lauritz/Programming/SpesPed/var/review-j10/frozen
PYTHONPATH=/Users/lauritz/Programming/SpesPed/var/review-j10/frozen/backend:/Users/lauritz/Programming/SpesPed/var/review-j10/frozen/backend/tests \
  /Users/lauritz/Programming/SpesPed/backend/.venv/bin/python -m pytest \
  backend/tests/test_assessment.py backend/tests/test_assessment_contracts.py \
  backend/tests/test_assessment_migrations.py backend/tests/test_bc09_application_composition.py -q

# Working directory: /Users/lauritz/Programming/SpesPed
PYTHONPATH=/Users/lauritz/Programming/SpesPed/var/review-j10/frozen/backend:/Users/lauritz/Programming/SpesPed/var/review-j10/frozen/backend/tests \
  backend/.venv/bin/python -m pytest var/review-j10/test_independent.py -q -s
```

Results:

- Candidate plus fresh-application composition suites: **43 passed, 1 skipped**, 69.61 seconds. The skip is the SQLite instance of the explicitly PostgreSQL concurrency test. The actual PostgreSQL same-key and competing-version commands ran.
- Independent probes: **10 passed**, 14.49 seconds. Five scenarios ran on both databases. Two assert the observed defects and must assert corrected behavior during recheck. Three positive adverse scenarios check exact scale/condition/authority rejection without state changes; same-transaction owner reads preserving flushed caller work and refusing pending identity changes without overwriting them; and rejection of authority responses misbound to another person, pupil, school, purpose, exact revision, digest or start date.
- Existing contract tests also instrument connection commit/rollback, SQL DML and caller flush events: owning-context reads produced zero such side effects, left the caller transaction active, preserved a flushed caller row until the caller rolled it back, and refused pending assessment edits. Retained ORM reads rechecked revoked original links and disabled actors. Fault injection verified business/audit/outbox/receipt rollback together.
- Static migration tests verified all 16 owned tables, model/metadata equality, empty upgrade/downgrade/upgrade, and refusal to discard retained assessment rows, on both databases.
- Logs/source: `var/review-j10/baseline.log`, `var/review-j10/independent.log`, `var/review-j10/pin.log`, `var/review-j10/test_independent.py`.
- Warnings: existing Starlette/httpx TestClient deprecation and the explicit BC06 `ResourceRights.copy` field shadowing Pydantic's legacy method.

The executed suites cover instrument review/version and licensing, finite explicit raw scales, recorded conditions, planned/started/aborted/recorded/reviewed outcomes, append-only result corrections, source-backed minimum intervals and open questions when guidance is absent, exact current source/goal/scheme/actual access, learner and tenant denial, immutable progress snapshots/human transitions, comparison limitations and late evidence at the original review, separate subject/IOP basis, public/Montessori scheme provenance, human-entered grades under an explicit authority fixture, contribution attribution, and separate factual communication records with `external_send_performed=false`. Those passing checks do not resolve the downstream freshness or event-envelope findings above.

## Required remaining delivery boundaries

- The real J19 qualification, professional finalization, subject completion, grading and exemption adapter remains absent. Fresh actual `create_app` tests omit synthetic authority ports: instrument planning visibly reports unavailable qualification, starting without authority fails with 409, and subject statement finalization without authority fails with 409 while preserving the manual draft, state, version and empty finalization/communication lists. Role/assignment test fixtures are not production professional approvals.
- Typed AI generation is not integrated. Manual source-backed progress and statement drafts persist `drafting=manual_grounded_source_review` and `ai_generation=not_integrated`. No model-generated judgement or grade is claimed.
- J20 browser journeys, graphs/comparison presentation, practitioner-specific assessment fields and full UI recovery remain required for complete F11/F17/F19 delivery.
- F32 authoritative-system transfers and actual disclosure/dispatch integrations remain separate. The current communication command records a human-reported factual event and does not send or certify delivery.
- Full delivery of all 40 features and production/legal readiness are not established by this backend review. No current-law research was performed; the September legal registry is not newly approved.

All reviewer-owned execution sessions completed and fixture teardown ran. Changes require independent repair verification before this bounded job is accepted.

## Independent R1/R2 repair recheck — 21 October 2026

**Rechecked commit:** `7443e4e1b4e0c3a9a6dfdd2b6cedd6bc53d3d09e`.

**Updated verdict: verified for the assigned BC09 backend and actual-application composition scope. J10-R1 and J10-R2 are fixed; no additional actionable finding remained in this bounded recheck.** The original review and evidence remain above. Native J19 authority, typed AI, browser/UI and dispatch/authoritative-system integration remain outstanding; this verdict does not establish full F11/F17/F19 or all-40-feature completion, production readiness or legal approval.

The recheck used a new frozen archive under `var/review-j10/repair-7443e4e`, with absolute archive backend/test imports. `var/review-j10/recheck-pin.log` verifies the five repair files against the exact commit, records frozen application/service module paths, and separately confirms that the original `j10_assessment.py` migration is byte-for-byte unchanged from the initially reviewed candidate. Uncommitted source-maintenance backend/web changes in the shared checkout were excluded.

### Finding dispositions

**J10-R1 fixed.** `resolve_reference` now carries an explicit `source_review` marker for an available but review-required historical progress review. The marker changes the resolved source digest and propagates through nested progress references, statement bases and staff-contribution sources. A review-required source is therefore distinct from a current source even when its exact confirmed human revision remains retained. Statement/progress transitions and statement finalization reject the unresolved basis. New draft statements referencing such history visibly need basis rather than silently resetting the warning. Previously finalized statements keep their human judgement, exact finalization and finalized state, while detail and replay report the live source warning.

The executed regression suite verified late observations through nested confirmed reviews, existing/new statements, creation/finalization replay, revision history, new progress references, and source corrections. It also verified that a fresh human review over the new evidence permits subsequent work without clearing the original historical warning. Late confirmed BC02 goal evidence propagates its exact evidence/revision coordinate; a late disputed report changes the evidence-availability marker without being promoted into usable confirmed evidence.

The original independently authored failing workflow was rerun with fixed expectations on both databases: the upstream review and downstream statement now report review required, the statement retains the original content/digest, finalization returns 409 and no finalization is persisted. An additional independent contribution-only workflow finalized a statement while its source was current, then added late contradictory progress evidence. Detail and exact finalization replay preserved the same human content/finalization while reporting the contribution's review dependency. An attempted subsequent factual communication entry returned 409 and created no communication row. These checks verify that the repair reaches contribution consumers as well as the main statement basis.

**J10-R2 fixed.** The forward `j10_assessment_events` migration adds aware `occurred_at`/`recorded_at`, `correlation_id` and explicit `schema_version` without editing the original migration. New emitter records use schema version 1, a command correlation, the request key as causation and minimized payload. Actual administration start/result and recorded communication events preserve their supplied occurrence instants separately from recording time; recording time also supplies `created_at`. Idempotent command replay adds no event. Existing caller correlation state is restored when the command ends.

Retained events are explicitly schema version 0: both event times use the only known original `created_at`, and correlation uses the retained event ID. The migration documents this legacy limitation rather than inventing a missing occurrence time or command correlation. The dual-database retained-row migration test verified all pre-existing column values unchanged, deterministic version-0 fields, UTC-aware ORM reads and refusal to downgrade while retained envelopes exist. New version-1 events were independently checked through real migrated columns and persisted HTTP-generated rows. Model/metadata alignment, empty roundtrip and retained-assessment downgrade refusal passed with the new migration head. The existing fault-injection test still verified business, audit, outbox and receipt rollback together.

### Commands and results

Set `SPESPED_TEST_POSTGRES_URL` to the assigned isolated synthetic database URL:

```sh
# Working directory: /Users/lauritz/Programming/SpesPed/var/review-j10/repair-7443e4e
PYTHONPATH=/Users/lauritz/Programming/SpesPed/var/review-j10/repair-7443e4e/backend:/Users/lauritz/Programming/SpesPed/var/review-j10/repair-7443e4e/backend/tests \
  /Users/lauritz/Programming/SpesPed/backend/.venv/bin/python -m pytest \
  backend/tests/test_assessment.py backend/tests/test_assessment_contracts.py \
  backend/tests/test_assessment_migrations.py backend/tests/test_assessment_repairs.py \
  backend/tests/test_bc09_application_composition.py -q

# Working directory: /Users/lauritz/Programming/SpesPed
PYTHONPATH=/Users/lauritz/Programming/SpesPed/var/review-j10/repair-7443e4e/backend:/Users/lauritz/Programming/SpesPed/var/review-j10/repair-7443e4e/backend/tests \
  backend/.venv/bin/python -m pytest var/review-j10/test_recheck.py -q -s
```

- Frozen repaired assessment, contract, migration, repair and fresh-application suites: **57 passed, 1 skipped**, 95.77 seconds. The skip is the SQLite instance of the PostgreSQL-only concurrency proof; the PostgreSQL case ran.
- Independently authored recheck: **12 passed**, 20.52 seconds. All six scenarios ran on SQLite and PostgreSQL. Both original defect probes now assert corrected behavior, three earlier adverse checks remain green, and the added contribution-only history/replay/communication check passes.
- Logs/source: `var/review-j10/recheck-baseline.log`, `var/review-j10/recheck-independent.log`, `var/review-j10/recheck-pin.log`, `var/review-j10/test_recheck.py`.
- The same two nonfatal Starlette/httpx and BC06 Pydantic field-name warnings remain.

All reviewer-owned execution sessions completed; unique synthetic PostgreSQL fixture schemas were cleaned up by their own teardown. No production edits, commits, pushes, subagents, external messages, demo database access or unrelated process interference occurred. Synthetic authority fixtures remain contract evidence only. The fresh actual application continues to fail closed where native J19 authority is unavailable, and manual drafts still declare typed AI generation unintegrated.

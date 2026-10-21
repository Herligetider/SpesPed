# J09 independent backend and application composition review

- Reviewer: `/root/review_j09`, independent of the implementation author.
- Reviewed commit: `d065091e8915594a3177876193f675c18ca0aa23`, branch `codex/implement-spesped`.
- Review date: 21 October 2026.
- Verdict: **changes required** for the bounded BC06 backend/application composition job. J09-R1 and J09-R2 require repair and independent recheck.
- Specifications read: `AGENTS.md`; complete F09/F10 entries in `docs/features.json`; BC06 definitions in `docs/04-domain-model.en.md`; shared authorization, revision, transaction and consumer contracts in `docs/09-domain-implementation.en.md`; J09/J15/J20 boundaries in `docs/10-master-plan.en.md`.
- Reviewed implementation: all seven curriculum modules, curriculum fixtures/tests, static `j09_curriculum` migration, application router registration, migration metadata registration and actual-app composition test. No production code or other agent's files were changed.

## Findings

### J09-R1 — P2: A corrected theme/goal choice leaves conflicting active decisions

Location: `backend/spesped/contexts/curriculum/service.py:291–301`, especially line 300; current context selection at lines 283–287. The HTTP binding surface is `backend/spesped/contexts/curriculum/router.py:100–119`.

`bind_goal` always creates another immutable active binding. There is no version-checked correction, withdrawal or supersession command, and no uniqueness/current-choice rule for an exact school, plan revision, theme, learner and goal revision. After a professional changes their decision from `adapt` to `not_relevant`, the normal class-context projection continues returning both contradictory choices as active. Creating a new command key is a legitimate new human decision, so request-key deduplication does not resolve the conflict. The old decision cannot be retired through this API.

Reproduced independently through the actual application on SQLite and PostgreSQL: publish a mixed-age class plan against a reviewed scheme, create a live BC05 goal, bind the exact theme/goal with adaptation and materials, then post the same coordinates with `participation=not_relevant` and a fresh key. Both return 201; the same dated class-context response contains `['adapt', 'not_relevant']`. Evidence: `var/review-j09/test_independent_j09.py::test_conflicting_binding_choices_remain_active`, markers `PROBE_CONFLICTING_ACTIVE_BINDINGS` in `var/review-j09/independent.log`.

Required correction: provide an explicit expected-version correction/supersession or withdrawal workflow that preserves authored history and exposes one current human choice per exact binding. Distinct goal links must remain possible. Check stale-version and concurrent correction handling, idempotent retries, and the final current context on PostgreSQL.

### J09-R2 — P2: Corrected actual delivery leaves unsupported resource experience unmarked

Location: `backend/spesped/contexts/curriculum/router.py:212–219`, especially line 218. Creation's current-actual validation is in `backend/spesped/contexts/curriculum/adapters.py:74–93` and `service.py:476–483`.

Experience creation correctly requires the current BC07 actual revision and nonzero delivered/partial pupil participation. The experience list then returns stored rows without checking that support or exposing its currentness. If BC07 corrects participation to absence, the resource library still exposes the former positive use experience without a review-required/historical-support marker. This makes a corrected actual look like valid evidence of use in the resource's recorded experience. `constitutes_approval=false` correctly separates approval, but does not disclose that the actual attribution has ceased to support the experience.

Reproduced independently on both databases: create a real delivered actual with pupil participation, record resource experience, then use the real BC07 correction command with a valid partial record, learner-absence cause, owned follow-up and zero pupil minutes. A fresh experience command against the old actual revision receives 409, demonstrating the native adapter detects the correction. `GET /resource-experiences?learner_id=...` nevertheless returns the previous row with its old delivery revision and no source status, actual status, review-required or state field. Evidence: `test_experience_still_exposed_after_actual_corrected_to_absence` and markers `PROBE_STALE_EXPERIENCE_NO_WARNING`.

Required correction: retain the historical record and its exact reference, but recheck its supporting actual when producing the current library projection and explicitly distinguish current support from review-required/historical support. Preserve learner authorization and do not turn the currentness check into a disclosure of another pupil's actual record. Verify both correction and loss-of-access paths.

## Verification and evidence

All executed acceptance evidence used a frozen `git archive` extraction under ignored `var/review-j09/frozen`. Absolute `PYTHONPATH` selected that archive's backend and tests, overriding the shared editable environment. `var/review-j09/pin-verification.log` verifies reviewed files byte-for-byte against the commit and records the imported frozen `spesped.main` and curriculum service paths. The shared checkout's teaching UI work was not read as candidate code or changed.

Runtime: existing Python 3.12 backend virtualenv. Database verification used temporary SQLite files and fresh uniquely named PostgreSQL schemas in `spesped_test`. Fixture cleanup drops only its own unique schemas. No `spesped_demo` access, global drops, real pupils, external messages or external model calls were used.

Commands, with `SPESPED_TEST_POSTGRES_URL` set to the assigned isolated synthetic database URL:

```sh
# Working directory: /Users/lauritz/Programming/SpesPed/var/review-j09/frozen
PYTHONPATH=/Users/lauritz/Programming/SpesPed/var/review-j09/frozen/backend:/Users/lauritz/Programming/SpesPed/var/review-j09/frozen/backend/tests \
  /Users/lauritz/Programming/SpesPed/backend/.venv/bin/python -m pytest \
  backend/tests/test_curriculum.py backend/tests/test_curriculum_composition.py -q

# Working directory: /Users/lauritz/Programming/SpesPed
PYTHONPATH=/Users/lauritz/Programming/SpesPed/var/review-j09/frozen/backend:/Users/lauritz/Programming/SpesPed/var/review-j09/frozen/backend/tests \
  backend/.venv/bin/python -m pytest var/review-j09/test_independent_j09.py -q -s
```

Results:

- Frozen implementation plus actual-app composition suite: **35 passed, 1 skipped**, 45.47 seconds. The skip is the SQLite instance of the PostgreSQL locking/concurrent idempotency test; the PostgreSQL instance ran.
- Independent reviewer-authored HTTP/transaction probes: **12 passed**, 15.59 seconds. Two scenarios assert the observed defects above, each on both databases; these must become assertions of corrected behavior during recheck. Four additional scenarios, each on both databases, verify revoked original authority on idempotent replay and cross-school denial; source-correction hook variant traversal, caller rollback and durable repeat deduplication; current license narrowing for retained revisions and loss of old sharing; and rejection of inconsistent positive inventory availability.
- An initial experience probe used an invalid `delivered` record with absent participation and was correctly rejected with 422 by BC07. The probe was corrected to the valid partial/absence record before the final run; this setup rejection is not an implementation finding.
- Logs: `var/review-j09/baseline.log`, `var/review-j09/independent.log`, `var/review-j09/pin-verification.log`. Reproduction source: `var/review-j09/test_independent_j09.py`.
- Warnings: existing Starlette/httpx TestClient deprecation, and the explicit JSON rights field `copy` shadowing Pydantic's legacy method.

The executed suite meaningfully checks authenticated/CSRF HTTP commands, tenant and learner restrictions, private-by-default library visibility, current dated team membership, immutable exact resource/scheme/class revisions, separate public/Montessori scheme metadata and assessment rules, mixed ages and manual period recovery, exact live BC05 goal bindings, native BC02 protected original/excerpt checks and correction invalidation, resource ancestry and separate read/use/copy/AI licensing, actual BC07 delivered/partial participation, future-impact owner decisions through an explicitly synthetic dependency index, atomic rollback, audit/outbox envelopes, PostgreSQL concurrent request-key serialization, static model/migration alignment, empty downgrade/upgrade and refusal to discard retained BC06 history. Passing those checks does not resolve the two additional workflow findings.

## Explicit remaining integration boundaries

These disclosed boundaries remain required work; they are not accepted as complete F09/F10 delivery:

- Real BC07 `FutureSessionReadPort`, persistent exact dependency indexing and application of human keep/change decisions. The tested dependency index is explicitly synthetic over real teaching rows. The actual app correctly returns 503 for required impact checks when this port is absent, preserving prior published content and rolling back the attempted change.
- BC05/BC07 exact class/resource selections in planning bases and generation, reauthorization at selection and worker execution, grounded AI selection/tagging and explicit professional suitability confirmation. No full AI consumer path was verified here.
- Source-correction/recall subscription invoking `record_source_correction_impacts`, and processing of its impact-decision outbox. The native source projection fails closed on stale originals; that does not deliver proactive change notifications by itself. The independently tested hook participates in the caller transaction and follows resource variants, but is not an installed subscriber.
- J15 reservation ledger/availability adapter. Actual-app availability is explicitly unavailable without the port; catalog counts do not claim a reservation.
- Practitioner/admin authority controls and J20 browser journeys for source/original comparison, period/reference review, explicit goal/resource selection, changes and human publication.

The reviewed commit therefore does not establish completion of all 40 features, full F09/F10 workspace/recovery behavior, production readiness or current legal approval. The September legal registry was not re-researched during this software review. Independent recheck of the two findings is required before accepting this bounded job.

## Independent R1/R2 repair recheck — 21 October 2026

**Rechecked commit:** `c5bf1ecd51deb98f843196bd62922ca68aaa73a4`.

**Updated verdict: verified for the assigned J09 BC06 backend and actual-application composition scope. J09-R1 and J09-R2 are fixed; no additional reproducible finding remained in this bounded recheck.** The original review and reproduction evidence remain above. The explicit BC07 dependency/decision application, BC05/BC07 selection/AI, source-event subscription, J15 reservation and J20/UI integration boundaries remain outstanding. This acceptance does not declare complete F09/F10 delivery, all 40 features complete, production readiness or legal approval.

Recheck used a new frozen archive at `var/review-j09/recheck-c5bf1ec` and absolute backend/test import paths, with byte-for-byte verification against the exact commit in `var/review-j09/recheck-pin.log`. The BC06 repair consists of the seven files named in the author's handoff: models, schemas, service, router, the pre-acceptance static migration, curriculum fixtures and curriculum tests. Other changes present in the committed repository are not accepted by this review. No production files were changed by the reviewer.

### Finding dispositions

- **J09-R1 fixed** (`service.py:302–342`, correction endpoint at `router.py:294`, model/migration active-choice index): duplicate fresh creation returns 409. The explicit correction command requires the exact expected version, checks current learner/source/goal/theme access, preserves coordinates and authored history, supersedes the previous choice and creates a successor with actor, reason and lineage. Both database schemas enforce one active choice per exact binding through a partial unique index. The executed PostgreSQL competing-correction test produced one winner and one version conflict, exactly two authored rows and one active choice. Direct duplicate database insertion was rejected, distinct goal links remained possible, and an unassigned manager received 403 before stale-version information. Independently reproduced the original scenario with fixed expectations and extended it through `adapt → not_relevant → participate`: current context returned only `participate`, history retained all three rows and the original adaptation, stale corrections returned 409, and replaying either the original creation or the first correction exposed its now-superseded logical record instead of stale active success.
- **J09-R2 fixed** (`service.py:513–545`, list projection at `router.py:218`, current reprojection on idempotent replay at `service.py:62–65`): creation, listing and replay use the actor-aware experience projection. A corrected actual retains its exact historical reference and recorded account with `actual_status=historical`, `state=review_required` and explicit review/source markers. It is not silently rebound to a replacement actual. Lost resource/original permission or stale originals redact experience prose; loss of current learner access denies retrieval. Executed tests cover actual correction, strongly retained cached actual/permission objects, native original replacement, resource withdrawal and idempotent replay after permission loss. The independent original absence-correction scenario now returned the required historical/review state on both databases, including replay. A second authorized actor could initially read shared history, then lost the experience prose after their own original-source grant was revoked, and received 403 after their pupil assignment was revoked. An independently added pending-actual edit returned `dependency_pending` while leaving the dirty ORM value untouched. The stored experience text and exact historic attribution remained retained.

### Commands and results

Set the assigned isolated synthetic PostgreSQL URL in `SPESPED_TEST_POSTGRES_URL` and use these absolute imports:

```sh
# Working directory: /Users/lauritz/Programming/SpesPed/var/review-j09/recheck-c5bf1ec
PYTHONPATH=/Users/lauritz/Programming/SpesPed/var/review-j09/recheck-c5bf1ec/backend:/Users/lauritz/Programming/SpesPed/var/review-j09/recheck-c5bf1ec/backend/tests \
  /Users/lauritz/Programming/SpesPed/backend/.venv/bin/python -m pytest \
  backend/tests/test_curriculum.py backend/tests/test_curriculum_composition.py -q

# Working directory: /Users/lauritz/Programming/SpesPed
PYTHONPATH=/Users/lauritz/Programming/SpesPed/var/review-j09/recheck-c5bf1ec/backend:/Users/lauritz/Programming/SpesPed/var/review-j09/recheck-c5bf1ec/backend/tests \
  backend/.venv/bin/python -m pytest var/review-j09/test_recheck_j09.py -q -s
```

- Frozen repaired implementation/composition suite: **46 passed, 2 skipped**, 64.00 seconds. Both skips are explicitly PostgreSQL-only concurrency tests' SQLite instances. Both PostgreSQL races ran.
- Independently authored recheck probes: **12 passed**, 17.21 seconds. All six scenarios ran on SQLite and PostgreSQL; the original defect probes now assert corrected behavior. Four earlier adverse checks also remain green: original-authority revocation on replay/cross-school denial, source-recall variant traversal with caller rollback/deduplication, retained-license narrowing/loss of old sharing, and inconsistent inventory availability rejection.
- The changed static migration's model/metadata alignment, empty downgrade/upgrade roundtrip, retained-data downgrade refusal and preservation of retained rows passed on both databases. The partial active-choice uniqueness constraint was verified against the actual migrated schemas.
- Final logs and evidence: `var/review-j09/recheck-baseline.log`, `var/review-j09/recheck-independent.log`, `var/review-j09/recheck-pin.log`, and `var/review-j09/test_recheck_j09.py`.
- The same two nonfatal warnings remain: Starlette/httpx TestClient deprecation and Pydantic's `copy` field-name shadowing.
- All reviewer-owned execution sessions completed. Synthetic fixture teardown ran for the unique PostgreSQL schemas; no global cleanup or demo database access occurred. No commits, pushes, subagents or external messages were used.

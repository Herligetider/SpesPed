# J06 independent backend review

**Latest disposition (repair pin `f5c7e883733d05c8b0d2ca6a7e4ea3938ffda4f0`): original J06-R1–R5 closed; J06-R6/R7 open. Candidate remains unaccepted.** See the appended repair recheck. The original review below is retained as historical evidence.

Reviewed 21 October 2026. **Not accepted: five actionable findings remain.**

## Pin, scope and method

Reviewed `e80380cdf7da10431c18685969351c9b0cf07e48`, implemented by
`/root/j06_teaching`, independently in the ignored archive
`var/review-j06/`. This includes the 12 files in that commit: the six teaching
module files, plans/entitlements projection ports, teaching migration, migration
model registry, fixtures and tests. Read `AGENTS.md`, all of F12/F13/F15/F16/F39,
`docs/08-first-workflow-review.no.md` and `docs/09-domain-implementation.en.md`.
No production files, shared contracts, commits or pushes were changed by this review.

All Python execution used `/Users/lauritz/Programming/SpesPed/backend/.venv/bin/python`
and explicit absolute
`PYTHONPATH=/Users/lauritz/Programming/SpesPed/var/review-j06/backend:/Users/lauritz/Programming/SpesPed/var/review-j06/backend/tests`,
overriding the editable installation. PostgreSQL used the specified synthetic test
database at `127.0.0.1:55432/spesped_test`, with unique disposable schemas only;
`spesped_demo` was not used. Data and loopback model responses were synthetic.

## Findings

### J06-R1 — P1: historical follow-up prose inherits a replacement session's permissions

Location: `backend/spesped/contexts/teaching/service.py:761–763`, also
`models.py:183–192` (`TeachingFollowUp`).

A session follow-up stores only the session aggregate ID. Its free-text resolution
is authorized against `current_revision(db, parent)`, so a later independently
written revision silently changes the dependencies protecting the old resolution.

Reproduction on SQLite and PostgreSQL (`review_probes.py::test_repaired_session_resurfaces_retired_source_followup_resolution`):

1. Save a session whose basis includes evidence. Remove the actor's `evidence.read`
   assignment while retaining teaching access; reading the session creates the
   owned `basis_changed` follow-up.
2. Restore source access and resolve the follow-up with a statement derived from
   that source. Revoke source access again: the follow-up list correctly masks
   `resolution` as `null`.
3. Create a new basis without that evidence and save a manual session revision.
   The same historical resolution now appears in the learner follow-up list,
   with `source_status: current`, although source permission remains revoked.

The old session revisions remain protected; this associated historical prose does
not. Bind the resolution/impact to its original exact revision and dependencies,
and retain that protection after current session content is replaced. Include
source/model/goal recall and permission revocation regression cases.

### J06-R2 — P2: absence can acquire delivered staff-time entitlement minutes

Location: `backend/spesped/contexts/teaching/schemas.py:158–165`,
`service.py:453–467`, `service.py:703–706`.

`Participation.actual` requires zero learner minutes for absence but permits
positive `attributed_staff_minutes`. The service only checks the allocation against
staff totals; the summary counts it as recorded support against the exact provision.

Reproduction on both databases
(`test_absent_learner_stafftime_is_counted_as_support`): confirm a personal-assistance
provision counted by staff time; submit one absent learner with `minutes: 0`,
`attributed_staff_minutes: 30`, and 30 assistant staff minutes. POST succeeds with
`state: delivered`, no cause or owned deviation follow-up. The learner summary
reports zero category minutes but **30 recorded minutes against the provision**.

Keep actual staff resource expenditure separate from delivered support for an absent
learner. Reject positive delivered allocation for absence, and preserve absence/
cancellation/deviation semantics rather than allowing an all-absent delivery to
bypass the cause/follow-up checks. The summary's `entitlement_fulfilment: unassessed`
label does not correct the misleading recorded-support quantity.

### J06-R3 — P2: assistant-only work can be counted as individually adapted education

Location: `backend/spesped/contexts/teaching/service.py:458–462`,
`schemas.py:168–172`; `validate_owner` at `service.py:273–277`.

Actual staffing checks only active school membership. It permits an assistant and
accepts the caller's free-text role/category without checking the distinction
between teaching responsibility and assistant support.

Reproduction on both databases
(`test_only_assistant_staff_can_be_classified_as_ito`): use a confirmed exact ITO
provision whose recorded organization/competence require a professional teacher;
submit 30 learner ITO minutes and the sole staff row with the fixture's actual
`assistant` account, role `Assistant`, category `individually_adapted_education`.
The API returns 201 and persists it against that provision, with no pedagogical
staff row or clarification state. This directly bypasses F15's requirement not to
equate assistant minutes with ITO teaching.

Validate the recorded staffing/support distinction and applicable basis before
counting a delivery as ITO. Preserve uncertain or incompatible staffing as an
explicit deviation/unassessed item; a supplied category or role string cannot
establish the required teaching staffing.

### J06-R4 — P2: assistant input can be reconciled against a superseded actual record

Location: `backend/spesped/contexts/teaching/service.py:741–748`.

The reviewer resolves the current delivery aggregate but compares input against any
supplied historical `DeliveryRevision`. It never requires that revision to be the
aggregate's current revision.

Reproduction on both databases
(`test_actual_input_can_reconcile_superseded_delivery`): submit assistant input for
30 minutes; record the corresponding actual delivery; correct that delivery to
cancelled/absent with zero minutes. Review the still-submitted input as `recorded`
using the original revision ID. The API succeeds and displays `state: recorded`
although the actual record now explicitly cancels that delivery.

Require the current exact actual revision for reconciliation, and make later
corrections invalidate or reopen an existing reconciliation as appropriate. Preserve
the historical review, but distinguish it visibly from current reconciled delivery.

### J06-R5 — P2: learner delivery listing repeats one event for each support category

Location: `backend/spesped/contexts/teaching/router.py:178–179`.

The join to `LearnerParticipation` selects one `SessionDelivery` row for every
matching learner/category row without deduplication. Python pagination and `total`
then count those duplicates.

Reproduction on both databases (`test_multicategory_delivery_list_duplicates`):
record one actual event with ordinary teaching and personal assistance for the same
learner. `GET /learners/{id}/teaching-deliveries` returns the same delivery ID twice
and `total: 2`. Each item already includes both categories, so this is duplicate
activity rather than a category-level projection. Deduplicate actual deliveries
before counting/pagination; verify a mixed-category event occupies one list slot.

## Verification evidence

- Pinned `backend/tests/test_teaching.py` with actual PostgreSQL enabled:
  **23 passed, 1 skipped**, 37.93 s. The skip is the SQLite instance of the explicit
  PostgreSQL concurrency test. Log: `var/review-j06/baseline.log`.
- Independent adverse/contract probes: **14 passed**, 18.88 s, seven probes on both
  database engines. Five probes assert the defects above remain reproducible;
  these are evidence of defects, not acceptance tests passing a corrected system.
  The other two verify the existing evidence-write constraint and rejection of
  an unknown generated source reference. Files:
  `var/review-j06/review_probes.py`, `var/review-j06/probes.log`.
  Desired-behavior versions are retained separately in
  `var/review-j06/review_acceptance_probes.py`; they fail the ten defect cases
  (five findings × two engines) at this pin, with the four boundary-contract
  cases still passing. Log: `var/review-j06/acceptance-probes.log`.
- SQLite and PostgreSQL migration checks: upgrade to `j06_teaching`, compare **all
  eight context model modules** to the actual schema, downgrade to
  `b4_integrate_comparison_basis`, and upgrade again. Both produced **18 teaching
  tables, zero merged metadata differences**, and successful roundtrips.
  Files: `var/review-j06/review_migrations.py`, `var/review-j06/migrations.log`.
- Rerun baseline/probes from the archive with the absolute `PYTHONPATH` above and
  `SPESPED_TEST_POSTGRES_URL` set to the assigned synthetic PostgreSQL URL:
  `.../backend/.venv/bin/python -m pytest backend/tests/test_teaching.py -q` and
  `.../backend/.venv/bin/python -m pytest review_probes.py -q -s`.

The passing baseline exercises persistent HTTP single/group planning, manual
fallback, exact review/approval, separately reviewed and dated briefs, assistant
questions/teacher answers, actual input reconciliation, independent learner/staff
quantities, corrections/cancellation, scoped learner projection, short observation
correction and next-basis reuse. It includes actual PostgreSQL revision races,
same-key delivery replay, stale follow-up uniqueness and rollback checks.

The real loopback OpenAI-compatible model protocol runs through the actual gateway
and teaching-basis resolver: typed `session_planning` output, exact source
references, field selection/diff, regeneration retaining manual edits, replay,
model recall, assistant redaction and independent field replacement are exercised.
The independent unknown-source probe fails the job with
`unsupported_source_reference`, leaves output unavailable, and preserves manual
session content. No external AI was called. Model quality and production deployment
were not assessed by this synthetic protocol exercise.

## Ports, side effects and remaining limits

- Inspected new `plans.projections` and `entitlements.projections` predicates:
  they select explicit metadata columns, return no source prose, and contain no
  commit/audit mutation. Goal checks include active exact plan/goal identity,
  digest, dates, source bindings and decision/provision bindings; profile checks
  include exact confirmation/version/source metadata. The curated assistant path
  uses these after its dated assignment authorization and does not grant evidence
  dossier access. Full actor-aware reads remain required for pedagogical source use.
- Gateway `current_job` is called inside the teaching command transaction and does
  not commit/audit independently. Its separate broad gateway/freshness review is
  not duplicated or accepted here.
- Teaching `session_view`, `brief_view` and `assignment_view` are **not pure read
  ports**: stale projections can create follow-up/audit/outbox rows, and HTTP GET
  handlers commit via `read`/`mutate`. Service consumers must own that transaction;
  there is no claim that these projections are side-effect free. Concurrent stale
  reads are covered by the PostgreSQL baseline.
- Source reuse still needs **`evidence.write`** because `depend()` calls the
  existing evidence `register_derivative` API. An independent probe retained
  evidence read + teaching write but removed evidence write: basis read remained
  available and session creation returned 403. This is an existing cross-context
  constraint, not an ideal completed product flow or a permission implicitly
  granted by the new metadata predicates.
- The pinned root application does **not register the teaching router**. Tests
  explicitly include it. Root J05/J16 composition (parent `30fe563`) and gateway
  `6c96cef` are separate review subjects, not intrinsic acceptance of this J06
  candidate. This review makes no browser/UI or whole-feature completion claim.
- J04 timeline composition and J09/J15/J25 integrations remain required. F12/F13/
  F15/F16/F39 also retain UI, assistant comprehension and one-minute-log usability
  checks, school configuration and the later catalogued integrations. Dictation,
  full scheduling/resource reconciliation, actual model professional quality and
  real pupil data were not exercised.

No legal registry, law, practitioner validation or production readiness was newly
verified by this code review. Resolve and independently reverify J06-R1–R5 before
accepting this bounded backend candidate.

## Repair recheck — f5c7e883733d05c8b0d2ca6a7e4ea3938ffda4f0

Rechecked independently on 21 October 2026 in ignored
`var/review-j06-repairs/`. Inspected all eight repair paths: teaching models,
router, schemas, service, new qualification port, fixtures/tests and forward
`j06_teaching_repairs` migration (parent `j06_teaching`). Python used the existing
backend venv with explicit absolute
`PYTHONPATH=/Users/lauritz/Programming/SpesPed/var/review-j06-repairs/backend:/Users/lauritz/Programming/SpesPed/var/review-j06-repairs/backend/tests`.
SQLite and the assigned synthetic PostgreSQL test database were both exercised;
PostgreSQL fixtures and migration probes used unique disposable schemas. No
production code, commit or push was changed by this review.

### Original findings: closed at this repair pin

| Finding | Recheck result |
|---|---|
| R1, historical follow-up prose | Closed. Exact immutable revision/basis bindings protect historical resolutions after independent replacement. Source correction/permission withdrawal, goal replacement, model recall and policy recall tests include response/replay redaction. Legacy unknown lineage remains unavailable. |
| R2, absence counted as delivered support | Closed. Positive absence allocation is rejected. Absence can still record separate actual staff expenditure in a partial record with cause and owned follow-up; delivered entitlement quantity remains zero. |
| R3, assistant-only ITO counting | Closed for the reviewed boundary. Unconfigured qualification is unavailable; roles, grants and caller labels do not prove competence. Assessed ITO requires an exact reviewed qualification/responsibility binding. Actual claimed work remains recordable as unassessed with an owned deviation. The separate interval defect R6 below remains open. |
| R4, superseded reconciliation | Closed. New review requires the exact current eligible delivery. Correction invalidates recorded reconciliation and opens follow-up; re-review appends immutable history. PostgreSQL correction/review serialization passes. |
| R5, duplicate learner delivery listing | Closed. Deduplication precedes pagination/counting; mixed-category events occupy one slot. |

The original retained `review_acceptance_probes.py` is byte-for-byte unchanged
(SHA-256 `a92c2a50253a9bdd94a3a8b3b56312f76e4e2e4162f4ef8c333eaf1ae8148da0`).
It passes all **14** cases on this pin, including the five original desired
behaviors on both engines and the two retained boundary-contract probes.

### J06-R6 — P2 open: qualification coverage checks only the start of delivered support

Locations at this repair pin:

- `backend/spesped/contexts/teaching/ports.py:64–68` checks
  `effective_from <= occurred_at < effective_until`.
- `backend/spesped/contexts/teaching/service.py:505–509` then credits all recorded
  staff minutes; `service.py:539–543` repeats that full-minute assumption at reads.

Independent probe
`review_repair_adverse.py::test_qualification_expiry_mid_delivery_is_counted`
reproduces this on SQLite and PostgreSQL. A trusted synthetic port returns an exact,
reviewed, sourced responsible-teaching qualification for the requested staff,
learner and provision, but its effective period ends **one minute after occurrence**.
A 30-minute ITO delivery is accepted with HTTP 201, its participation is shown as
`support_assessment: assessed`, and the provision summary reports **30 assessed
recorded minutes**.

The request has no end/duration binding, and neither consumer check limits credited
minutes to the qualified interval. Require reviewed coverage for the recorded
support interval, with the exact interval in the request/binding as needed; check
it again in historical/current projections and summaries. Insufficient coverage
must not establish assessed ITO minutes. Unassessed actual expenditure and an owned
deviation should remain recordable. Do not infer continuous coverage from one
valid instant or manufacture qualification from role/access grants.

### J06-R7 — P2 open: permitted downgrade loses legacy reconciliation recovery state

Locations:

- `backend/migrations/versions/j06_teaching_repairs.py:56–58` preserves a legacy
  latest review and invalidates recorded input linked to superseded delivery.
- The downgrade guards at `:71–74` omit `invalidated_by_revision_id`, then drop it
  at `:77–79`.
- `backend/spesped/contexts/teaching/service.py:866` permits re-review of an
  invalidated entry only while that token is present.

Independent reflected-table probe
`review_repair_adverse.py::test_legacy_invalidation_is_lost_through_permitted_roundtrip`
reproduces this on both engines:

1. Seed the pre-repair schema with an assistant input marked recorded against an
   earlier delivery revision, while the same delivery has a newer current revision.
2. Upgrade. The migration correctly changes it to `needs_clarification` and binds
   `invalidated_by_revision_id` to the current delivery. Its legacy review has
   `reviewed_at: null`, preserving the unknown timestamp.
3. Downgrade is allowed: there are no new frozen follow-ups, qualification bindings
   or timestamped reviews. This drops the recovery token but leaves the input's
   state as `needs_clarification`.
4. Reupgrade leaves the token null because backfill only selects `state = recorded`.
   A new review against the eligible current actual revision now returns 409,
   claiming that the entry has already been reviewed. The previously possible
   recovery path has been lost.

Either preserve/reconstruct the invalidation and immutable review provenance
through a supported roundtrip, or explicitly refuse the downgrade before discarding
that state. Empty-schema roundtrips are insufficient to prove safe rollback.

### Recheck verification and limits

- Full pinned teaching suite plus unchanged original desired probes:
  **66 passed, 2 skipped**, 104.46 s. The skips are the SQLite instances of the
  PostgreSQL concurrency tests. Command from the repair archive:
  `.../backend/.venv/bin/python -m pytest backend/tests/test_teaching.py review_acceptance_probes.py -q`,
  with the absolute repair `PYTHONPATH` above and assigned
  `SPESPED_TEST_POSTGRES_URL`. Log: `var/review-j06-repairs/baseline.log`.
- Independent additional probes: **6 passed**, 7.61 s. Four reproduce R6/R7 across
  both databases. Two verify that an injected failure after reconciliation
  invalidation rolls back delivery revision, input state/version, command,
  follow-up, outbox state and review history together; the exact
  same-key correction retry then succeeds once and replay creates no second
  revision/history. Files: `review_repair_adverse.py`, `adverse.log` in the repair
  archive.
- Desired-behavior R6/R7 probes are retained separately in
  `var/review-j06-repairs/review_repair_acceptance.py` and
  `repair-acceptance.log`: **4 expected defect-case failures, 2 passing atomicity
  cases**, 8.31 s. The R7 guard accepts either explicit downgrade refusal
  or preserved state with successful current-record re-review.
- Independent full-head migration/metadata check on both engines:
  **19 teaching tables, zero merged model/schema differences**, empty downgrade
  to `j06_teaching` and reupgrade succeed. This includes all eight model modules
  and both migration heads (`j05_plan_generation`, `j06_teaching_repairs`). Files:
  `var/review-j06-repairs/review_migrations.py`, `migrations.log`. Legacy unknown
  follow-up fail-closed behavior and refusal to discard new frozen history are
  also covered by the pinned tests; R7 identifies the additional populated case.
- Inspected the qualification port's exact school/learner/staff/decision revision/
  provision/digest/occurrence equality, reviewed responsibility/source requirements,
  fail-closed default and recall recheck. The fixture adapter is synthetic;
  **no production qualification adapter is delivered or accepted** here.
- Inspected `revision_valid` preference for temporary `ai_gateway_runtime`, ahead
  of teaching/plans fallback runtime. This avoids selecting a stale outer runtime
  during nested worker lineage checks. Root's accepted typed gateway `8d82b74`
  and the separate J05 consumer `2ccc30e` are not independently reaccepted here.
- Root application registration/joined integration work, including later
  composition candidate `ae44969`, is outside this exact repair pin and review.
  No browser/UI, complete J06, practitioner usability or production readiness
  claim is made. Earlier integration, evidence-write and local-model quality
  limits remain in force.

**Disposition: original J06-R1–R5 closed; J06-R6 and J06-R7 require repair and
independent recheck before this bounded backend candidate is accepted.**

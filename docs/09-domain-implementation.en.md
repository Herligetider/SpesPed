# Domain implementation contracts

Version 0.3 · 21 October 2026. This extends the complete strategic/tactical model in
[the domain model](04-domain-model.en.md). All 40 feature specifications remain
binding. These decisions make parallel implementation concrete; they do not
replace practitioner validation or school-specific legal configuration.

## Architecture and ownership

Use a modular monolith with explicit context modules under `backend/spesped/contexts/`.
Domain value objects and policies live under `backend/spesped/domain/` and remain
independent of HTTP, database sessions and AI clients. Application services own
transactions. SQLAlchemy models and migrations use explicit context-owned tables,
not one generic JSON record table masquerading as the entire domain.

PostgreSQL is the production database. SQLite may run deterministic unit/service
tests, but must not be the sole evidence for isolation, reservation concurrency,
outbox claims or production migrations. Object files use a storage port with
protected local storage initially; metadata and access checks remain in the database.
React/TypeScript is a separate client in `web/`. All development data is synthetic.

| Context/module | Aggregate roots and typed work | Required integration contracts |
|---|---|---|
| BC01 `identity` | School, UserAccount, LoginSession, SchoolMembership, Enrollment, StaffAssignment, AuthorityGrant, GuardianRelationship | Actor context, school/learner access, current recipient relationships |
| BC02 `evidence` | SourceItem, SourceRevision, ExtractionProposal, EvidenceItem, EvidenceRevision, CorrectionImpact | Authorized evidence query, source references, correction events |
| BC03 `governance` | RequirementDefinition/Version, RuleProfile, ObligationInstance, ComplianceDeviation, WorkloadStudy, StatutoryExport | Applicable rule versions, task owner/deadline, unresolved inputs |
| BC04 `entitlements` | SupportCase, Referral, EducationConsent, ExpertAssessment, EducationDecision/Provision, ExemptionDecision, AppealCase | Confirmed typed entitlement, authority and effective period |
| BC05 `plans` | LearnerSupportProfile, IndividualEducationPlan, PlanRevision, LearningGoal, Adaptation, PlanContribution | Effective goal versions and approved teaching scope |
| BC06 `curriculum` | CurriculumScheme, AssessmentScheme, ClassLearningPlan/ThemePeriod, TeachingResource/Revision, MaterialCatalogItem | Current class context, licensed resources, reservable materials |
| BC07 `teaching` | TeachingSessionPlan/Revision, AssistantBrief, SessionDelivery, LearnerParticipation, StaffParticipation, DeliveryObservation, ProposalReview | Actual delivery versus intent, goal-linked observations |
| BC08 `scheduling` | ResourceCalendar, StaffCapacity, AcceptedGroup, ConstraintSet, SchedulePlan/Revision, Reservation | Conflict-checked resource commitments and coverage |
| BC09 `assessment` | AssessmentInstrument, AssessmentAdministration/Result, ProgressReview/GoalFinding, AssessmentStatement | Typed scores, grounded progress, human-finalized judgements |
| BC10 `documents` | DocumentCase/Revision, EvidenceSnapshot, ContentApproval, EmailDraftSchedule/Run | Frozen reviewed content and evidence manifest |
| BC11 `communication` | DisclosurePackage, RecipientAuthorization, Dispatch/Attempt, DeliveryReceipt, PortalAccessGrant | Exact-package delivery, current rights, receipt reconciliation |
| BC12 `collaboration` | CollaborationCase, Meeting, ActionItem, IndividualSupportPlan, AttendanceEpisode/Entry/FollowUp | Restricted participant projections, actual contacts/actions |
| BC13 `safeguarding` | SchoolEnvironmentCase/Investigation/ActionPlan, PhysicalInterventionRecord, ConcernReport | Explicit case permissions, alternative notification routes |
| BC14 `records` | RightsRequest, ManagedRecord, RetentionPolicy, LegalHold, DispositionDecision, ArchiveTransfer, TransferCase/Package | Record lifecycle, verified receipts, derivative disposal |
| BC15 `platform` | GenerationJob/Attempt, ModelRelease/Evaluation, ProcessingPolicy, RecoveryExercise, OperationalIncident | Approved providers, local-only enforcement, recovery evidence |
| BC16 `integrations` | IntegrationConnection, ExternalMapping, ImportBatch, ReconciliationIssue, ExportBatch | Scoped source ownership, versioned adapters, retry outcomes |

F37 has concrete administrative work types under governance: AdmissionCase,
TransportFollowUp, SFOFollowUp, EnvironmentInspection, QualificationCheck,
InsuranceReview, ProcurementCase and PrivateSchoolGovernanceReview. Each has a
typed checklist, owner, applicability decision, evidence and external system
reference. These are not an invented payroll, clinical or accounting system.
Every enabled area needs a usable workflow; an unchecked generic task is insufficient.

## Shared primitives and invariants

Use opaque UUIDs for identifiers. Every tenant-owned table carries `school_id`;
references are checked in the same school and meaningful learner/case scope.
Store UTC-aware instants and a school's IANA timezone. Store occurrence and entry
times separately. SummaryPeriod accepts inclusive local dates and resolves to a
half-open interval using each date's first real instant. A skipped midnight moves
to the transition instant; a repeated midnight uses its earlier occurrence. A
range containing no real instants is rejected. Recurrences skip wholly nonexistent
dates, while explicit occurrence/entry instants still reject nonexistent wall times.

`EffectivePeriod`, `SourceReference`, `EvidenceAttribution`, `DurationMinutes`,
`EntitlementQuantity`, `AssessmentScore`, `ApprovalBinding`, `RecipientScope`,
`DraftRecurrence` and `ApplicabilityResult` are explicit validated types. The
domain model defines their meanings. `EntitlementQuantity` requires an exact
`DecisionProvisionReference(scope, decision_id, decision_revision, provision_id)`;
addition checks that identity as well as period, category, clause and counting basis.
A textual clause label does not identify a decision or an individual entitlement.
Do not coerce a missing amount into zero,
an unknown right into permission, or a missing observation into a progress finding.

An aggregate has `id`, `school_id`, `version`, creation/update instants and explicit
state. Every non-append-only update uses an expected version; stale updates return
a conflict. Source corrections never rewrite a past official record silently.
Teaching plan approval and document disclosure approval are different decisions.
Content hashes use canonical serialized content and include relevant attachments.

Transactions persist state, necessary audit metadata and outbox events together.
Audit records store actor/action/target/time/outcome, not duplicated pupil prose.
Jobs reauthorize current access at execution, and enforce unique logical request
keys. An uncertain external outcome is reconciled before any new send attempt.

One-off email drafting uses `ManualDraftRequest(scope, period, requested_at,
logical_request_key)` and needs no schedule or activation. Retry the same logical
command with the same key; use a fresh key for a deliberately new request. Its
`request_digest` detects conflicting reuse of a key with a changed period. The
application must include additional semantic command fields (purpose, topic selection,
language and recipient scope where relevant) in its durable request fingerprint.
Schedule-bound `DraftRequest` instead deduplicates schedule/revision/subject/period.
Automatic selection skips a run whose calendar summary contains no real instants
and advances within the unchanged cadence and end-date bounds. Manual empty
periods and all other validation errors remain explicit errors.
Neither request type authorizes sending. Durable uniqueness, current authorization
and duplicate-payload conflict handling belong to the application service.

## Authentication and access contract

Use server-validated opaque cookie sessions backed by hashed session tokens.
Passwords use a modern password hash. Mutating cookie-authenticated requests need
a CSRF token and allowed origin checks. Cookies are HttpOnly/SameSite; Secure is
required in production. Do not enable real-data use through a public demo login.

`Actor` represents a validated user, never input headers. Membership grants school
entry; an active learner assignment or explicit scoped authority grants pupil
access. A technical administrator can manage infrastructure without reading pupil
content. Case grants are independent of learner-team access. Signing authority is
explicit and dated. An assistant sees the assigned brief and necessary observation
input, not the whole evidence dossier. Guardians receive only approved packages.

Professional records in the supporting `administration` module extend BC01's
staff and authority responsibilities; they do not introduce another bounded
context. Immutable qualification, pupil responsibility and subject-policy
revisions support separately attributed human reviews. A recorded external HR
reference is explicitly human-checked: storing its identifier, version and digest
does not establish a live connection to the issuing system.

BC07's `QualificationReadPort` binds the exact person, pupil, decision provision
and whole actual teaching interval. BC09's `AssessmentAuthorityPort` binds the
person, pupil, purpose, exact instrument/result/statement revision and digest,
and complete assessment period. Subject completion, exemption and grading policy
need their own reviewed sources. Neither adapter grants access or derives
competence from a job title. Curated eligibility metadata and private personnel
evidence use separate permissions. A later withdrawal makes current eligibility
unresolved while retaining the original human review and actual-work history.
Native owner readers recheck authority and source revisions, and refuse pending
dependency edits without flushing, committing, rolling back or replacing the
caller's staged data. These contracts need their own implementation review;
they do not establish complete school administration or legal compliance.

Curated projections can call
`evidence.projections.confirmed_binding_is_current(db, school_id, learner_id,
evidence_id, evidence_revision, link_id)` after authorizing their own projection.
The port returns only a boolean for the exact confirmed evidence/link/original
revision. It cannot authorize source prose, review reasons, history or original
documents; those still require the evidence service's actor-aware access checks.
Contexts must not replace full source authorization with this metadata check.

Teaching session generation has its own `session_planning` purpose and
`ai.session_planning` authority. A request references exactly one immutable
`teaching_basis` for the authorized learner. The teaching context validates its
current goals, sources and support context; application assembly adds any explicit
operator-owned synthetic provenance attestation. The reviewed template and output
schema are both `teaching-session.v1`. The output contains practical session
content, exact supplied source references and missing-evidence notes, and always
remains unconfirmed pending professional selection and approval. This distinct
template does not invalidate existing evaluated suggestion/intake template digests.

Consumers use `platform.current_job(db, actor, school_id, job_id, runtime,
lock=False)` to validate the current source and processing binding inside their
own transaction. It does not commit or write an audit record; the consuming
command owns its business change and audit/outbox. `platform.job_binding_is_current
(db, school_id, job_id, runtime)` is a metadata-only boolean for an existing
successful job's policy, reviewed release/evaluation and configured provider.
It selects no job output and does not resolve source prose. Only a previously
authorized curated projection may use it, and that projection must separately
check its exact learner/source/goal dependencies. A true result never grants
permission to read sources or confirms factual accuracy. Remote development
provenance must still match a current operator attestation. Both ports fail
closed when the relevant runtime or processing binding is unavailable.
The metadata predicate preserves pending caller edits and deletions. It returns
false for a binding with pending changes until the owner explicitly flushes or
rolls them back; it neither flushes nor refreshes those ORM objects.

This bounded gateway was independently accepted at `ac55549`; see the
[gateway review](reviews/teaching-gateway-review.md).
The teaching consumer, application route composition and UI require their own
verification; this contract does not declare the complete teaching flow delivered.

IEP proposal generation uses the separate `iep_drafting` purpose and
`ai.iep_drafting` authority. It accepts exactly one immutable `plan_basis`
reference at revision 1. The plans context's
`resolve_generation_source(db, actor, school_id, learner_id, purpose, reference)`
authorizes and rechecks the original confirmed decision, assessment, profile,
source and target-plan/goal coordinates before returning canonical JSON in a
`SourceInput` with `text/plain` media type. The gateway content digest binds that
input; a caller cannot provide a trusted digest or synthetic provenance flag.

Both the distinct template and schema are `iep-draft.v1`. Required nullable plan
fields are title, rationale, organization, responsibility and evaluation method;
null means no proposal. The required goals list has at most 20 entries with a
unique proposal key, nullable exact target goal ID and bounded proposed title,
expected action, arena, support, responsibility and evaluation method. Non-null
target IDs must be unique. The plans consumer validates target IDs against the
original immutable basis before presenting or applying proposals. At least one
nonnull plan field or goal is required, with unique supplied source references
and an explicit missing-evidence list. Dates, quantities, rights, curriculum
references, participation and approval fields are excluded from model output.
New goal dates and curriculum choices come from explicit human input.

Plans routes supply `db.info['plans_runtime']` from the assembled AI gateway.
While resolving a source, the gateway also binds its trusted current runtime to
`db.info['ai_gateway_runtime']`, restoring the previous session entry in a
`finally` block. Nested source validators prefer that binding over their route
fallbacks. This lets a fresh worker session recheck generated ancestor plans and
teaching observations against the same processing configuration used for the
current job; it does not grant source access or skip any authorization check.
Selection, regeneration, rejection and activation remain separate commands;
per-field model lineage survives ordinary manual edits until an explicit human
replacement severs the selected dependency. Standalone adaptation generation
and curriculum integration remain recorded F08 work. The typed gateway boundary
was independently accepted at `8d82b74`; see
[the IEP gateway review](reviews/iep-gateway-review.md). The plans consumer at
`2ccc30e` and the combined teaching workflow require separate independent review.

Teaching routes obtain the configured optional `QualificationReadPort` from
`app.state.teaching_qualification_port`. Each request binds school, learner,
staff member, exact decision revision and provision digest, and the actual
half-open event interval `[occurred_at, ended_at)`. The required end is strictly
after occurrence and comes from the recorded event duration. Without recorded
staff placement inside the event, the proof must cover the whole interval.
A `reviewed_current` result includes effective dates, responsible teaching status,
an identified reviewer and versioned source references. Effective dates must
cover both interval boundaries, and reads recheck the same exact binding.
Legacy bindings without an end remain unassessed until explicitly corrected.
Missing configuration
returns `unavailable`; caller role labels and permissions cannot establish
qualification. Actual work can still be recorded as unassessed with a cause and
owned follow-up, separately from assessed support and entitlement comparisons.
The production qualification source belongs to the remaining J19 work. This
teaching repair contract at `da503e1` is independently accepted in the bounded
[J06 backend review](reviews/J06-review.md); the complete UI and real adapter
remain unfinished.

The independently reviewed read port
`governance.projections.case_requirements(db, actor, school_id, learner_id, case_id)`
requires governance case authority, the owning context's live case resolver and
each obligation's current detailed-access check. It returns only authorized
recorded obligations, with separate profile/rule identity, digest, state and
version, applicability, unresolved inputs and recorded deadlines. Generic required
actions and document types are actionable only for current, resolved, applicable
rules; the port never classifies a generic action as a notification. Multiple
source profiles remain distinct. Empty/inaccessible sets are unavailable, and
legal completeness is always unassessed. Reading creates or fulfills no task.
The bounded read port was independently accepted at `30c656f`; see
[the review](reviews/protected-rule-projection-review.md). The application
registers a safeguarding adapter that preserves each recorded
obligation's source, applicability, deadline and review state. Its strict context
type rejects contradictory review/actionability claims. Missing or denied optional
governance context yields an unavailable projection after the owning case's access
check, so otherwise authorized case detail and manual urgent work remain usable.
This never grants case access or marks a duty fulfilled. Plans/entitlements and
safeguarding routes, the evidence-to-goal validator, the protected case resolver
and exact current snapshot validator are also registered by application assembly.
This bounded composition was independently accepted at `30fe563`; see the
[composition review](reviews/composition-review.md). UI and reviewed school
configuration remain required.

Foundation public Python contracts:

- `spesped.db.Base`, `get_db()` and `make_session_factory(database_url)`.
- `spesped.auth.Actor` with `user_id`; `get_actor()` resolves the validated session.
- `require_school_access(db, actor, school_id)` returns the active membership.
- `require_learner_access(db, actor, school_id, learner_id, action='read')` performs
  a current scope check; helpers raise the common access error.
- `require_authority(db, actor, school_id, action, learner_id=None, case_id=None)`
  validates explicit dated authority; staff role labels alone are insufficient.
- `spesped.errors.DomainError(code, message, status_code=400)` for safe errors.
- `spesped.audit.record_audit(db, actor, school_id, action, target_type, target_id)`
  participates in the caller's transaction without committing independently.
- Context routers export `router`; orchestrator owns final router registration.

If implementation reveals a necessary contract change, agree it explicitly and
update this document before parallel callers assume a different interface.

## Initial HTTP contract

All business endpoints use `/api/v1/schools/{school_id}/...`. JSON fields use
`snake_case`. List responses use `{items: [...], total: number}` and bounded
pagination. Errors use `{error: {code, message}}`; field validation can carry a
safe `details` list. Access errors must not disclose hidden resource existence.

| Endpoint | Request / successful response |
|---|---|
| `GET /api/v1/health` | `{status: 'ok'}`; no secret/configuration dump |
| `POST /api/v1/auth/login` | `{email, password}` → user, csrf_token, schools; sets session cookie |
| `GET /api/v1/auth/me` | `{user: {id, email, display_name}, csrf_token, schools: [{id, name, kind, timezone, role}]}` |
| `POST /api/v1/auth/logout` | CSRF protected; revoke session; 204 |
| `GET /api/v1/schools` | Current user's active memberships, list envelope |
| `GET /api/v1/schools/{id}/learners` | Only authorized pupils; `{id, display_name, grade, group_name, version}` in list envelope |
| `POST /api/v1/schools/{id}/learners` | `{display_name, grade, group_name}`; explicit authority; validated grade 1–10 |
| `GET /api/v1/schools/{id}/learners/{learner_id}` | Authorized profile, no implicit protected case access |
| `PATCH /api/v1/schools/{id}/learners/{learner_id}` | Allowed changed fields and `expected_version`; 409 on stale version |

Subsequent modules add typed commands rather than a universal unvalidated PATCH.
For raw intake file uploads and replacement revisions, browser clients percent
encode the UTF-8 filename in `X-Evidence-Filename` and set
`X-Evidence-Filename-Encoding: percent`. The server decodes once and validates the
plain filename; the absent encoding header retains legacy literal filenames.
`X-Evidence-Metadata` uses ASCII-escaped JSON with the same typed field limits and
a 16 KiB transport bound. Invalid encodings must fail before source persistence.
`GET .../intake/assignees` accepts `query` (up to 100 characters), `offset` and
`limit` (1–100), returning `{items: [{id, display_name}], total}` for currently
authorized school-wide intake staff. Reading the list requires intake authority;
assignment commands recheck the chosen person's current authority.

The client sends `X-CSRF-Token` on writes, uses credentials on same-origin requests
and never logs in by selecting a role from a dropdown. The Vite development proxy
forwards `/api` to the local backend. UI integration tests use the real API.

## Module completion evidence

A feature requires a working user flow, typed rules, durable persistence, access
enforcement, errors/recovery, tests and independent review. A generated form,
an endpoint returning canned success, a mock-only test or a declared integration
port is not completion. Boundary adapters can use local test servers for rigorous
contract tests, but actual deployment/third-party access remains explicitly
unverified until exercised with approved configuration.

No national rule from the September register becomes an automatically approved
rule package. Current law, school-specific authority and archive configuration
are production gates. Work on software continues while those inputs are missing.

Technical references inspected 21 October 2026: [FastAPI](https://fastapi.tiangolo.com/),
[SQLAlchemy](https://docs.sqlalchemy.org/en/20/), [React](https://react.dev/learn),
[Vite](https://vite.dev/guide/). Actual installed versions are recorded in lockfiles;
references establish the architecture's building blocks, not compliance.

Practitioner choice ports support the planning and teaching screens without
administrative configuration access. `GET /ai/choices` takes an authorized
`learner_id`, `purpose=iep_drafting|session_planning`, offset and limit, and returns
only current reviewed policy/release pairs with model labels and review dates.
It neither resolves pupil sources nor contacts a provider; generation still
rechecks exact sources and processing boundaries. `GET
/learners/{learner_id}/teaching-staff` takes
`purpose=owner|assistant|delivery|follow_up` and returns paginated current active
staff identifiers and names. The assistant choice requires assignment authority;
no choice establishes qualifications or grants the chosen person pupil access.
Persisted session briefs and their assignments have separately paginated read
ports. An authorized dated assignee receives only the assigned learner's name
and responsible contact name alongside the curated brief. Full-group delivery
reads recover exact persisted deviation ownership/action only through the
existing dependency gate; learner-scoped reads never expose that group prose.
These read ports at `3c4d823` are independently accepted in the bounded
[practitioner choice review](reviews/practitioner-choice-ports-review.md).
Complete UI workflow acceptance remains separate.

Durable proposal recovery uses `GET /education-plans/{plan_id}/suggestions` and
`GET /teaching/sessions/{session_id}/suggestions`, with offset/limit pagination.
Both require the owning write authority and current purpose-specific AI access.
The IEP list is restricted to generation bases for the exact current plan
revision; the session list is restricted to its current immutable teaching basis.
A teaching job belongs to that basis, so another authorized session using the
same basis can independently review it. The response explicitly identifies this
scope and the current consumer revision rather than implying job ownership by
the session where it happens to be listed.

Each entry carries job ID/version, recorded execution state/attempt count,
timestamps, basis ID, current availability and the consumer's recorded review
outcome. It carries no output, source manifest, review reason or model settings.
Current availability rechecks source authorization, exact source content and the
reviewed processing/model boundary without invoking a model. A recalled job
retains its recorded execution state but becomes `review_required`; it cannot
be treated as usable generated content. Existing job read/run/diff/review commands
remain the authoritative action gates. A reload must select the persisted job
and basis instead of silently creating another generation. This backend port
does not yet complete browser recovery; its UI and independent acceptance remain
required.

### Curriculum and resource consumer contracts

BC06 is registered under `/curriculum` in the actual application. Its exact-read
ports are `current_class_context(db, actor, school_id, plan_revision_id, on_date,
learner_id=None)` and `resolve_resource(db, actor, school_id,
resource_revision_id, purpose='read', learner_id=None)`. Dates are inclusive local
dates. Resource purposes distinguish read, use, copy and AI; permission to read
never implies the others. Both ports recheck original sources and current rights,
and neither commits the consumer's transaction nor establishes pupil suitability.

The default evidence adapter resolves actual BC02 original storage or confirmed
controlled pupil excerpts. Pupil-derived resources remain private, including
their variants. Institutional sharing cannot expand underlying source access.
Native resource teams have explicit dated membership; they do not grant pupil
case access. Source correction handling exposes
`record_source_correction_impacts(db, actor, school_id, exact_old_reference)` for
the event consumer, with exact-source deduplication in the caller's transaction.
The event subscription itself is still required.

The owning teaching context must supply
`app.state.curriculum_future_session_port` with exact upcoming session revisions,
owners, learner IDs and instants, and validate an owner's keep/change decision.
The production dependency index and application of those decisions remain to be
implemented. Required impact checks currently return `session_impact_unavailable`
and roll back when this port is absent. Tests use an explicitly synthetic index;
it must never be installed as a production adapter. Likewise, the future J15
`curriculum_material_reservation_port` must return an exact inventory version,
interval and reservation-ledger revision. Current inventory counts do not prove
bookable availability; absent ledger integration returns `unavailable`.

Exact curriculum/resource selection into IEP and teaching bases, AI license
checks on those selections, practitioner authority controls and the complete J20
browser workflow remain separate required integration work. The BC06 backend
candidate is not full F09/F10 acceptance.

## Read-only assessment inputs

Revision `a0bcab2` adds two owning-context projections accepted in a
[separate independent review](reviews/owned-learning-projections-review.md).
They are building blocks for J10, not completed assessment workflows.

`curriculum.projections.reviewed_assessment_scheme(db, actor, school_id,
scheme_revision_id, starts_on=..., ends_on=...)` accepts inclusive local dates.
It checks the exact reviewed revision, full period coverage, current original
source rights and a digest of the stored curriculum plus assessment rules. It
returns scheme identity, goals, reviewed assessment-rule text, source references,
review metadata and a basis digest. A newer draft does not replace the previous
reviewed scheme; a reviewed successor does. The text grants no grading or
exemption authority, which remains explicitly unassessed for the consumer.

`teaching.projections.learner_delivery_basis(db, actor, school_id, learner_id,
delivery_revision_id)` returns only the authorized pupil's current actual-work
revision and participation, including absence and zero minutes. It includes
occurrence and recording dates, exact goal/provision references, support context,
the reported support status and its current assessment. It exposes no group
narrative, other pupil or staff total. A corrected revision returns
`actual_changed`; lost pupil scope denies access. A recalled staffing basis
changes support to unassessed without rewriting the recorded fact or creating a
follow-up task during the read.

Both calls leave transaction ownership with the consumer. They refuse pending
dependency edits before refreshing retained ORM objects. The caller supplies
the native `curriculum_source_port` and, where configured, the
`teaching_qualification_port` through its session. Neither projection supplies
professional finalization authority or proves learning progress from attendance.

## Assessment records and human review

Candidate `673a0eb` registers BC09 in the actual application with a static
`j10_assessment` migration after `j09_curriculum`. Its independent review is
assigned to `/root/review_j09`; the following describes implemented contracts
awaiting that review, not complete F11/F17/F19 delivery.

`/api/v1/schools/{school_id}/assessment` provides versioned instruments,
administrations and factual results; source-backed progress reviews; and subject
assessment statements. Instrument versions retain scales, conditions, licensing
and sourced reassessment guidance. Result corrections append revisions and
invalidate prior interpretation. A missing documented reassessment interval
remains an open professional question.

Progress snapshots bind exact goals, evidence, observations, actual participation,
selected reviewed results and prior reviews within a chosen interval. Confirmed
reviews remain historical records; late evidence and changed dependencies create
a visible review need. Recorded activity does not establish progress. Subject
statements bind the exact reviewed curriculum scheme and human-selected subject
evidence, keeping IOP context separate. Contributions, finalization and factual
communication records remain distinct.

The trusted `AssessmentAuthorityPort.resolve(db, actor, AuthorityRequest)` binds
school, pupil, person, purpose, exact revision/digest, full period and relevant
subject/scheme. The native J19 authority implementation remains required.
Missing authority blocks instrument administration, professional result review
and formal finalization; a role or textual curriculum rule cannot substitute for
it. Grade setting has a separate human authority check. Synthetic authority exists
only in tests.

The current manual source-review path persists `drafting=manual_grounded_source_review`
and `ai_generation=not_integrated`. Typed local AI generation, J20 practitioner
screens, external task integration and J12 authorized dispatch/receipts remain
required work. A factual communication entry performs no external send.

Source adapters use fresh owner-service identities on the same database
transaction, reject pending dependency edits and leave transaction ownership with
the caller. Root fresh-application tests exercise persistence across app instances,
native source recall and unavailable authority without fixture-supplied adapters.

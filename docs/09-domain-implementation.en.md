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

Curated projections can call
`evidence.projections.confirmed_binding_is_current(db, school_id, learner_id,
evidence_id, evidence_revision, link_id)` after authorizing their own projection.
The port returns only a boolean for the exact confirmed evidence/link/original
revision. It cannot authorize source prose, review reasons, history or original
documents; those still require the evidence service's actor-aware access checks.
Contexts must not replace full source authorization with this metadata check.

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

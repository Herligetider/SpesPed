# Master implementation plan

21 October 2026. Goal: implement and verify all current F01–F40 capabilities,
including extensions, error paths and professional review controls. The earlier
[P0–P8 plan](05-implementation-plan.en.md) defines product phases. This document
breaks the full work into jobs; it does not narrow scope to the first pilot.

## Source of truth and completion

`features.json` remains the product specification, including rules and workflow
steps beyond its acceptance examples. `implementation-manifest.json` lists all
features, all original acceptance criteria, required jobs and verification status.
An acceptance criterion is not completed by writing its test name in a manifest.
Evidence must be inspected at the actual source revision, and must include runtime
behavior at the relevant scope. Production-only gates remain explicit.

Each implementation job goes through `queued → implementing → awaiting_review →
changes_requested / verified`. A different reviewer examines every returned job.
The orchestrator integrates only reviewed work; findings go back to its implementer
and are independently rechecked. Later changes that invalidate evidence reopen it.

Use `gpt-6.1-sol` with high reasoning for domain invariants, access control,
transactional work and security reviews. Use `gpt-6-luna` with medium reasoning for
bounded scaffolding, typed UI work and straightforward checks once contracts are
fixed. Escalate if findings show the task is more complex. Review is independent
of implementation, regardless of chosen model. Three worker slots are available;
reserve a freed slot for review before dispatching unrelated new work.

Workers own disjoint paths and do not commit or alter common interfaces without
agreement. The orchestrator owns assembly, dependencies across modules, ledger,
Git checkpoints, integration verification and final requirement-by-requirement audit.

## Jobs and dependencies

| Job | Scope and deliverable | Features | Depends on | Evidence required |
|---|---|---|---|---|
| J01 | Backend foundation, durable identity, school/learner scope, sessions and CSRF | F01 F02 F27 F34 | Contracts | Login/logout, expiry, cross-school/learner denial, authority and persistence tests |
| J02 | Framework-independent domain primitives, period/quantity/provenance/approval policies | Cross-cutting | Contracts | Boundary and adverse domain examples, especially DST, revision and unsupported evidence |
| J03 | Accessible Norwegian web shell, real login, school/learner selection and API client | F01 F02 F31 | HTTP contract | Production build, typed client, keyboard flow, real API integration after J01 |
| J04 | Intake, file/OCR parsing, source confirmation, timeline and correction impact | F03 F04 F05 | J01 J02 | Multi-pupil source separation, file rejection, provenance, derivative correction |
| J05 | Source-backed support profiles, referrals, decisions, imported/created IEPs, goal versions and contributions | F02 F07 F08 | J01 J02 J04 | Profile confirmation/history, scope validation, dated authority, original approval, historical goals preserved |
| J06 | Session planning, exact approval, assistant briefs, actual delivery and notes | F12 F13 F15 F16 F39 | J01 J02 J04 J05 | Complete teaching cycle; no scheduled-as-delivered; assistant scope; stale brief |
| J07 | Teaching-cycle UI from intake to next observation | F02–F05 F07 F08 F12 F13 F15 F16 F39 | J03 J04 J05 J06 | Browser journey against persistent API with negative paths and usable review |
| J08 | AI capability gateway, local/remote development adapters, OCR/speech ports, model evaluation | F33 | J01 J02 | Real local protocol tests, no production remote fallback, injection/source limits |
| J09 | Curriculum/class plans, reusable resources, licenses and material inventory | F09 F10 | J01 J04 J05 | Published revisions, authorized reuse, license restrictions, change impact |
| J10 | Instruments/results, progress reviews and ordinary/Montessori assessment | F11 F17 F19 | J05 J06 J09 | Scale/condition validity, evidence gaps, human-only grades, scheme differences |
| J11 | Evidence snapshots, statutory templates, parent emails and opt-in draft schedules | F18 F20 | J04 J05 J06 J10 J08 | Correct periods/goals, late evidence, cadence deduplication, no auto-send |
| J12 | Exact-package disclosure, secure dispatch, receipts and recipient access | F21 | J01 J02 J11 | Rights recheck, invalidation, unknown outcome reconciliation, secure recipient view |
| J13 | Reviewed rule profiles, obligations, deadlines, leadership deviations and workload studies | F06 F29 F40 | J01 J02 | Unresolved applicability, correct triggers, actual action separate from document |
| J14 | Meetings, coordinated plans, tasks, attendance and follow-up | F22 F23 | J01 J04 J06 J13 | Participant scope, typed IP versus IOP, duplicate imports, absence versus cancellation |
| J15 | Capacity, accepted groups, deterministic scheduling and atomic reservations | F14 F36 | J05 J06 J09 | Feasible plan and explained infeasibility, concurrency, group/staff time separation |
| J16 | Protected school environment, intervention and concern workflows | F24 F25 F26 | J01 J02 J13 | Case isolation, alternative routes, no headteacher gate on personal/urgent duty |
| J17 | Rights requests, retention/holds, disposal, archive and school transfer | F27 F28 F35 | J04 J11 J12 J13 | Third-party masking, held records, derivative disposal, selective transfer receipts |
| J18 | Versioned scoped identity/mail/calendar/school/archive integration adapters | F32 | J01 J04 J12 J17 | Actual adapter contracts with local servers, revoked scope, retries and reconciliation |
| J19 | Full school/account administration, public extracts, conditional administrative case types, exemptions and appeals | F01 F30 F37 F38 | J05 J10 J13 J17 J18 | Account/enrollment lifecycle and revocation, school profile revisions, source reconciliation, type-specific authority/deadlines, working named administrative flows |
| J20 | Curriculum/resource/assessment/reporting UI | F09 F10 F11 F17 F18 F19 | J03 J09 J10 J11 | Browser journeys, revisions and source review; public/Montessori fixtures |
| J21 | Period-email, recipient portal and collaboration UI | F20 F21 F22 | J03 J11 J12 J14 | Chosen dates, paused draft plan, explicit send, recipient-specific view |
| J22 | Scheduling/capacity/attendance UI | F14 F23 F36 | J03 J14 J15 | Interactive conflict explanation, locks, publication and real attendance follow-up |
| J23 | Protected cases, rights, archive and transfer UI | F24 F25 F26 F27 F28 F35 | J03 J16 J17 | Role-separated browser journeys, urgent routing and disposition preview |
| J24 | School administration, governance, exports, integrations and workload UI | F01 F06 F29 F30 F32 F37 F38 F40 | J03 J13 J18 J19 | Actual editable workflows for every enabled administrative type |
| J25 | Complete language/accessibility coverage, reviewed translation and opt-in local dictation | F16 F31 | J07 J08 J20 J21 J22 J23 J24 | Bokmål/Nynorsk, keyboard/screen-reader checks, transcript confirmation and audio disposition |
| J26 | Production packaging, PostgreSQL isolation, encrypted storage, queue worker, backup/restore and local AI gate | F33 F34 | All backend jobs | PostgreSQL migrations/concurrency, restore drill, egress failure tests, operational runbooks |
| J27 | Full browser/API/adversarial/operational verification and repairs | F01–F40 | All implementation jobs | Each specification workflow and exception exercised; no mock-only completion |
| J28 | Independent whole-product completion audit and release decision | F01–F40 | J27 and all job reviews | Inspect every feature, criterion, extension and gate; reopen missing evidence |

Some dependency loops in product use are resolved through narrow contracts: J04
supports manual text/import before J08 AI extraction; J06 supports manual plans
before model generation; J13 starts with reviewed configuration independent of
formal reports. This orders work without removing the later required capability.

J01 and J03 provide foundation slices only. J05 supplies confirmed pedagogical
profile fields with sources and correction history; J07 exposes those fields in
the teaching workspace. J19 completes school profiles, staff/account lifecycle,
qualifications, membership/enrollment administration and credential/session
revocation. J24 supplies their editable administrative UI. Passing the foundation
reviews must not be interpreted as completion of F01 or F02.

## Delivery order

1. Freeze implementation contracts and the all-feature ledger. Dispatch J01–J03.
2. Review each result independently; resolve and retest findings before dependent
   callers rely on it. Build J04–J08 and demonstrate the first complete teaching flow.
3. Deliver curriculum, assessment, reporting and optional parent communication.
4. Deliver governance, collaboration, scheduling and protected cases.
5. Deliver records/integrations/administrative casework and all remaining UI.
6. Complete operations, accessibility, local AI and the full acceptance audit.

Every delivery includes necessary persistence, error recovery and access checks.
Every feature needs both its first release and the later extensions specified in
the catalog. The ledger records partial progress explicitly.

## Execution and release gates

- Synthetic development runs without third-party credentials using explicit local
  fixtures/test servers. Unconfigured services report unavailable, never success.
- External school/identity/secure-post contracts need actual authorized configuration
  before claims about that deployment. A manual boundary must match the catalog and
  have a working user flow; it cannot hide an unimplemented required integration.
- Legal source freshness, school rule approval, recipients, retention and public
  versus Montessori profiles require named school ownership. Software exposes
  unresolved configuration instead of claiming legal compliance.
- Local production AI requires tested processing policy, known model/version,
  hardware capacity and approved evaluation evidence. No real pupil data goes to
  development APIs while these are absent.
- Final completion requires all implementation and review evidence plus production
  gates applicable to the delivered scope. A launch is not automatically authorized
  merely because the code exists. Keep the goal active while required work remains.

## Evidence recording

For each job, record changed paths, exact Git revision, commands/results, reviewer,
findings and rechecks in `docs/reviews/`. For each feature, link tests, runtime
scenarios and UI flows in the manifest. The orchestrator audits these against the
actual specification, not only the 86 example acceptance criteria.

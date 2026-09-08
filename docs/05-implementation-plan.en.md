# Implementation plan – Spesped

Version 0.2 · 8 September 2026. Planning only; no application has been built or deployed. All 40 capabilities remain in scope. The legal register distinguishes sourced national requirements from areas needing local/detail review. The DDD model is a first pass to validate with practitioners.

## Delivery strategy

Deliver usable workflows through a modular monolith. Begin with school/access configuration and a complete intake-to-teaching-session-to-observation flow using confirmed existing plans. Then extend IEP authoring, assessment/reporting, optional parent communication, scheduling, protected cases and integrations. A phase may expose a capability manually before automating it. The [traceability matrix](06-traceability.md) records the first delivery phase; the extensions below remain required for full scope.

Parent email drafting moves to P4. It supports explicit date ranges and optional recurring draft preparation; there is no default weekly cadence and no automatic sending. The first release of this communication type goes only to eligible parents/guardians; a later learner-facing variant retains its own policy. Statutory communication has separate audience rules. The [Norwegian first-workflow walkthrough](08-first-workflow-review.no.md) is the initial domain-review entry point.

Every increment has three parallel concerns: user workflow, domain invariants and evidence of correct operation. We measure saved effort after review and correction. A fast generator that creates more review work fails the product goal.

## Proposed architecture

| Layer | Proposed choice | Reason and constraint |
|---|---|---|
| Staff and guardian UI | TypeScript web application with accessible components; framework finalized at P0 | Responsive desktop/tablet use, clear sources and side-by-side review; Norwegian UI |
| Application/API | Python modular backend with FastAPI | Shared ecosystem for document processing, inference and scheduling; domain objects remain independent of framework |
| Core storage | PostgreSQL, separate module ownership, migrations and explicit transaction boundaries | Structured decisions, assignments, revisions and audit relationships |
| Access enforcement | Application policy plus database protections as defense in depth | School isolation and case/learner/purpose restrictions; authentication alone is insufficient |
| Documents | Encrypted object storage with version references and record classes | Originals, approved revisions and exports have different lifecycles |
| Background work | Durable job queue and transactional outbox; implementation selected at P0 | Imports, draft generation and dispatch reconcile safely after retries |
| AI | Server-side capability gateway; remote development adapter and local inference adapter | No provider-specific concepts inside pedagogical domain objects |
| Scheduling | Deterministic constraint checking plus an optimization adapter | The optimizer proposes feasible allocations; educators approve pedagogy |
| Search | Start with structured filters and text search; add local semantic retrieval when justified | Enforce authorization before retrieval and track every indexed derivative |
| Identity/integration | OIDC-compatible identity boundary; evaluate Feide connection with the pilot owner | Teacher roles, school membership and signing authority need explicit mapping |
| Deployment | User-controlled server for production AI; separately protected backups and operational tooling | Capacity, availability, security, support and recovery remain explicit responsibilities |

Primary technical references: [FastAPI](https://fastapi.tiangolo.com/), [PostgreSQL row security](https://www.postgresql.org/docs/current/ddl-rowsecurity.html), [OR-Tools scheduling](https://developers.google.com/optimization/scheduling), [Feide documentation](https://docs.feide.no/). These establish available building blocks, not a claim that the stack itself achieves legal compliance. Verify supported versions and licensing when creating the actual dependency lockfiles.

```mermaid
flowchart LR
  UI[Staff / guardian interface] --> API[Application and authorization]
  API --> DOM[Domain modules]
  DOM --> DB[(PostgreSQL)]
  DOM --> OBJ[(Protected document storage)]
  DOM --> JOB[Durable jobs and outbox]
  JOB --> GATE[AI processing gateway]
  GATE --> LOCAL[Local production inference]
  GATE -. synthetic development only .-> DEV[External API adapter]
  JOB --> EXT[Authorized external adapters]
  EXT --> POST[Secure delivery]
  EXT --> ARCH[Archive / school systems]
```

## P0 – discovery, legal profiles and delivery baseline

Dependencies: none. Work from the current planning artifacts.

- Validate ES01–ES12 with at least a class teacher, special educator, assistant, school leader and relevant privacy/records expertise. Include public and Montessori examples.
- Confirm school legal category, godkjenning, current assessment scheme, municipalities, local templates/deadlines and decision authority.
- Decide the system of record for each data class: enrollment, guardian rights, official grades, decisions, finalized reports, attendance and archives.
- Resolve the minimum deployment facts: host specification, expected learners/concurrent users, IT ownership, backup location and incident contact.
- Record legal/application hotspots and a responsibility matrix. The 90-row registry is input, not an approved executable ruleset.
- Observe current work and measure baseline time for notes, session preparation and assistant guidance; establish separate baselines for parent emails and annual reporting when those workflows are introduced. Use synthetic material in the development environment.
- Select implementation libraries and CI/deployment approach; pin versions only after verifying current support.

Exit: reviewed vocabulary and workflows, initial public/Montessori rule profiles, approved implementation ADRs, synthetic scenarios and a measured workflow baseline. Unresolved local questions remain explicit and cannot be marked compliant.

## P1 – secure foundation and rule/record configuration

Features: F01, F02, F06, F27, F28, F31, F34. Contexts: BC01, BC03, BC14–BC16.

- School configuration, academic periods, typed IDs and school isolation.
- Staff assignments, qualifications, authority grants and guardian relationships with effective dates and restrictions.
- Authentication boundary, role/learner/case authorization, secure sessions and controlled administrative access.
- Initial requirement/rule registry with applicability tri-state, effective dates, accountable roles and configurable deadlines.
- Document classification, basic retention policy, legal holds and auditable access; rights-request intake.
- Secure storage, backups, secret management, minimal operational logs and a tested restore path.
- Accessible UI shell and translation structure for Bokmål/Nynorsk.

Exit: a user cannot retrieve another school's content through direct IDs, search, exports or jobs; expired assignments are refused. A restored environment re-applies current access and erasure/disposition controls. No real pupil data until the P1 privacy and processing gates have been satisfied.

## P2 – first vertical slice: intake → reviewed session → actual delivery and note

Features: F03–F05, limited existing-document intake for F07–F08, F12–F13, F15–F16, F33, F39–F40; extend F27/F28. Contexts: BC02, BC04–BC05, BC07, BC15. BC01/BC03/BC14 provide the P1 foundation.

- Manual notes, document upload, controlled email-file import, duplicate detection and source/learner confirmation.
- OCR/text extraction with original beside proposed fields; preserve occurrence date, recorded date, attribution and contradictions.
- Register an existing authoritative decision and approved IEP with confirmed source references, relevant scope and selected active goals. Preserve original approval evidence; do not require new IEP generation or a complete referral process in this slice.
- Select one learner, one goal, duration, manually entered class theme and available materials. For ordinary adapted teaching without ITO, use a confirmed ordinary teaching goal without requiring an IEP.
- Generate or manually edit a concrete session plan, with clear sources, steps, adaptations and observation points. Record review and exact approved revision.
- Generate and approve a short assistant brief where an assistant is involved; access is tied to the assigned support task.
- Place the session manually, record actual participation/time/category or cancellation and capture a short observation useful for the next session.
- Handle source corrections, changed plans, rejected proposals, unavailable AI and uncertain saves without duplicating or silently replacing accepted work.
- Use a synthetic development AI adapter, local adapter contract and deterministic fake model. Measure total planning/review/note effort and assistant comprehension.

Exit: demonstrate a complete synthetic teaching cycle, from confirmed source material to a useful next-session observation. Wrong learner, unsupported claims, expired assignment, stale assistant brief, cancellation and source correction must have explicit outcomes. A planned session cannot count as delivered. Show a useful manual path when AI is unavailable.

Scope: first delivered support for F07/F08 is existing-plan intake, not complete casework or IEP authoring. Automated scheduling arrives at P5. Parent email, recurring drafts, guardian portal and external dispatch are not P2 acceptance dependencies. Before any real-data AI pilot, pull forward the required local-processing subset of P8.

## P3 – extend casework, IEP authoring and reusable teaching plans

New feature areas: F09–F10. Extend F07–F08, F12–F13, F15–F16 and F39 beyond the P2 subset; basic manual schedule ahead of F14 automation. Contexts: BC04–BC08.

- Referral case, participation/consent references, expert-assessment import and formal decision register.
- Typed decision provisions with quantity units, effective period, support category, organization and competence constraints.
- Draft, review and activation of IEP revisions, including goal lineage and learner/parent contributions.
- Curriculum/assessment scheme references and class theme plans; material and reusable teaching-resource library with permitted use.
- Next-session proposals grounded in current plans, available materials and previous delivery.
- Five-minute assistant briefs approved by the responsible teacher; assignment-scoped access.
- Manual weekly scheduling, actual per-learner participation, cancellations and support-coverage ledger.
- One-minute structured notes; dictation is a later F16 extension at P7 after its privacy/quality checks.

Exit: a fictitious learner can move from imported decision to reviewed IEP to planned/delivered session and next-step proposal. A changed decision triggers review without rewriting history. Assistant time cannot silently satisfy a teaching entitlement. An unavailable resource cannot be shown as reserved.

## P4 – assessment, statutory documents and optional parent communication

Features: F11, F17–F22, F38; extend F39 to these document types. Contexts: BC03–BC05, BC09–BC12, BC15.

- Assessment instruments, versions, result scales, test conditions and professionally maintained reassessment guidance.
- Progress reviews linked to goal revisions, with insufficient/conflicting evidence displayed.
- Annual ITO evaluation: actual delivery, development against relevant IEP goals, source snapshot and authorized review.
- Ordinary and Montessori half-year assessment, including the correct handling of subjects completed early.
- Contributions from class/subject teachers, meeting preparation and recorded completion of actual assessment conversations.
- Document templates mapped to requirements; separate local half-year report templates from statutory annual ITO evaluation.
- Grade-warning, exemption and appeal workflows with human authority and type-specific timing.
- Secure preparation and export of formal documents; no automated final grades or legal decisions.
- Parent email subject/body generation for an explicit start/end date, with topic selection, evidence preview, internal citations and separately labelled future plans.
- Optional recurring draft schedule: frequency, period rule, timezone, owner, next run and pause/end. Default to on-demand drafting; due jobs request reviewable drafts only.
- Inclusive local date boundaries, evidence cutoff, late notes, empty periods, overlapping coverage and visible recipient/purpose-specific “since last confirmed sent period” semantics.
- Shared content review, exact-revision approval, recipient-specific disclosure checks and explicit dispatch through the first approved secure adapter; use sandbox delivery in development.
- Reconcile duplicate submissions and unknown transport outcomes. Controlled copy/export remains available but does not claim verified delivery.
- A minimal authenticated recipient page only if needed by the pilot's selected secure channel; the full portal remains P7.

Exit: public and Montessori scenarios select the correct document obligations. Missing evidence cannot become a positive progress claim. A document draft cannot close an unperformed conversation or unfulfilled support requirement. Formal approval authority is tested by document type rather than requiring both teacher and special educator for every output. Parent email scenarios verify selected dates, late evidence, no-evidence outcomes, paused schedules, per-period idempotency, changed approvals, revoked recipients and explicit sending. Successful recurring draft creation must produce zero dispatch requests until a sender acts.

## P5 – scheduling, staffing and attendance follow-up

Features: F14, F23, F36; extend F15/F22. Contexts: BC07–BC08, BC12.

- Availability, qualifications, guidance/preparation time, breaks, room/material calendars and accepted group relationships.
- Deterministic hard-constraint model and separate ranked preferences.
- Candidate timetable, manual changes, locked allocations and publication with atomic reservation checks.
- Explainable infeasibility report identifying conflicts and capacity gaps; no silent relaxation of statutory/decision constraints.
- Cancellation/replanning workflow, preserving already delivered sessions and staff worktime constraints.
- Attendance import/manual entry, contact follow-up and distinction from cancelled support.

Exit: no overlapping staff/learner/resource commitments; multiple publishers cannot race into a double booking. Group sessions account for each learner's participation and the staff allocation correctly. Teacher-approved grouping remains a prerequisite. A plan that cannot satisfy requirements says so clearly.

## P6 – protected cases and leadership follow-up

Features: F24–F26, F29; extend F06/F22/F27. Contexts: BC03, BC12–BC14.

- School environment casework, investigations, student voice, activity plans, action completion and evaluations.
- Appropriate notification paths, including matters involving a staff member or school leader.
- Dedicated physical-intervention documentation and escalation rules.
- Concern-report and urgent-action workflows that do not impose an unlawful headteacher approval dependency.
- Deviations, remedial tasks, rule-specific evidence and management dashboards that distinguish unresolved, overdue and satisfied states.
- Restricted case access, safe exports and practical unavailable-system procedures.

Exit: protected details do not leak into generic lesson prompts or parent email drafts. Emergency/personal reporting is possible without the ordinary report queue. Creating a plan does not mark the underlying issue resolved. Leadership can see responsibility and status without blanket access to every sensitive detail.

## P7 – complete integrations and conditional administration

Features: F30, F32, F35, F37; complete extensions of F16, F20–F21 and F28. Contexts: BC03, BC11, BC14–BC16.

- Prioritize the pilot's actual identity, school administration, calendar, mail, archive and secure delivery systems. Confirm API availability and agreements; do not assume connectors exist.
- Authorized mailbox folders/selections, import reconciliation, deduplication and error recovery. No unrestricted collection from staff mailboxes.
- Full guardian portal, notification preferences, accessible documents and version-specific access history.
- After the guardian-only first release, add the retained learner-facing update variant and participation view where the school enables it. Give it its own age-appropriate content and recipient policy; never expose the internal dossier by reusing the parent page.
- Optional dictation with explicit activation, transcript correction, limited audio retention and local processing.
- School-year transitions, enrollment/authority changes and selective school-transfer packages. Implement current purpose-specific disclosure rules, including applicable 2026 changes, after legal profile review.
- Managed archive transfer, verified receipts, disposition and correction workflows.
- Reconciled GSI/elevdata/statutory extracts and controlled export/attestation; retain official submission in its proper system if no suitable API exists.
- Conditional leader modules from L074–L086: admission, transport, SFO, physical environment, HR/qualification checks, working arrangements, resources, insurance, procurement and private-school governance/finance. Each needs its own confirmed applicable rules before automatic compliance checks.

Exit: external data ownership is documented, round-trip imports reconcile, exports preserve necessary metadata and no external retry creates an unreviewed duplicate. Every conditional area has either implemented agreed workflow/integration or an explicit, accepted external-system boundary; nothing is silently called complete because an API is unavailable.

## P8 – local production AI and operational release

Features: complete F33/F34 plus final integration, accessibility and privacy verification across all features.

This phase completes the production release. The local processing/privacy subset must be pulled forward before **any real-data pilot** using AI, even if the rest of P8 follows later. Real school data must not be sent to the development API just because a pilot precedes general production.

- Benchmark candidate local models against approved synthetic/redacted evaluation scenarios in Norwegian, including source-grounded drafting and refusal to invent evidence.
- Run all required production AI operations on the approved local processing path: extraction/OCR where AI is used, embeddings/retrieval, generation, reranking and speech if enabled.
- Enforce outbound network policy, provider allowlists and local-only production configuration. Disable unapproved telemetry and content logging. No silent external fallback.
- Load/capacity test using measured simultaneous users, document sizes and reporting peaks. Define queueing and manual alternatives when inference is saturated.
- Validate backup restore, key recovery, patching, access reviews, incident contacts and rollback. One server remains a potential availability bottleneck unless redundancy is deliberately added.
- Conduct accessibility assessment, threat-model review, penetration/security assessment appropriate to real-data use, and recovery rehearsal.
- Train staff in review, provenance, exceptions, incident handling and manual alternatives. Confirm school owner acceptance of each enabled rule profile.

Exit: the production system passes the approved acceptance scenarios, legal/privacy/records configuration is signed by responsible owners, local inference quality meets thresholds and total staff workload is improved in the pilot. A limited release may enable only completed workflows; it must label unavailable capabilities honestly.

## Suggested initial backlog slices

| Slice | User-visible result | Essential acceptance condition |
|---|---|---|
| B01 | A teacher sees only assigned learners | Changing a learnerId or queued job context cannot bypass authorization |
| B02 | A parent email is linked to the right learner | Ambiguous names require confirmation; original attribution remains |
| B03 | Confirmed existing plan and one note inform a session proposal (P2) | Goals and factual claims have sources; gaps remain explicit |
| B04 | A teacher edits and approves a session and assistant brief (P2) | Changing relevant content requires new approval; previous edits remain available |
| B05 | Actual participation and a short note feed the next session (P2) | No planned minutes count as delivery; cancellation and partial participation are explicit |
| B06 | A decision is translated into a new IEP proposal (P3) | Proposed scope cannot silently exceed or reduce the decision |
| B07 | An assistant gets a brief and records delivery | Brief access is scoped; actual minutes remain separate from plan |
| B08 | An annual evaluation uses the correct year and goals | Historical revisions and delivery gaps remain visible |
| B09 | A scheduler explains an impossible week | No hard constraint is silently converted to a preference |
| B10 | A protected concern gets the correct route | No routine approval queue delays a personal/urgent duty |
| B11 | A source correction reveals affected documents | Draft invalidation and sent-document correction are distinct |
| B12 | The same workflow runs with local inference | Production cannot contact a remote development model |
| B13 | A teacher requests a parent email for a chosen period (P4) | Inclusive dates, source cutoff, late notes and overlap are explicit; no invented progress |
| B14 | An opt-in schedule creates a new draft (P4) | Repeated execution creates one request per schedule revision/learner/period and never auto-sends |
| B15 | An eligible guardian receives an approved package (P4) | Current rights are checked; unknown outcomes reconcile; edits require new approval |

## Verification plan

Tests should cover meaningful invariants and failure modes, not merely mirror field setters.

1. Domain examples: correct rule profile, decision scope, revision approval, recipient authority, delivery counting, deadline semantics and lawful disposition.
2. Authorization tests: cross-school, cross-learner and restricted-case access through APIs, source links, exports, semantic search and background jobs. Database service accounts must not silently bypass the intended row policies.
3. Workflow tests: ES01–ES12 happy paths and exceptions, including source conflict, withdrawn access, changed attachments, overlapping schedule publication and queue retry.
4. AI evaluation: Norwegian quality, valid source support, unsupported-claim rate, wrong-learner leakage, prompt injection in uploaded documents, excessive disclosure and contradictory evidence. Evaluate the full pipeline and each changed model/prompt/template version.
5. Legal profile fixtures: public grade 8; Montessori grade 8; Montessori subject completed early; ITO annual review; learner with assistance only; under-15 and over-15 authority scenarios without treating age as a universal privacy rule.
6. Human usability: observed time for input, review, editing and retrieval; assistant comprehension; keyboard/screen-reader completion; user ability to reject a poor suggestion.
7. Period communication: custom date ranges, relative shortcuts, timezone/daylight-saving boundaries, late records, empty periods, overlap, unknown previous send status, schedule edits/pauses/owner revocation, missed runs and duplicate job delivery. These verify P4; they are not prerequisites for the teaching-only P2 slice.
8. Operations: recovery to agreed objectives, source erasure propagated to indexes, retained records preserved lawfully, provider failure, unknown delivery outcome and local inference outage.

Initial release targets are proposals to validate: zero cross-learner/cross-school disclosure in the adversarial test suite; all evaluated factual report statements traceable to supporting material; all invalid approval/recipient scenarios blocked; median routine note entry ≤ 60 seconds and normal assistant-brief orientation ≤ 5 minutes. No finite test suite proves universal absence of AI error or complete legal compliance.

## Operating the rule and template catalog

Maintain an owner, source, effective date, status and review history for every requirement version. Keep national law, regulation, authority approval, guidance, local routine and product preference distinguishable. A reviewed rule change runs an impact calculation against enabled schools and open obligations. Notify the relevant staff about changed work, not every source-page edit.

Maintain templates the same way: purpose, applicability, required content, author/reviewer roles, recipient rules, record category and version. Default dates must never invent a national deadline. A newly discovered rule can create a review task and a manual workaround while implementation is pending.

## Product boundaries and remaining decisions

This program supports teaching, documentation and coordination. Actual teaching, meetings, professional judgement, PPT assessments, statutory authority, physical environment work and health treatment remain with responsible people/services. Existing systems may remain authoritative for grades, HR, payroll, finance, formal archives and public submissions. Their integration/export boundaries count as deliberate product scope only when the user workflow and ownership are explicit.

The full scope is too broad for a credible calendar estimate before P0. Estimate each accepted slice after identifying team capacity, integration access, local obligations and server constraints. The production plan must include ongoing legal/template maintenance and operational responsibility as actual work, not assume that deployment completes them forever.

## Planning completion criteria

The present planning deliverable is complete when all user capabilities have IDs, every mapped legal area has a source and capability link, event flows cover the work and its exceptions, proposed aggregates have consistency rules, and implementation phases include the full backlog. Legal sign-off for a particular school, practitioner validation and implementation itself are subsequent work with explicit prerequisites above.

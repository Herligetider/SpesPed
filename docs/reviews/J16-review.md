# J16 independent backend review

- Reviewer: `/root/review_j16`, independent of the implementer; no implementation edits, subagents, commits, pushes, external messages or external AI calls.
- Exact candidate: `e4c295d66b47cd34f5ab2a0f20314af4021994fb`.
- Date: 21 October 2026.
- Verdict: **changes requested**. Five reproducible findings remain. Passing tests do not accept this backend job or establish complete F24/F25/F26 delivery.
- Scope: the candidate's safeguarding models, schemas, ports, service, router, migration `j16_safeguarding`, and tests. Read AGENTS.md, the complete F24/F25/F26 objects (including workflow, rules, workspace, state behavior, automation boundary and recovery), shared domain implementation contracts, the BC13 model and relevant J13 evidence/case contracts and review. High-risk domain/access/transaction review; no model-selection override or delegated review was performed.

## Findings

### J16-R1 — P1: Cached contributor replies disclose a task after its assignment has been removed

Locations: `backend/spesped/contexts/safeguarding/service.py:282–285`, `301–304`; cached projection creation at `248–250` and assignment-filtered projection at `587–591`.

A command replay rechecks the exact case contribution grant, then returns the entire previously cached contribution projection. It never reapplies current assignment filtering to that response. Consequently a contributor who retains permission for their own contributions can retrieve the protected description, deadline, owner and outcome of a followup that has been reassigned away from them. The ordinary contribution GET correctly hides that same task. Reassignment therefore fails to revoke retrieval through the receipt path. This is a current authorization bypass for protected task content; it does not require stealing another actor's request key or permission to read the dossier.

Reproducer, independently executed on SQLite and PostgreSQL: `test_contributor_replay_returns_reassigned_task_hidden_by_current_projection` grants only exact-case `safeguarding.case.contribute`, assigns a followup to that contributor, and posts their own account. The response caches the assigned task. A reviewer reassigns it to the teacher. Contributor GET now returns `assigned_followups=[]`, but replaying the original own-account POST with its original request key returns 201 and the removed task's full cached row. The independent fresh-completion check confirms that a new command against the reassigned task is denied, so the exception is specifically cached retrieval.

Required correction: retain command deduplication and conflict detection, but authorize every returned part against current ownership and case scope on replay. Return a currently authorized projection or a minimal authorized receipt rather than an unconditional historical projection. Cover reassignment, revoked grants, new exclusions and task-specific completion replays; no replay may repeat the mutation.

### J16-R2 — P2: Reconciled failed contact continues to appear as actual contact, and notification status collapses every outcome

Locations: `backend/spesped/contexts/safeguarding/service.py:133`, `441–452` (especially `449–451`).

Contact reconciliation can append an explicit failure of an earlier purportedly performed contact, but only the `performed` branch changes the case state. A concern with one contact remains `state=actual_contact` after the responsible user reconciles that same contact as failed. The workflow summary also reports `notification_execution=recorded` for every nonempty contact collection, including a failed notification, unknown receipt, or unrelated personal contact. It ignores contact kind and all reconciliation results. Thus the backend's execution summary does not distinguish unresolved/failed notification from actual execution, and its case state can contradict the latest human reconciliation. F25 separates prepared text from actual contact; F26 requires separate notification execution status and explicitly unresolved missing receipts.

Reproducers on both databases: `test_failed_reconciliation_keeps_successful_state` records one performed concern contact, then reconciles it as failed at a later actual time. Response: `state=actual_contact`, latest reconciliation `outcome=failed`, summary `notification_execution=recorded`. `test_failed_notification_summary_claims_recorded` records only a failed physical-case notification and gets that same summary. `test_information_contact_also_claims_notification_recorded` records only a personal contact and also gets that summary.

Required correction: derive an explicit effective status from the relevant contacts and their reconciliations, preserving the original attestations and subsequent corrections. Distinguish unrelated contact, attempted/failed/unknown notification, performed contact and receipt uncertainty. A failed reconciliation of the sole purported success must not leave an unqualified current success state. Other independent successful contacts must remain effective.

### J16-R3 — P2: Assigned pupil-perspective followup is invisible to its limited owner

Locations: `backend/spesped/contexts/safeguarding/service.py:310–319` and `587–591`.

The full writer's missing-pupil-view command permits a current exact-case contributor as `followup_owner_id`, but stores that assignment only on `PupilPerspective`. The contribution projection returns pupil views solely when `author_id` matches the actor and assigned tasks solely from `Followup`/`PlanMeasure`. A different contributor assigned to obtain the pupil's view receives neither the missing reason nor its deadline or assignment. They cannot use the full dossier GET either. No separate followup is created. This leaves the accepted owned followup without an actionable view for its responsible person, contrary to the F26 missing-perspective workflow.

Reproducer on both databases: `test_missing_pupil_view_assigned_to_contributor_is_invisible_to_owner` creates a physical case, grants another teacher only exact-case contribution permission, and has the full writer record a missing pupil statement with that teacher as owner and a due date. The command succeeds and the full case names that owner. Their contribution GET has empty `own_pupil_views`, `assigned_followups` and `assigned_measures`, contains none of the pending item's ID/reason/date, and full case GET is 403.

Required correction: expose a narrow, currently assigned pupil-perspective followup projection or create a linked actionable Followup, including the necessary reason/deadline and a resolution path. Do not grant dossier access merely to make this task visible. Test another author, reassignment/revocation and a later supplied pupil statement.

### J16-R4 — P2: API accepts text lengths that PostgreSQL cannot persist, returning HTTP 500

Locations: `backend/spesped/contexts/safeguarding/schemas.py:149` (`Short` permits 2000), versus `models.py:144` and migration `j16_safeguarding.py` (`channel` is varchar(100)). The same mismatch exists for route channel, and `received_from`/physical `place` allow 2000 in schemas while their tables allow 1000.

A syntactically valid contact request passes HTTP validation and fails during PostgreSQL flush. The transaction wrapper does not translate SQLAlchemy `DataError`, so the real HTTP result is 500 `internal_error`, rather than a useful field error. SQLite accepts the same request, concealing the production failure. A valid supported input therefore cannot be saved and provides no actionable recovery.

Reproducers: `test_postgres_accepts_api_length_but_fails_storage` submits a 101-character channel and observes PostgreSQL `value too long for type character varying(100)`; SQLite returns 201. `test_validated_channel_returns_http500_without_partial_commit` uses the real HTTP client with server exceptions disabled and receives 500 with `{"error":{"code":"internal_error","message":"The request could not be completed."}}`. The independent check confirmed complete rollback: unchanged case version and no contact row.

Required correction: align all field limits across schemas/models/migration, then verify boundary-length requests on PostgreSQL and field-level validation for unsupported lengths. Preserve the demonstrated rollback behavior.

### J16-R5 — P2: A new incident followup can be completed before the incident happened

Location: `backend/spesped/contexts/safeguarding/service.py:467–475`.

Followup completion checks only whether the supplied instant is in the future. A post-incident prevention followup can therefore be marked performed at a time preceding the physical incident by a month. That older action is accepted as completion of the new incident's followup, with no explicit distinction for historical/background work. This undermines F26's actual preventive-followup trail and loses the occurrence-versus-entry distinction at the completion boundary.

Reproducer on both databases: `test_followup_completion_before_case_occurrence_accepted` creates a physical intervention occurring two hours ago, creates a new prevention task for that intervention, and completes it with `occurred_at` thirty days ago. The request succeeds and the task becomes `performed`; captured output shows the completion instant preceding the incident instant.

Required correction: validate actual completion against the relevant incident/followup chronology. Retrospective entry must remain possible: do not require completion after the database entry time. If earlier preventive/background actions are relevant, represent them as such rather than using them silently as completion of a later incident's followup. Cover valid late entry and impossible pre-incident completion independently.

## Verification and isolation

The candidate was extracted with `git archive` into ignored `var/review-j16/pinned`. All execution used the absolute archive backend path in `PYTHONPATH`, with cwd set to that archive, avoiding the shared editable installation. Explicit import inspection returned:

```text
/Users/lauritz/Programming/SpesPed/var/review-j16/pinned/backend/spesped/__init__.py
/Users/lauritz/Programming/SpesPed/var/review-j16/pinned/backend/spesped/contexts/safeguarding/service.py
```

Commands:

```sh
mkdir -p /Users/lauritz/Programming/SpesPed/var/review-j16/pinned
git archive e4c295d66b47cd34f5ab2a0f20314af4021994fb | tar -x -C /Users/lauritz/Programming/SpesPed/var/review-j16/pinned

# cwd: /Users/lauritz/Programming/SpesPed/var/review-j16/pinned
PYTHONPATH=/Users/lauritz/Programming/SpesPed/var/review-j16/pinned/backend \
SPESPED_TEST_POSTGRES_URL=postgresql+psycopg://spesped_test:synthetic-development-only@127.0.0.1:55432/spesped_test \
/Users/lauritz/Programming/SpesPed/backend/.venv/bin/pytest \
/Users/lauritz/Programming/SpesPed/var/review-j16/pinned/backend/tests/test_safeguarding.py -q

PYTHONPATH=/Users/lauritz/Programming/SpesPed/var/review-j16/pinned/backend:/Users/lauritz/Programming/SpesPed/var/review-j16/pinned/backend/tests \
SPESPED_TEST_POSTGRES_URL=postgresql+psycopg://spesped_test:synthetic-development-only@127.0.0.1:55432/spesped_test \
/Users/lauritz/Programming/SpesPed/backend/.venv/bin/pytest \
/Users/lauritz/Programming/SpesPed/var/review-j16/test_adversarial.py -q -s
```

Results:

- Candidate suite: **41 passed, 1 skipped**, 26.93 seconds. The skip is SQLite concurrency; the corresponding production PostgreSQL locking/CAS test passed.
- Independent probes, final run: **27 passed, 1 skipped**, 18.09 seconds. The skip is the PostgreSQL-specific HTTP varchar check on SQLite. PostgreSQL executed all 14 independent cases.
- The defect probes deliberately assert observed candidate behavior. Passing those probes records reproduction, not correction. After repair, retain them with corrected authorization/status/validation/chronology expectations.
- Only the existing Starlette TestClient/httpx deprecation warning appeared.
- All PostgreSQL fixtures created and dropped unique temporary `j16_<uuid>` schemas in the synthetic `spesped_test` database. No demo database or real pupil data was used.
- Migration tests targeted **`j16_safeguarding`**, downgraded explicitly to **`b1_integrate_contexts`**, confirmed preservation of identity learners/removal of safeguarding tables, and upgraded back to all **19** context tables on both engines. No uncommitted integration migration was used.
- The candidate suite exercised PostgreSQL duplicate-create serialization and optimistic concurrent mutation (one success/one conflict), audit/outbox failure rollback, all three typed workflows, immutable historical snapshots, exact-case permissions and grant revocation, reviewed recipient/body/revision binding, actual contacts without a prior draft, alternative headteacher routing, exclusions and owned followups. Independent probes added fresh/replayed reporting revocation, author newly accused/excluded across history/export/submission/contribution paths, hidden event/list/aggregate counts after revocation, wrong-kind commands with unchanged state, premature closure rejection, reassignment denial for fresh completion, provider-unavailable recovery, and real PostgreSQL DataError rollback, beyond the findings above.
- Evidence: ignored `var/review-j16/baseline.log`, `var/review-j16/adversarial.log`, and `var/review-j16/test_adversarial.py`. This report is the only non-ignored review change.

## Remaining integration and acceptance boundaries

Root production router/model registration, the real governance case/evidence adapters and reviewed-rule resolver, and J23 browser UI remain explicitly unverified integration work. These known omissions are not counted as the five candidate findings, and this review does not mark whole F24/F25/F26 features complete. No transmission connector, automatic legal determination or force-use instruction exists or was requested; contact records are retrospective human attestations.

The current rule port (`ports.py:6–11`) models one reviewed profile and flat documentation/notification strings. Actual J13 obligations carry applicability/resolution state, immutable profile/rule provenance and generic required actions/documents. Composition must preserve those facts rather than treating every action as notification or an empty requirement list as fulfillment. Before claiming that integration, agree a contract that represents unavailable/recalled/unresolved rule context, multiple actual source profiles where applicable, and per-obligation applicability/state, exact source version, required document types and generic required action. The presentation must keep action, documentation and notification distinct. No contract or implementation was changed in this review.

An independent probe also confirmed the present failure behavior: a configured resolver raising safe `rule_context_unavailable` makes authorized dossier GET return 503, while the author's narrow submission GET and retrospective urgent-contact POST remain usable. A missing resolver instead returns an unavailable context inside a successful detail response. Root composition must represent recalled/missing/multiple/unresolved rules visibly without making otherwise authorized case access dependent on a successful rule lookup; this is a required integration/recovery decision, not evidence that the adapter has been implemented.

No new legal research, school configuration approval, real service contact, production deployment, UI journey or whole-product release acceptance was performed. Findings require implementer repair and an independent pinned recheck before accepting the assigned backend scope.

## Independent repair recheck — 21 October 2026

**Repair revision:** `77ce990cfcec8a9007e609c9654e53cfb651e72c`.

**Exact executed archive:** `30c656f624a32bb4512f4894388f46afcc2e521d`, extracted afresh into ignored `var/review-j16/recheck-pinned`. Git comparison confirmed no safeguarding source/test changes between the repair revision and this execution pin. The latter adds the separately reviewed governance projection candidate; its review is recorded in `docs/reviews/protected-rule-projection-review.md`.

**Verdict: all five original findings are fixed; bounded review accepted for the assigned J16 backend scope only.** No additional reproducible finding remained in this recheck. The initial review and original observed-defect probes remain preserved above and under `var/review-j16/test_adversarial.py`. This verdict does not accept whole F24/F25/F26 features, UI delivery, or live rule-adapter/application composition.

### Finding dispositions

- **J16-R1 fixed** (`service.py:252–255`, `287–290`, `595–606`, `646–652`): replays reconstruct current authorized projections, and new receipts persist only aggregate ID/revision. Independent recheck explicitly replaced a stored new receipt with the original candidate's full historical cached projection, reassigned its protected task, and replayed it. Both engines returned the current restricted projection without the removed task, description or deadline. Snapshot/event/receipt counts and own-account count remained unchanged. Supplied tests additionally verified completion replays, changed-key conflict, later revocation/new exclusion, current route-revocation status and hiding measures from superseded plans.
- **J16-R2 fixed** (`service.py:131–138`, `447–456`, `655–699`): the latest actual reconciliation determines effective contact status while original attestations remain intact. Independent original reproductions now require a failed notification summary, a separate personal-contact summary and `contact_failed` after the sole success is reconciled as failed; all passed on both engines. Supplied tests additionally exercised all execution outcomes, separate receipt uncertainty, unrelated contact, preserved independent successful contacts, older actual reconciliations entered later, environment notification reversal, invalid chronology, and late closed-case reconciliation retaining closure while setting `review_required`.
- **J16-R3 fixed** (`service.py:603–606`, `702–716`; new contribution resolution route): another contributor assigned to obtain a missing pupil view now receives the narrow pending ID/reason/deadline/state, without source attribution or dossier access. The independent recheck resolved it through the actual new HTTP command, observed the appended own pupil statement and disappearance of the pending item, verified identical replay without a second statement, denied a fresh second resolution, and checked preserved original missing-view history. Supplied checks additionally covered reassignment, stale targets, current grant revocation/new exclusion, later supplied statements and pre-incident resolution rejection.
- **J16-R4 fixed** (`schemas.py:10–11`, affected create/correction/contact/route fields): schema limits now match the existing tables. Independent real HTTP requests on both engines reject channel length 101 with 422 and no mutation; length 100 persists, including on PostgreSQL. Supplied checks verify route channel/recipient and environment source/physical place maxima and max+1 in create/correction commands, along with unchanged audit/event/receipt counts on rejection.
- **J16-R5 fixed** (`service.py:471–480`): completion preceding the incident is rejected with unchanged version/task state. The independent recheck also completed the same task at a valid post-incident time preceding its database entry time, preserving retrospective entry on both engines. Supplied checks cover limited contributors, retained incident occurrence through correction and separate historical background actions.

### Recheck commands, results and isolation

All commands ran from `/Users/lauritz/Programming/SpesPed/var/review-j16/recheck-pinned` with the explicit absolute environment below. Import inspection returned only that archive for `spesped`, safeguarding service and governance projections; the shared editable installation was not imported.

```sh
PYTHONPATH=/Users/lauritz/Programming/SpesPed/var/review-j16/recheck-pinned/backend:/Users/lauritz/Programming/SpesPed/var/review-j16/recheck-pinned/backend/tests \
SPESPED_TEST_POSTGRES_URL=postgresql+psycopg://spesped_test:synthetic-development-only@127.0.0.1:55432/spesped_test \
/Users/lauritz/Programming/SpesPed/backend/.venv/bin/pytest \
backend/tests/test_safeguarding.py backend/tests/test_protected_rule_context.py -q

PYTHONPATH=/Users/lauritz/Programming/SpesPed/var/review-j16/recheck-pinned/backend:/Users/lauritz/Programming/SpesPed/var/review-j16/recheck-pinned/backend/tests \
SPESPED_TEST_POSTGRES_URL=postgresql+psycopg://spesped_test:synthetic-development-only@127.0.0.1:55432/spesped_test \
/Users/lauritz/Programming/SpesPed/backend/.venv/bin/pytest \
/Users/lauritz/Programming/SpesPed/var/review-j16/test_fixed_regressions.py -q
```

- Combined candidate suites: **84 passed, 1 skipped**, 52.36 seconds: 74 passing safeguarding checks, 10 passing root projection checks, and the SQLite concurrency skip. PostgreSQL concurrency/CAS, audit/outbox rollback and the explicit `j16_safeguarding` ↔ `b1_integrate_contexts` migration roundtrip passed again.
- Corrected original independent regressions: **28 passed**, 16.92 seconds, covering all five repairs plus the original positive authority/exclusion, scope/count, wrong-kind, closure, reassignment and urgent recovery probes. The new file changes the original observed-defect expectations to require the repaired outcome; passing old buggy behavior was not treated as repair evidence.
- Only the existing Starlette TestClient/httpx deprecation warning appeared.
- Unique temporary PostgreSQL schemas in synthetic `spesped_test` were created/dropped by fixtures. No demo database, real pupil data or external service was used.
- Evidence: `var/review-j16/recheck-suite.log`, `fixed-regressions.log`, and `test_fixed_regressions.py`. The separately recorded independent rule-port checks have their own report/log.

The original integration boundaries remain. In particular, the governance read helper is not registered into safeguarding, and the richer safeguarding adapter contract, resilient case-detail composition, root production registration and J23 UI are separate work. The September legal registry received no new legal certification. This recheck changed only review reports and ignored probe/log artifacts; no implementation edit, commit, push or subagent was used.

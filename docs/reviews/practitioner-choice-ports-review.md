# Practitioner choice and persisted teaching read ports review

- Reviewed commit: `3c4d823626a69c3b0a5b5996b5760217808c4b30`, limited to its six-file parent diff.
- Reviewer: `/root/review_composition`, independent of the root implementation author.
- Review date: 2026-10-21.
- Verdict: **accepted for these bounded read/choice ports; no blocking findings**.

## Accepted scope

The practitioner AI choice endpoint requires current learner and exact purpose authority, independently of administrative configuration access. It lists current policy/release pairs only after the existing evaluated-release and runtime checks. The projection contains IDs, model labels and review dates, with stable pagination; it neither resolves pupil sources nor invokes a provider. Listing a choice does not establish source-specific generation eligibility or provider availability; job creation/execution retain those checks.

The teaching staff endpoint requires teaching write access for the selected learner, plus assignment authority for assistant choices. It exposes only identifiers and display names for current eligible staff accounts/memberships. These are staff candidates, not declarations of qualification or grants of pupil access; owner/session commands still enforce their additional conditions. `validate_owner` now refreshes current account and membership state rather than trusting cached values.

Assigned brief labels remain behind the existing dated-assignee or teacher scope checks. The assistant projection adds the assigned learner's name and responsible contact name without opening the full learner dossier. Teacher assignment lists retain the brief's learner scope.

Full-group delivery reads recover the persisted deviation owner/action for the exact delivery revision, through the existing dependency gate. Missing, inconsistent or recalled dependencies hide the prose. Learner-only delivery reads always omit that group follow-up prose and owner. Correcting the actual record cannot make recalled historical follow-up text current again.

## Method and results

The reviewer used a separate `git archive` under `var/review-practitioner-choices/pin`. All Python execution used the shared Python 3.12 runtime with these absolute import paths first:

```text
/Users/lauritz/Programming/SpesPed/var/review-practitioner-choices/pin/backend
/Users/lauritz/Programming/SpesPed/var/review-practitioner-choices/pin/backend/tests
```

Both SQLite and actual PostgreSQL ran. PostgreSQL fixtures created and removed unique temporary schemas in the configured synthetic test database. No demo schema, real pupil data, external AI or external messaging was used. The local wire-server fixtures exercise HTTP model evaluation, and independent choice probes assert that subsequent choice reads make no model requests.

| Verification | Result | Saved log |
| --- | --- | --- |
| Exact-pin `backend/tests/test_practitioner_choices.py` | 12 passed, no skips, 16.21 s | `var/review-practitioner-choices/pinned-choices.log` |
| Focused original teaching/gateway regressions | 30 passed, no skips, 43.14 s | `var/review-practitioner-choices/focused-regressions.log` |
| Independent choice/authorization probes | 14 passed initially; two remaining delivery cases passed after correcting the reviewer scenario | `var/review-practitioner-choices/independent.log`, `independent-delivery-rerun.log` |
| Patch whitespace check | Passed | `git diff --check 3c4d823^ 3c4d823` |

The focused regression command selected:

```text
test_teaching.py::test_complete_manual_teaching_cycle_and_assistant_scope
test_teaching.py::test_group_minutes_corrections_cancellation_and_unplanned
test_teaching.py::test_source_correction_stales_brief_history_replay_and_owned_followup
test_teaching.py::test_ito_requires_exact_reviewed_qualification_port_and_supports_unassessed_recovery
test_teaching.py::test_follow_up_resolution_keeps_original_dependencies_after_independent_revision
test_teaching_gateway.py::test_current_configuration_rechecks_cached_rows_after_recall
test_teaching_gateway.py::test_current_job_refreshes_active_assignment_actions_and_membership_role
```

These were run with `python -m pytest -q`, the archived absolute import paths and `SPESPED_TEST_POSTGRES_URL` configured. The reviewer waited for each process to finish and inspected its saved output. The only warning is the existing FastAPI/Starlette TestClient deprecation.

## Independent adverse-path evidence

The ignored reviewer artifact `var/review-practitioner-choices/test_independent_choices.py` contains **16 passing cases** across both databases, covering:

1. Two policies and two reviewed releases produce exactly four distinct pairs. Every one-row page agrees with the complete ordered result, offset beyond the end preserves the total, and responses contain only the documented fields. A source resolver that raises if called is never invoked; provider-request and generation-job counts remain unchanged.
2. Editing a reviewed evaluation artifact removes its release's choices. Removing a release's review timestamp removes its remaining choices. Neither read invokes the provider.
3. Changing the trusted runtime's allowed private network removes otherwise reviewed local choices. Losing learner-read authority denies the endpoint even with the purpose grant; a warmed service session also denies access after another committed session revokes its purpose authority.
4. A warmed owner check notices a staff member becoming a guardian. Future memberships and excluded roles disappear from staff lists; revoked assignment authority denies assistant choices while other authorized purposes remain usable. Invalid paging/purpose and foreign-school requests are rejected.
5. An expired brief assignment denies the assistant's named projection and disappears from the active assignment list.
6. A not-yet-valid brief assignment does the same.
7. Changing the assignee's membership role to guardian denies the named projection.
8. Deactivating the assigned learner denies the named projection. Across these assignment scenarios, a teacher authorized for another learner cannot read the brief assignment or its teacher list.

The delivery probe additionally verifies, on both databases:

- Only full-group authorization exposes the persisted action; a teacher with one participant's scope receives neither the group endpoint nor group prose in that learner's list.
- Correcting a supporting source hides the original follow-up action and owner with `review_required` status.
- An explicit actual-record correction that removes the invalid historical goal claim and supplies a new action exposes only the new revision's action. The recalled historical revision stays redacted.
- Repeated current/history reads do not create additional follow-up rows.

The first delivery scenario incorrectly attempted a retroactive replacement-plan activation and correctly received `activation_period`. The reviewer changed the scenario to the valid actual-record correction described above; both targeted reruns passed in 4.53 seconds. No application changes were needed.

## Limits

This review accepts the new choice/name/follow-up projections and the account/membership refresh change. It does not accept entire features, the practitioner UI, actual provider uptime, complete staff qualification data, deployment readiness or unreviewed later commits. It does not infer a staff member's qualification from a selectable name or an entitlement's fulfilment from recorded work. Documentation accurately retains the source-specific generation and group-disclosure boundaries. The legal registry was not re-researched. No production files were modified and nothing was committed or pushed by the reviewer.

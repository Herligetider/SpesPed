# Teaching author label review

- Reviewed commit: `b553a5a306c1149adb075157ebc1e95f00d1bb37`, limited to its two-file parent diff.
- Reviewer: `/root/review_composition`, independent of the root implementation author.
- Review date: 2026-10-21.
- Verdict: **accepted for these additive author labels; no blocking findings**.

## Accepted boundary

`teaching/service.py:732–741` adds the current display name of `ObservationRevision.author_id` to the already authorized observation projection. The name query follows learner/assignment scope, wrong-pupil history checks and the private-draft guard. It uses the selected revision's author ID, not the current reader. Public corrections continue to require the original author and preserve attributed history.

`teaching/service.py:915–919` adds the current display name of `AssistantActualInput.author_id` to the existing actual-input projection. Both public callers retain their existing gates: the list first authorizes the exact assignment, and the review command authorizes the teacher and learner before returning its projection. The query selects only `UserAccount.display_name` for the already exposed author ID. Neither addition exposes email, roles, account credentials or a searchable directory.

These are current display labels, not snapshots of a person's name at recording time. Stable author IDs remain the historical attribution. The change does not add names to actual-input review-history reviewers, and does not change source/prose authorization or treat assistant input as delivered entitlement minutes.

## Verification

The reviewer froze the exact commit under `var/review-teaching-author-label/pin` and used Python 3.12 with absolute archived imports:

```text
/Users/lauritz/Programming/SpesPed/var/review-teaching-author-label/pin/backend
/Users/lauritz/Programming/SpesPed/var/review-teaching-author-label/pin/backend/tests
```

`import-origins.log` confirms that the application and fixture imports resolved to that archive. All scenarios ran on SQLite and actual PostgreSQL using `SPESPED_TEST_POSTGRES_URL`, with unique temporary schemas created and removed by the fixtures. Only synthetic data was used.

| Check | Result | Log |
| --- | --- | --- |
| New HTTP author-label regression and three existing teaching regressions | 8 passed, no skips, 11.36 s | `var/review-teaching-author-label/focused.log` |
| Independent permission-query and source-recall scenarios | 4 passed | `var/review-teaching-author-label/independent.log` |
| Independent author/history/draft scenario after reviewer-fixture correction | 2 passed, no skips, 2.73 s | `var/review-teaching-author-label/independent-history-recheck.log` |
| Patch whitespace | Passed | `git diff --check b553a5a^ b553a5a` |

The focused command used `python -m pytest -q` with these exact test nodes:

```text
backend/tests/test_practitioner_choices.py::test_attributed_history_names_require_existing_teacher_or_assignment_access
backend/tests/test_teaching.py::test_observation_draft_transcription_correction_reuse_and_wrong_pupil
backend/tests/test_teaching.py::test_assignment_revocation_blocks_replay_and_unassigned_assistant_cannot_write
backend/tests/test_teaching.py::test_complete_manual_teaching_cycle_and_assistant_scope
```

The independent probes are in `var/review-teaching-author-label/test_independent_labels.py`. They verify:

- Real observation corrections and records from two authors retain the matching author ID/name in current reads, paginated history and the learner list. Renaming an account changes its display label without changing the recorded author ID. Another author's unsaved observation and its history remain denied.
- SQL tracing sees no display-name query for denied guardian, technical-administrator, revoked-assignment or foreign-school requests. Authorized assistant observation/history and actual-input reads do execute the narrow name query. Responses contain no account email or directory fields.
- After source reassignment, teacher session and assistant brief content remain suppressed. Actual-input review reasons and review-history reasons remain hidden. Independently recorded observation and assistant-input facts retain their author labels under their existing valid access rules.

The first independent history fixture tried to mutate an immutable observation revision to distinguish its author artificially. The application correctly rejected that fixture with `immutable_revision`. The reviewer replaced it with the public correction workflow and current account-name updates; both targeted reruns passed. No production change was needed. The reviewer awaited every process and inspected all saved logs. The only warning was the existing FastAPI/Starlette TestClient deprecation.

## Limits

This accepts the two author-label projections at this pin. It does not accept the whole practitioner UI, complete features, deployment readiness or later commits. No legal sources were re-researched. The reviewer changed only this report and ignored review artifacts and did not commit or push.

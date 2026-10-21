# Durable suggestion recovery — independent review

Candidate: `c18a0e05c7dd3519df6365e7a0bab740841f351a`. Reviewer: independent `review_j05`. **Bounded backend acceptance: no actionable finding from this review.** This accepts the two persisted-job listing ports and their stated scope, not browser recovery or full J07/F08 completion.

## Scope and isolation

Read all seven commit files and the directly used owning authorization, immutable-basis/source validation, gateway configuration, lineage and job read/run/review paths. Contracts are `GET /education-plans/{plan_id}/suggestions` (generation bases for the exact current plan revision) and `GET /teaching/sessions/{session_id}/suggestions` (the exact current teaching basis). Teaching jobs belong to the basis; session-specific review outcomes must remain independent. The supported generation path is single learner; group teaching remains a manual workflow.

Created a fresh `git archive` at `var/review-suggestion-recovery/pinned`. Every test used absolute `PYTHONPATH=/Users/lauritz/Programming/SpesPed/var/review-suggestion-recovery/pinned/backend:/Users/lauritz/Programming/SpesPed/var/review-suggestion-recovery/pinned/backend/tests`, with `/Users/lauritz/Programming/SpesPed/backend/.venv/bin/python` only as the runtime. `import-paths.log` verifies archived main, gateway, plan and teaching services plus all three fixture modules. Each independent case also asserts its fixture/main import location. All seven archived candidate files still byte-match the commit after testing; the frozen migration tree contains no evolving shared J09 migration.

Tests use actual authenticated FastAPI requests, real SQLite and fresh uniquely scoped PostgreSQL schemas on the authorized test database at 127.0.0.1:55432, actual source/plan/session commands and a synthetic loopback model protocol. Administrative grants/recalls and extra pagination rows use fixture ORM writes. Model calls are local synthetic calls; no external messages, model services or real pupil data are involved. No production source was edited.

## Commands and results

The following environment was used for each pytest command:

```
PYTHONPATH=/Users/lauritz/Programming/SpesPed/var/review-suggestion-recovery/pinned/backend:/Users/lauritz/Programming/SpesPed/var/review-suggestion-recovery/pinned/backend/tests
SPESPED_TEST_POSTGRES_URL=postgresql+psycopg://spesped_test:synthetic-development-only@127.0.0.1:55432/spesped_test
```

```
# cwd: var/review-suggestion-recovery/pinned
/Users/lauritz/Programming/SpesPed/backend/.venv/bin/python -m pytest backend/tests/test_suggestion_recovery.py -q
# cwd: repository root
/Users/lauritz/Programming/SpesPed/backend/.venv/bin/python -m pytest var/review-suggestion-recovery/test_independent.py -q
/Users/lauritz/Programming/SpesPed/backend/.venv/bin/python -m pytest var/review-suggestion-recovery/test_independent.py -q -k 'new_app_and_session_scoped_review or permission_and_stale_goal_rechecks'
/Users/lauritz/Programming/SpesPed/backend/.venv/bin/python -m pytest var/review-suggestion-recovery/test_independent.py -q -k permission_and_stale_goal_rechecks
/Users/lauritz/Programming/SpesPed/backend/.venv/bin/python -m pytest var/review-suggestion-recovery/test_independent.py -q -k previously_applied_plan_lineage
```

- Committed suite: **18 passed**, no skips, 64.03 seconds (`author-tests.log`), exit 0.
- Independent suite: **14 distinct parametrized cases passed** across the initial run and targeted reruns, seven cases on each database. The initial run passed eight and failed four because the review scaffold used the IEP outcome literal `applied` for teaching and reused a pre-login CSRF token. Those requests were correctly rejected; only the ignored probes were corrected. Its targeted rerun passed the two session-outcome cases, while the stale-goal setup was correctly rejected for attempting retroactive replacement activation. The probe was corrected to use a future replacement interval before the planned lesson; the two stale-goal cases then passed. The subsequently added two applied-lineage cases passed. Preserved logs: `independent.log`/`independent-initial.log`, `independent-rerun.log`, `stale-goal-rerun.log`, `lineage.log`. There is no remaining failed desired-behavior assertion.

## Independent evidence

- **Durability and lost responses:** discard a successful request response, construct a fresh FastAPI app and authenticated client against the same database, recover the queued job using only the owner path, and resume the same job. Construct another app/client after completion and recover the succeeded job with one attempt. Re-running a completed job is refused without another model invocation. This simulates loss of the client response/state after a real commit; it is not a browser/network-abort test. IEP discard outcome is recovered afterward. Teaching recovery likewise survives a new app/client and resumes the existing queued job.
- **Exact owner/basis selection:** two independent valid IEP bases on the same current revision are both recoverable. Fixture jobs with another learner, wrong kind, unknown basis, wrong reference revision, multiple source references or another purpose are excluded. The committed suite proves that a new manual plan revision excludes older bases. Independently revising a teaching session to a different current basis yields an empty list and the new session revision ID.
- **Authorization and recalls:** wrong school and assistant/guardian/technical roles are denied. A teacher with owning access but without purpose-specific AI authority is denied. Revoking current AI authority or owning write access is denied. Revoked exact case-read permission and removed evidence-read permission retain safe metadata with `availability: review_required`; the existing job output endpoint refuses access. Revoked processing policy, model release, missing runtime/provider configuration and a superseded active goal make jobs unavailable without rewriting their recorded queued/succeeded state. Stale teaching proposals remain blocked at the existing diff gate.
- **Pagination and no output/model invocation:** both committed IEP and independent teaching probes reach 103 matching jobs across 50/50/3/0 pages with unique IDs, stable repeated ordering and no model calls. The extra rows are synthetic fixture rows, not 103 independently executed jobs. SQL event guards reject any SELECT of `platform_generation_jobs.output`; guards pass for ordinary recovery and, independently, for an IEP basis whose current revision already contains applied generation lineage. SQL evidence is saved as `plan-query-*`, `teaching-query-*` and `lineage-query-*`. Every response item is checked against exactly nine allowed metadata keys, excluding output, source manifest, review prose and model settings. Invalid offset/limit requests are rejected.
- **Session-specific outcomes:** two authorized sessions sharing one immutable basis recover the same job. Rejecting it in one session leaves the other session's outcome unset; accepting selected support in the other produces its own `accepted` outcome while preserving the first session's `rejected` outcome. A separate same-learner basis does not join this list. The existing run/diff/review commands remain the action gates; listing metadata does not itself approve or apply content.

All reviewer test processes completed and were explicitly awaited. Fixture teardown closed the local protocol servers and disposed engines. A direct read-only namespace check verifies that all ten PostgreSQL schemas recorded by the independent runs have been removed (`cleanup.log`); no demo database or unrelated schema was touched. Only this new report and ignored review evidence were written. UI reload/relogin/resume affordances remain a required separate job, and this review does not establish complete feature, practitioner, legal or production readiness.

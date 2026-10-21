# Owned learning source projections — independent review

Exact candidate: `a0bcab2ac738605fe754ae16d5d4337d810276f5`. Independent reviewer: `review_j05`. **Bounded acceptance: no actionable finding.** This review covers only the two new source projections and their tests, not the downstream J10 feature or assessment decisions.

Read `AGENTS.md`, both production modules and the directly used authorization, scheme/source, delivery/participation and qualification checks. Reviewed scheme selection requires native curriculum and current original-source authority, a reviewed exact revision, valid inclusive date bounds, stored rule/content digest agreement and explicit approval metadata. It returns source references rather than original pages and marks grading/exemption authority `unassessed`. Actual-work projection authorizes the selected pupil, selects only that pupil's participation, rejects an old corrected delivery revision and omits sibling/group narrative, other participants and staff totals. Qualification recall changes current support assessment to `unassessed` while preserving the originally reported status; it creates no follow-up, audit or event.

Frozen archive: `var/review-owned-learning/pinned`, created with `git archive` of the exact candidate. Both commands below used absolute `PYTHONPATH=/Users/lauritz/Programming/SpesPed/var/review-owned-learning/pinned/backend:/Users/lauritz/Programming/SpesPed/var/review-owned-learning/pinned/backend/tests`, shared `.venv` only as a Python runtime, and `SPESPED_TEST_POSTGRES_URL` set to the authorized loopback test database at 127.0.0.1:55432. No demo database, shared source imports or other service ports were used.

```
# cwd: frozen archive
/Users/lauritz/Programming/SpesPed/backend/.venv/bin/python -m pytest backend/tests/test_owned_learning_projections.py -q
# cwd: repository root
/Users/lauritz/Programming/SpesPed/backend/.venv/bin/python -m pytest var/review-owned-learning/test_independent.py -q
```

Results: committed suite **14 passed** on SQLite/PostgreSQL in 17.47 seconds; final independent suite **4 passed** on both databases in 5.36 seconds. All processes completed and were awaited. Evidence is under `var/review-owned-learning/`.

The independent probes add exact inclusive boundary checks; datetime/date confusion rejection; unauthorized roles and wrong school/pupil denial; detection of an external committed rule change despite cached ORM state; revoked/withdrawn original source checks; preservation of pending source deletion and selected-pupil edits; no implicit flush/commit/rollback or DML while returning a valid projection with a staged audit; and later explicit flush/rollback of caller-owned work. Initial scaffolding attempted direct ORM writes to immutable rule/participation records; the existing immutable guards correctly refused them. Only the ignored probes were corrected: fixture tamper restoration uses SQL update, and the pending immutable edit is expected to remain staged until the explicit flush correctly refuses it, followed by rollback. The original failure log is preserved; no desired-behavior failure remains. The supplied qualification-recall test additionally patches flush/commit/rollback, records SQL verbs and checks audit/outbox/follow-up counts and an empty pending-state set.

`isolation-cleanup.log` verifies actual archived module/fixture paths, byte identity of all three candidate files, and absence of all four unique PostgreSQL schemas recorded by the independent runs after fixture teardown. No production files, commits, pushes, agents, external messages or real pupil data were involved. This projection acceptance does not confer grading, exemption, entitlement fulfilment or progress conclusions and does not establish full-feature/legal/production readiness.

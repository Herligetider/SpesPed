# Independent review: J05 timestamp-offset digest repair

21 October 2026. Reviewer: independent `review_plan_offset` worker. **Accepted for this narrow repair; no actionable findings.** This does not approve the entire J05 feature set, dependent jobs, or production readiness.

## Reviewed source and isolation

Pinned commit: `5c676a8951cc4aed5a268b300ed342e1154391bd`. Parent used for independent before/after reproduction: `d00c118665e6d9acaf1a94c2d173328b1bb3ca31`.

Reviewed the complete two-file diff and relevant schema, persistence, snapshot, lifecycle, replay, historical goal, and generation callers:

- `backend/spesped/contexts/plans/service.py`
- `backend/tests/test_plan_offset_canonicalization.py`

Reviewed source came from `git archive` into `var/review-plan-offset/archive`; the baseline used a separate parent archive at `var/review-plan-offset/baseline`. Both changed-file SHA-256 hashes exactly match `var/j05-offset/owned-hashes.json`: service `be0939c451776bdc6d3fb4bf9469d2d78571c69efef26489c49df878f9f2b971`, tests `b12abce0f9bd64c043a0d3da518ab85c21f0abe70e518c7fbc280c9afcb48fba`.

Used Python 3.12.13 from the repository's `backend/.venv/bin/python`, SQLite, and the assigned local PostgreSQL 17.11 test database. Every test invocation set **absolute** archive `backend:backend/tests` PYTHONPATH entries. Runtime inspection independently confirmed both `spesped.contexts.plans.service.__file__` and `plans_fixtures.__file__` resolve inside the reviewed archive. PostgreSQL fixtures create/drop their own UUID schemas. No unrelated server, process, or schema was changed.

## Assessment

The cause and repair align: `UTCDateTime` converts bound/reloaded values to UTC, while the attached new revision can retain its input offset during initial hashing. `new_content_values` normalizes the newly constructed plan, goal, contribution and allocation datetime column values before hashing. It is applied through `save_plan`, which serves native creation, native revision and generated revision application. All these command timestamp fields require aware datetimes. Adaptations have no datetime fields.

The change leaves shared canonical hashing, snapshot serialization, request hashing, migrations, historical rows and original-approval JSON serialization unchanged. New positive, negative and UTC representations survive reload, exact review, approval and activation; wrong digests and changed persisted instants still fail. Microseconds and goal effective-time queries are exercised. Existing valid approved history, original approval JSON with a non-UTC timestamp, historical goal binding, recorded digests and approval records remain exact.

Idempotency still hashes the submitted command before normalization; replaying the identical request succeeds, while changing its offset representation under the same key conflicts. Scope, source access, authority, transactional rollback and concurrent commands were also covered by the nearby regression suite.

A reviewer-authored adverse test recreated an offset-corrupt record through the former write behavior. Reload/review still report `revision_conflict`. Creating and activating a new normalized revision preserves the old corrupt revision's content, old digest, draft state, empty approval binding and absence of approval records. The repair therefore does not silently rehash or bless corrupted history.

## Independent execution

All logs, JUnit results and the reviewer-only adverse test are retained under `var/review-plan-offset/`.

| Run | Result | Evidence |
| --- | --- | --- |
| Original J11 reproduction against parent archive | Expected 2 failures for offset input, 2 passes for UTC; both databases show the same contrast | `baseline.txt`, `baseline.xml` |
| New focused suite plus original J11 reproduction against reviewed archive | 18 passed, no skips | `focused-repro.txt`, `focused-repro.xml` |
| Reviewer legacy-corruption/history boundary against reviewed archive | 2 passed, SQLite and PostgreSQL | `test_review_boundaries.py`, `reviewer-boundaries.txt`, `reviewer-boundaries.xml` |
| Nearby plans, assembly and generation regressions against reviewed archive | 111 passed, 3 SQLite-only concurrency skips; all 57 PostgreSQL cases passed | `regressions.txt`, `regressions.xml` |
| Commit diff whitespace check | Passed | `git diff --check 5c676a8^ 5c676a8 -- backend/spesped/contexts/plans/service.py backend/tests/test_plan_offset_canonicalization.py` |

The baseline failures occur at exact native review with `The stored content no longer matches its review digest.` The repaired original reproduction passes all four combinations. Existing dependency/schema/OpenAPI warnings remain visible in the logs and did not fail these runs.

Commands used the following environment and argument sets (repository root `/Users/lauritz/Programming/SpesPed`):

```sh
export SPESPED_TEST_POSTGRES_URL='postgresql+psycopg://spesped_test:synthetic-development-only@127.0.0.1:55432/spesped_test'
export PYTHONPATH='/Users/lauritz/Programming/SpesPed/var/review-plan-offset/archive/backend:/Users/lauritz/Programming/SpesPed/var/review-plan-offset/archive/backend/tests'
# Both variables were passed in each command's environment.
/Users/lauritz/Programming/SpesPed/backend/.venv/bin/python -m pytest \
  /Users/lauritz/Programming/SpesPed/var/review-plan-offset/archive/backend/tests/test_plan_offset_canonicalization.py \
  /Users/lauritz/Programming/SpesPed/var/j11-documents/repro_plan_offset_digest.py \
  -q --junitxml=/Users/lauritz/Programming/SpesPed/var/review-plan-offset/focused-repro.xml
/Users/lauritz/Programming/SpesPed/backend/.venv/bin/python -m pytest \
  /Users/lauritz/Programming/SpesPed/var/review-plan-offset/test_review_boundaries.py \
  -q --junitxml=/Users/lauritz/Programming/SpesPed/var/review-plan-offset/reviewer-boundaries.xml
# Regression cwd was the reviewed archive.
/Users/lauritz/Programming/SpesPed/backend/.venv/bin/python -m pytest \
  backend/tests/test_plans.py backend/tests/test_plan_assembly.py backend/tests/test_plan_generation.py \
  -q --junitxml=/Users/lauritz/Programming/SpesPed/var/review-plan-offset/regressions.xml
```

The baseline command ran the same original J11 repro with absolute `baseline/backend:baseline/backend/tests` PYTHONPATH entries and `baseline.xml` as its result path. Exit 1 was expected and inspected: only the two offset variants failed.

## Bounded decision and retained limits

Accept commit `5c676a8951cc4aed5a268b300ed342e1154391bd` for normalization of newly persisted typed plan timestamps before exact revision digest creation. No code fix is requested. Previously corrupt records remain unresolved and fail closed; they need an explicitly authored valid revision rather than migration or automatic rehash. This review makes no claim about unrelated features, external deployments or production operations.

No implementation files, commits or shared contracts were changed by this reviewer. The only tracked reviewer output is this report; reviewer artifacts remain in the dedicated `var/review-plan-offset` directory.

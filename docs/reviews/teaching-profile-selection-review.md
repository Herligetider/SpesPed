# Exact teaching profile selection review

- Reviewed commit: `3df0a501d66ddc263dc180833eade5f90e5094ee`, limited to its three-file parent diff.
- Reviewer: `/root/review_composition`, independent of the root implementation author.
- Review date: 2026-10-21.
- Verdict: **accepted for this bounded profile-selection repair; no blocking findings**.

## Accepted scope

`plans/service.py:81–110` adds an internal exact-statement filter after the existing school/learner authorization and before state filtering, source projection and pagination. It keeps the existing public list limits and history behavior. The statement query refreshes previously loaded ORM objects, so a cached statement does not override a committed change.

`teaching/service.py:89–98,124–129` uses the chosen statement IDs both when creating a basis and when checking its later currency. A confirmed statement remains selectable beyond the first public page. Only the selected statements affect this comparison: an unrelated statement's dispute does not invalidate the basis. Foreign, missing, proposed, replaced or recalled selections do not become usable through the exact-ID filter.

The live profile is encoded using the same JSON representation as its persisted teaching snapshot before hashing. Aware observation and review timestamps therefore do not raise the previous serialization error or spuriously invalidate the saved basis. Existing source and learner checks, exact human approval, and the separate metadata-only assistant currency gate remain in place.

## Method and results

The reviewer used a separate `git archive` under `var/review-teaching-profile-selection/pin`. Execution used the shared Python 3.12 runtime with the following absolute imports, independently checked in `import-origins.log`:

```text
/Users/lauritz/Programming/SpesPed/var/review-teaching-profile-selection/pin/backend
/Users/lauritz/Programming/SpesPed/var/review-teaching-profile-selection/pin/backend/tests
```

Tests ran against SQLite and actual PostgreSQL configured through `SPESPED_TEST_POSTGRES_URL`. Each PostgreSQL fixture created and removed a unique temporary schema in the synthetic test database. No demo schema, real pupil data, external model service or external messaging was used. Existing AI regressions use synthetic local loopback services.

| Verification | Result | Saved log |
| --- | --- | --- |
| Exact-pin new selection tests plus original plan/profile and teaching suites | 127 passed, 5 expected SQLite skips, 200.15 s | `var/review-teaching-profile-selection/pinned-regressions.log` |
| Independent adverse selection and currency probes | 14 passed, no skips, 26.68 s | `var/review-teaching-profile-selection/independent.log` |
| Reviewed patch whitespace | Passed | `git diff --check 3df0a50^ 3df0a50` |

The test commands were:

```text
python -m pytest backend/tests/test_teaching_profile_selection.py backend/tests/test_plans.py backend/tests/test_teaching.py -q
python -m pytest var/review-teaching-profile-selection/test_independent_selection.py -q
```

The first command ran from the archived tree; the second ran from the repository with the same absolute archived imports. The reviewer waited for both processes and inspected their logs. The only reported warning is the existing FastAPI/Starlette TestClient deprecation.

## Independent evidence

The ignored reviewer probe `var/review-teaching-profile-selection/test_independent_selection.py` verifies these seven scenarios on both databases:

1. With 105 earlier statements and two later choices, the first public page excludes both choices. Selecting the later IDs in reverse order creates a current basis preserving that explicit order. Observation input uses a non-UTC offset; stored observation/review timestamps normalize to UTC and produce identical results on repeated fresh HTTP reads and idempotent replay. Disputing an unselected earlier statement leaves this basis current.
2. A mix of a valid choice with a different learner's statement, another school's statement, a missing ID, or an unconfirmed proposal is rejected. The internal exact read returns only the authorized learner's matching ID; a teacher without the other learner's teaching scope is denied before selection.
3. Confirming a replacement through the public workflow preserves the original statement and review history while suppressing the previous session and assigned assistant brief. Replaying the old basis is rejected as stale; a new basis can use the confirmed replacement.
4. Revoking the creator's current `profile.read` permission suppresses that user's saved basis/session prose and blocks a new selection. The independently authorized assistant still receives the reviewed assigned brief, without gaining access to the full profile.
5. Revoking the creator's current `evidence.read` permission has the same protected-read behavior. Revoking one user's raw-source permission does not silently revoke another user's valid curated assignment.
6. Reassigning the supporting evidence to a different learner through the correction workflow hides the chosen profile's prose/source and suppresses both the teacher session and assistant brief. A new basis cannot reuse that recalled statement.
7. A service session with a warm profile object and teaching basis observes a separately committed review change. The exact query refreshes the object and the digest comparison correctly makes the old basis non-current.

The original suites additionally cover profile dispute/correction/history, original source revision recall, historical plan bindings, cross-learner sources, stale approvals, revoked authority, transaction rollback, dated teaching/assistant assignments and PostgreSQL concurrency. Expected SQLite-only skips concern checks requiring actual PostgreSQL locks or deadlock behavior; their PostgreSQL variants ran.

## Limits

Acceptance covers the exact-selection and normalized profile-digest repair at this pin. It does not declare the complete teaching workflow, practitioner UI, all features, deployment readiness or later commits accepted. No entitlement fulfilment or staff qualification is inferred from the chosen profile or passing tests. No legal sources were re-researched. The reviewer modified only this report and ignored review artifacts, and did not commit or push.

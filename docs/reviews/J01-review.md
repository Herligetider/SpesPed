# J01 independent review

Latest recheck: `1895d8876a15ce9a05a4e7c5f2667244a203e6df` — **J01 verified within its assigned foundation scope; all five findings resolved**. See the appended final residual recheck and retained limits below.

- Reviewer: independent `review_j01` worker, 21 October 2026.
- Candidate: `da754c695bdadf4f031eb2f00ab15b364afd5fda`.
- Scope: `.env.example`, `backend/**`, excluding `backend/spesped/domain/**` and `backend/tests/test_domain_core.py`.
- Decision: **changes requested**. Four reproducible findings follow. No implementation files were changed by this review.
- Read: `AGENTS.md`, `docs/09-domain-implementation.en.md`, `docs/10-master-plan.en.md`, and complete F01/F02/F27/F34 entries in `docs/features.json`.
- The shared checkout advanced to `9ac02a22f272f7a8090d67d8e43a73325ff6b541` during review. `git diff da754c695bdadf4f031eb2f00ab15b364afd5fda -- .env.example backend ':!backend/spesped/domain/**' ':!backend/tests/test_domain_core.py'` was empty after verification: the tested J01 files still exactly matched the pinned candidate. Unrelated workers' changes were left alone.

## Findings

### J01-R1 — [P2] Initial protected-case authority cannot be issued through the supported management API

Location: `backend/spesped/auth.py:128–131`, with the case match at `:98` and bootstrap grants in `backend/spesped/cli.py:43`.

`require_delegation` passes the requested case ID into the lookup for `authority.delegate`. `require_authority` requires an exact case match, so the explicitly school-wide bootstrap delegation (`case_id = NULL`) never matches. The fallback requires the actor to possess the very case permission being created. There is consequently no API path to issue the first grant for any case, even for the provisioned leader with explicit delegation and authority-management powers. The existing case test inserts the grant directly into the database and misses this path.

Reproduction, verified independently on SQLite and PostgreSQL:

1. Provision a school with the supported bootstrap, and an active teacher membership.
2. Sign in as its bootstrap leader.
3. `POST /api/v1/schools/{school_id}/authorities` with `{user_id: teacher_id, action: "case.read", learner_id: an_active_local_learner, case_id: a_UUID, valid_from: today}`.
4. Observed **403 access_denied**. The same request without `case_id` succeeds for the leader.

Provide an explicit authorized path for initial case delegation. Keep ordinary case-content authorization exact: making every case permission match a school-wide grant would defeat the separate case boundary. Case existence and school/learner ownership must be supplied by the future case module; the present finding is the unreachable delegation bootstrap, not a claim that case content endpoints exist.

### J01-R2 — [P2] A scoped assignment manager can create access but cannot revoke it

Location: `backend/spesped/contexts/identity/router.py:285–288`; related list restriction at `:272` versus scoped creation at `:211`.

Creation deliberately accepts `assignment.manage` scoped to the target learner. The generic update endpoint instead checks the same action with no learner ID, requiring school-wide management before it looks up the assignment. A manager who is properly authorized for one pupil can grant that pupil's access but cannot revoke the grant, shorten it, or even list their managed assignments. Granting broader school authority to perform an immediate revocation would violate the intended scope separation.

Reproduction, verified on both databases:

1. Give the teacher `assignment.manage` and explicit `learner.read` authority, both scoped to pupil A; give no school-wide management authority.
2. As that teacher, create a `learner.read` assignment for another active member and pupil A. Observed **201**.
3. PATCH that exact new assignment through `/access/assignments/{id}` with `expected_version: 1`, `state: "revoked"`, and the original validity period. Observed **403**, leaving the access active.

Evaluate management authority against the record's actual learner scope on update and filter management lists to authorized scope, while preserving generic denials for hidden records. The analogous scoped `guardian.manage` create/update paths should be checked too.

### J01-R3 — [P2] Concurrent first login failures bypass the configured attempt count

Location: `backend/spesped/contexts/identity/router.py:42–58`.

`SELECT ... FOR UPDATE` locks only an existing throttle row. When none exists, concurrent requests all perform password verification before attempting to insert the same key. One insert succeeds; every losing transaction receives a uniqueness conflict and rolls back its failure count. This permits a parallel password-guess burst beyond the configured limit and records only one attempt. It also produces misleading 409 business conflicts at the login endpoint.

PostgreSQL reproduction: start six requests for one account with no throttle row and `login_attempt_limit=3`. Synchronize immediately after the actual Argon2 verification to deterministically expose the first-row race. Observed statuses **[409, 401, 409, 409, 409, 409]**, persisted `failures=1`, and `blocked_until=NULL`. A seventh incorrect login was still **401**, not throttled. The synchronization hook changes scheduling only; password checking, transactions, HTTP routing, and persistence remain real.

Create/claim the throttle key atomically before verification, or retry conflicting creation within a bounded transaction so every attempted check is counted. Add a PostgreSQL parallel-first-attempt test. This finding concerns the first-row race; the existing-row sequential throttle tests pass.

### J01-R4 — [P2] Delegation period ignores the actor's expiring school membership

Location: `backend/spesped/auth.py:128–133`.

The delegation period is bounded only by the selected `AuthorityGrant`, even though effective authority also requires an active dated school membership. An actor whose school access ends today can delegate an unbounded right starting tomorrow if their underlying authority row has no end date. That actor has no effective authority during any part of the new grant's period. This conflicts with the helper's explicit rule that managers delegate only authority they hold in the requested effective period, and weakens temporary access boundaries.

Reproduction, verified on both databases:

1. Use an active technical manager with the existing explicit `authority.manage` grant; end their membership today.
2. Give them an explicit pupil-specific `learner.read` authority whose stored end date is NULL.
3. As that user, POST a `learner.read` authority for another active member, same pupil, with `valid_from=tomorrow` and `valid_until=NULL`.
4. Observed **201** with an unbounded future grant, despite the delegator's school access ending today.

Bound delegable periods by the intersection of the relevant current membership and content/delegation grant. Add tests where one component expires earlier than the other. This finding does not assume that revoking a delegator should retroactively revoke every independently issued grant; it concerns accepting a grant whose entire requested validity already lies outside the delegator's known effective scope.

## Verification evidence

Executed from `/Users/lauritz/Programming/SpesPed` using Python 3.12, the locked backend environment, and the supplied local synthetic PostgreSQL 17 database. Each PostgreSQL fixture migrates its own uniquely named schema and drops it afterward.

```sh
SPESPED_TEST_POSTGRES_URL='postgresql+psycopg://spesped_test:synthetic-development-only@127.0.0.1:55432/spesped_test' \
  uv run --project backend pytest backend/tests/test_foundation.py -q
```

Result: **25 passed**, no PostgreSQL skips, 7.79 seconds. One Starlette/httpx deprecation warning.

Additional temporary review harness: `/tmp/j01_review_adversarial.py`, using the existing `env` fixture and isolated schemas. It was not added to implementation files.

```sh
PYTHONPATH=backend/tests \
SPESPED_TEST_POSTGRES_URL='postgresql+psycopg://spesped_test:synthetic-development-only@127.0.0.1:55432/spesped_test' \
  uv run --project backend pytest /tmp/j01_review_adversarial.py -q -s
```

Result: **11 passed, 1 skipped**, 2.99 seconds. The skipped case is deliberately SQLite concurrency; that same concurrency case ran on PostgreSQL. These assertions document the observed defects as well as successful controls, so this harness passing does **not** accept the candidate.

A focused rerun with `-k schoolwide_delegate` added the same `case.read` request without a case ID as a positive control: **2 passed, 10 deselected**, 0.86 seconds; the case-scoped requests stayed 403 while their otherwise identical non-case requests returned 201.

Confirmed controls:

- Real login/logout/rotation, hashed opaque sessions, Argon2id passwords, expiry, disabled user rejection, exact Origin and CSRF checks, and production cookie attributes.
- Forged identity headers do not authenticate. Current assignments, school memberships, school state, learner state, expired case scope, cross-school IDs, unrelated pupils, guardian relationships, assistants, and technical management without content/delegation rights fail closed in the exercised paths.
- Filtering occurs before pagination/counting. Safe validation errors do not echo pupil input or credentials.
- Version conflicts and actual SQLAlchemy concurrent snapshots reject overwriting an intervening update on both databases.
- Migrations execute on both databases, and the composite learner-school foreign key rejects a cross-school assignment.
- Additional injected `IdentityEvent.before_insert` failure produced HTTP 500 and rolled back the learner change, its version increment, success audit, and outbox event on both databases. Persisted learner remained grade 4/version 1 with no new success audit or event.
- Production settings reject the exercised unsafe defaults; explicit synthetic provisioning has no built-in password and is rejected in production. Static inspection found no application logging of raw session tokens or passwords.

## Limits and completion boundary

This is a review of J01 foundation only, not acceptance of full F01, F02, F27, or F34. Case objects/content, rich pupil profiles, recipient dispatch, identity-provider/account lifecycle, rights handling, production encryption/key management, restore drills, outbox consumers, queue claiming/delivery reconciliation, and full school administration remain separate work. A UUID in `case_id` is not proof of a valid case/learner relationship; downstream case modules must enforce that relationship before calling the authority helper. Assignment purpose is stored, but this slice does not establish full downstream purpose-based processing controls.

The review did not exercise a deployed TLS proxy, external identity provider, browser accessibility, production database permissions, backup/restore, or external services. Existing-row login throttling and basic optimistic concurrency were verified, but this is not a general load/security penetration test. No current-law/compliance claim is made. The scoped assignment/authority findings must be fixed and independently rechecked before dependent modules treat this boundary as verified.

## Recheck at f38b06142252fea78b7f20c0b094227fade3a230

Independent recheck on 21 October 2026. **J01-R1 through J01-R4 are verified fixed. Changes remain requested because the throttle repair exposes J01-R5 below.** The preceding candidate findings and evidence are retained as history. Only this review document was changed; the tested foundation paths matched `f38b06142252fea78b7f20c0b094227fade3a230` exactly (`git diff` against that commit was empty for the assigned implementation scope).

| Finding | Independent recheck result |
|---|---|
| J01-R1 | Fixed. Bootstrap leader can issue the first case grant (201) while still failing case-content authorization. A case-specific delegate can issue within that case but cannot widen to another case, pupil, or unscoped permission. Ordinary case authorization remains exact. |
| J01-R2 | Fixed. Learner-scoped assignment **and guardian** managers can list, count, paginate, shorten, and revoke records within their learner scope. Other-learner and missing IDs return the same denial; a hidden record stays unchanged. Shortening/revocation works after the manager's content authority is revoked. |
| J01-R3 | Original first-row lost-count race fixed. Six simultaneous first failed PostgreSQL login requests at limit three result in three 401s and three 429s, exactly three password checks, persisted failures three, and a current block. A correct-password follow-up remains 429 without another password check. See the separate success/reset race below. |
| J01-R4 | Fixed. Membership, explicit delegation, and content-authority periods each constrain the full delegated period. Earlier starts, later/unbounded ends, and wholly future grants outside membership fail; an inclusive matching end is accepted. Both assignment and authority creation are covered. |

Independent supplemental checks also verified both **assignment and authority** updates on SQLite and PostgreSQL: a management-only actor cannot extend or reactivate access; can shorten and revoke it; can reactivate after receiving exact dated content authority; and still cannot extend beyond that authority's end. No public Python signature or HTTP shape changed in these repairs.

### J01-R5 — [P2] Successful login can delete a throttle row between another request's upsert and lock

Location at this candidate: `backend/spesped/contexts/identity/router.py:46–49`, `:59–61`, and `:74`.

The new claim function runs `INSERT ... ON CONFLICT DO NOTHING` and then a separate `SELECT ... FOR UPDATE`. When the key already exists, PostgreSQL's conflict/no-op insert does not reserve that row until the subsequent select. A concurrent successful login can lock and delete it in the gap. The waiting request then receives `None` from `claim_login_throttle`, dereferences `throttle.blocked_until`, and returns **500 internal_error**. This also breaks a competing login with valid credentials, so ordinary concurrent reauthentication can fail after this repair.

Exact deterministic reproduction against the migrated PostgreSQL schema, real HTTP handlers, and real Argon2:

1. POST one incorrect login for the synthetic teacher. It returns 401 and creates a committed throttle row.
2. Start login A for that same account. Pause it in the SQLAlchemy engine's `after_cursor_execute` hook immediately after its `INSERT INTO identity_login_throttles ... ON CONFLICT DO NOTHING` returns, before the helper's select. The hook only controls interleaving; it does not change SQL, rows, or password verification.
3. While A is paused, run login B with the correct password through a separate `TestClient` and database session. B returns **200** and commits deletion of the throttle row.
4. Resume A. It returns **500**, instead of 401 for an incorrect password or 200 for a correct one. Both variants were independently reproduced.

Keep the claimed throttle row stable while serializing requests, for example resetting its counters/window in place under the existing row lock after success, or otherwise make claim/retry tolerate a disappeared row without bypassing throttling. Add this existing-row success/failure and success/success interleaving to the PostgreSQL regression tests. The original first-attempt burst test should continue to assert both counters and password-check count.

### Recheck commands and evidence

Same synthetic PostgreSQL 17 DSN and per-test migrated/drop-on-exit schemas as the initial review; no connection to the separate web review database.

```sh
SPESPED_TEST_POSTGRES_URL='postgresql+psycopg://spesped_test:synthetic-development-only@127.0.0.1:55432/spesped_test' \
  uv run --project backend pytest backend/tests/test_foundation.py -q
```

Result: **38 passed, 1 skipped**, 11.66 seconds. The only skip is intentional SQLite row-lock concurrency; PostgreSQL concurrency ran. One Starlette/httpx deprecation warning. I did not rerun or independently claim the reported full-backend/domain total, since the foundation is this recheck's scope.

Temporary independent harness `/tmp/j01_review_recheck.py` imports the candidate's isolated `env` fixture, but adds its own extension/reactivation checks and the success/delete interleaving:

```sh
PYTHONPATH=backend/tests \
SPESPED_TEST_POSTGRES_URL='postgresql+psycopg://spesped_test:synthetic-development-only@127.0.0.1:55432/spesped_test' \
  uv run --project backend pytest /tmp/j01_review_recheck.py -q -s --tb=short
```

Result: **4 passed, 2 failed, 2 skipped**. All four assignment/authority scope-update checks passed. Both PostgreSQL reset races failed their expected-status assertion: B returned 200 and A returned 500 for each competing-password variant. The two skips are intentionally PostgreSQL-only race tests on SQLite. The temporary harness is available to the implementer for repair verification and was not added to implementation files.

The original completion limits remain: this foundation does not complete F01/F02/F27/F34; case object ownership, downstream purpose checks, recipient dispatch, and production operations are still outside the verified slice. The review uses real database/HTTP security boundaries, but does not substitute for deployed TLS, full browser, external identity-provider, or operational verification.

## Final residual recheck at 1895d8876a15ce9a05a4e7c5f2667244a203e6df

Independent verification on 21 October 2026. **J01-R5 is verified fixed; J01-R1 through J01-R5 are closed. J01 is verified for its assigned foundation scope, with no outstanding finding from this review.** This disposition supersedes the historical changes-requested decisions above; their reproductions and evidence remain intact.

The repair replaces successful-login deletion with an in-place reset of `failures`, `window_started_at`, and `blocked_until` while retaining the claimed row lock (`backend/spesped/contexts/identity/router.py:74–80`). I inspected the exact candidate delta and reran both the foundation suite and my independent harness, without modifying implementation files.

- The original deterministic PostgreSQL success/failure interleaving now returns **200 and 401**, rather than 200 and 500.
- The original success/success interleaving now returns **200 and 200**. The added candidate regressions also verify that the stable row remains, counters reflect the final request, and each successful login has a distinct usable session.
- The first-attempt parallel-failure regression continues to enforce the configured limit before excess password checks: three 401s, three 429s, three checks, and a persisted block. A correct password cannot bypass that block.
- The suite retains the prior case-content separation, scoped assignment/guardian management, and membership/authority-period checks. My supplemental assignment/authority extension and reactivation checks also still pass on both databases.

Commands, executed against the same synthetic PostgreSQL 17 DSN and isolated schemas used above:

```sh
SPESPED_TEST_POSTGRES_URL='postgresql+psycopg://spesped_test:synthetic-development-only@127.0.0.1:55432/spesped_test' \
  uv run --project backend pytest backend/tests/test_foundation.py -q

PYTHONPATH=backend/tests \
SPESPED_TEST_POSTGRES_URL='postgresql+psycopg://spesped_test:synthetic-development-only@127.0.0.1:55432/spesped_test' \
  uv run --project backend pytest /tmp/j01_review_recheck.py -q -s --tb=short
```

Independent results: **40 passed, 3 skipped** in 12.28 seconds for the foundation suite; **6 passed, 2 skipped** in 2.29 seconds for the independent harness. Every skip deliberately excludes a PostgreSQL row-lock test from the SQLite variant; all corresponding PostgreSQL cases ran. Both commands emitted only the previously noted Starlette/httpx deprecation warning.

HEAD started at the pinned candidate and advanced to `df8c5d2077f33e43ff857bf2c2c1faf6a4e5086b` during the shared checkout's unrelated work. After both runs, `git diff 1895d8876a15ce9a05a4e7c5f2667244a203e6df -- .env.example backend ':!backend/spesped/domain/**' ':!backend/tests/test_domain_core.py'` remained empty. The tested J01 implementation therefore exactly matched the requested candidate. Only `docs/reviews/J01-review.md` was edited by this recheck; no commit, push, new agent, or external service operation was performed.

**Retained limits:** this verifies the J01 foundation slice, not complete F01/F02/F27/F34 or production readiness. Case ownership/content, full downstream purpose enforcement, recipient dispatch, full account lifecycle, production encryption/key management, restore drills, outbox processing, and broader school administration remain their assigned jobs. No deployed TLS, external identity provider, full browser, current-law, or operational acceptance is implied. The full backend/domain suite was not independently rerun in this residual review.

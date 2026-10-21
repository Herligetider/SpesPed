# Independent typed teaching gateway review

Initial reviewed pin: `5e9afe15094c71de65d5bef3ce08839777c1c6c1`.
Final independently accepted repair pin: `ac555498c0f8741d77d567075913b2e75a173779`.
Comparison base: `ddc29707262696c9fdd37379602caf2b063a8f43`.
Review date: 2026-10-21.

## Verdict

**Accepted within the reviewed gateway scope at `ac55549`; no open findings.**
Both P1 authorization findings and the P2 metadata transaction-preservation
finding are independently verified as fixed. The typed generation schema, local
wire adapter, release binding and metadata-only predicate passed the checks below.
This report does not accept J06, a real teaching-source consumer, route composition
or the separate UI candidate.

The following original findings and intermediate verdicts are retained as
historical evidence. The final repair recheck is recorded at the end.

## Finding

### P1 — Refresh cached actor and school state before returning a current result

Pinned location: `backend/spesped/contexts/platform/service.py:363-366`
(`current_job`), delegating to `_authorize` at lines 40-57 and the existing
`backend/spesped/auth.py:81-85` identity checks.

`current_job` promises current authorization within a consumer-owned transaction,
but only refreshes the generation job and processing configuration. If that
session retains an active `UserAccount` or `School` ORM identity, another
transaction can disable that row and commit; subsequent `current_job` calls still
return the successful job and its output. `require_school_access` uses `db.get`
for these two rows, so the identity map supplies the old `state == 'active'`
without a new read. Calling `_authorize` twice does not refresh them.

Reproduction, using synthetic local-wire generation:

1. Finish a typed `session_planning` job.
2. In a reader session, retain `reader.get(UserAccount, actor.user_id)` (or the
   school row) and successfully call `current_job`.
3. In a separate writer transaction, change that same row's `state` to `disabled`
   and commit.
4. Call `current_job` again in the reader. Expected: 403. Actual: the successful
   aggregate, including generated output, is returned.

The independent desired-behavior test
`var/review-teaching-gateway/test_independent_probes.py::test_current_job_rejects_disabled_cached_actor_or_school`
reproduces all four combinations: SQLite/user, SQLite/school, PostgreSQL/user,
PostgreSQL/school. The test fails with `DID NOT RAISE DomainError` in every case.
Refresh these authority-bearing identities before the port authorizes access,
while preserving the caller's transaction and avoiding a broad session reset.
Add a regression for a retained identity and committed concurrent disablement.

The underlying auth helper predates this commit. This finding concerns the new
port's current-state guarantee in a caller's already populated session; it does
not claim that the new schema introduced the original helper behavior.

## Isolation and scope

- Read repository `AGENTS.md` and the teaching contract in
  `docs/09-domain-implementation.en.md`; reviewed all seven changed files.
- Archived the exact pin to `var/review-teaching-gateway/5e9afe1`, rather than
  importing the active shared checkout. Every Python/pytest invocation used an
  absolute `PYTHONPATH` to that archive, optionally followed by its `backend/tests`.
- An explicit probe verifies `platform.service.__file__` is inside the archive
  and `spesped.contexts.teaching` has no importable spec at this pin. The existing
  editable virtualenv cannot supply the uncommitted J06 context to these tests.
- Used `/Users/lauritz/Programming/SpesPed/backend/.venv/bin/python` (Python 3.12),
  SQLite and the supplied PostgreSQL test instance. PostgreSQL fixtures created
  unique temporary schemas and dropped them; no demo schema was used.
- Generated synthetic data over localhost HTTP only. The remote-attestation
  predicate test changes persisted binding metadata solely for the predicate;
  it makes no remote model request.
- No production edits, commits, pushes or subagents were used for this review.

## Verification

Primary pinned regression command, run from the archived repository root:

```sh
PYTHONPATH=/Users/lauritz/Programming/SpesPed/var/review-teaching-gateway/5e9afe1/backend:/Users/lauritz/Programming/SpesPed/var/review-teaching-gateway/5e9afe1/backend/tests \
SPESPED_TEST_POSTGRES_URL=postgresql+psycopg://spesped_test:synthetic-development-only@127.0.0.1:55432/spesped_test \
/Users/lauritz/Programming/SpesPed/backend/.venv/bin/python -m pytest \
backend/tests/test_teaching_gateway.py backend/tests/test_ai_gateway.py \
backend/tests/test_context_integration.py backend/tests/test_intake_structuring.py -q
```

Final regression result: **182 passed, 7 skipped** in 248.49 seconds. The seven
skips are the expected SQLite-only exclusions for PostgreSQL concurrency checks.

Independent probe command, using the same environment and archived working
directory:

```sh
/Users/lauritz/Programming/SpesPed/backend/.venv/bin/python -m pytest \
/Users/lauritz/Programming/SpesPed/var/review-teaching-gateway/test_independent_probes.py -q --tb=short
```

Result: **8 passed, 4 failed** in 11.09 seconds. The four failures all reproduce
the single finding above. The passing probes verify archive isolation, safe 503
when the teaching context is absent, direct resolver scope rejection, additional
typed bounds, unknown actor rejection, absent runtime returning 503, changed
provider binding rejection, and no autoflush of a pending consumer event by the
metadata predicate. Both test runs reported the existing FastAPI/Starlette
TestClient deprecation warning.

The pinned suites additionally cover:

- `session_planning` requires a learner and exactly one `teaching_basis`, with
  separate `ai.session_planning` authority; other purposes cannot use the basis.
- Typed content rejects duplicate/unknown/missing references, blank text,
  coercible or boolean minutes, missing support, extra approval fields, generic
  output and tool calls. Results remain unconfirmed and require human review.
- Releases require matching `teaching-session.v1` template/schema and reviewed
  evaluation evidence for the exact purpose. Cache-warmed release, policy,
  evaluation evidence and reviewed-evaluation digest recalls fail closed.
- Actor authority revocation, source revocation and changed source content block
  full current-result reads and idempotent replay. Metadata eligibility alone
  deliberately does not validate source access, dependency currency or actor
  permission.
- Metadata queries select no generation output, perform only SELECT statements,
  preserve transaction rollback, reject wrong school/invalid ID/missing runtime
  or provider, and require a current exact operator attestation plus the allowed
  development boundary for remote synthetic metadata eligibility.

Independently ran the release-digest algorithm from archived accepted base
`ddc2970` and the candidate with identical fixed provider/model inputs. Both
returned the same hashes:

| Template | SHA-256 at both pins |
| --- | --- |
| `bounded-suggestion.v1` | `a0aed6acc8d675173cf94fce8403328729a29ac2cec6cf9fb5dcf31e2533f2ae` |
| `intake-structuring.v1` | `0ab69f0c5adba3599cb4508daa5787c57a978e7b214de48509d1c087142529ed` |

## Remaining boundary

At this pin `EvidenceSourceResolver` safely rejects session generation with
`teaching_context_unavailable` (503) because the teaching context is not installed.
The gateway tests use an explicit synthetic basis resolver. They verify this
gateway contract; they do not establish the actual J06 goal/source/support
resolver, persistent teaching selection and approval, assistant projection
dependency checks, business audit/outbox atomicity, HTTP composition or UI.

## Independent repair recheck — 381b012

Repair pin: `381b0120c1ab5fa0b70d0049c86a76c3b660036c`.
Archived separately to `var/review-teaching-gateway/381b012`; all repair Python
commands used the absolute backend and tests paths inside that archive.
The original archive and desired-behavior probes were preserved. A copy named
`var/review-teaching-gateway/test_repair_probes.py` changes only the expected
archive path in the import-isolation assertion.

**Repair verdict: changes still required.** The initial UserAccount/School
finding is fixed and independently verified, but the assignment-action branches
below still return output after a committed authority reduction.

The repair refreshes `UserAccount` and `School` with `populate_existing=True`
inside platform `_authorize`, then checks their current active state. The
preserved four previously failing probes pass, and the new committed regression
also exercises `get_job` and idempotent creation after these deactivations.

The existing full repair run completed without a restart:

```sh
PYTHONPATH=/Users/lauritz/Programming/SpesPed/var/review-teaching-gateway/381b012/backend:/Users/lauritz/Programming/SpesPed/var/review-teaching-gateway/381b012/backend/tests \
SPESPED_TEST_POSTGRES_URL=postgresql+psycopg://spesped_test:synthetic-development-only@127.0.0.1:55432/spesped_test \
/Users/lauritz/Programming/SpesPed/backend/.venv/bin/python -m pytest \
/Users/lauritz/Programming/SpesPed/var/review-teaching-gateway/test_repair_probes.py \
backend/tests/test_teaching_gateway.py backend/tests/test_ai_gateway.py \
backend/tests/test_context_integration.py backend/tests/test_intake_structuring.py -q --tb=short
```

Result: **198 passed, 7 expected SQLite skips** in 256.43 seconds, with the same
existing TestClient deprecation warning.

### P1 — Refresh retained staff-assignment actions on both authorization paths

Pinned locations at `381b012`:
`backend/spesped/contexts/platform/service.py:59-62` (session-planning authority)
and the existing `backend/spesped/auth.py:114-116` (learner-read authority), reached
from the new `current_job` port.

Both queries filter active assignment rows in SQL, but use `assignment.actions`
from an existing ORM identity without refreshing it. With school-wide fallback
`learner.read` and `ai.session_planning` grants revoked, create one active dated
assignment containing both actions and retain it in a reader session. The first
`current_job` call succeeds. In another transaction, replace that assignment's
actions with a list that removes either `ai.session_planning` or `learner.read`,
leaving the row active, and commit. The next reader call still returns the
successful job output using the cached action list. Expected: 403 for either
removed action.

Independent desired-behavior probe:
`var/review-teaching-gateway/test_assignment_action_probes.py::test_current_job_rejects_removed_cached_assignment_action`.
Run it with the same repair environment and working directory:

```sh
/Users/lauritz/Programming/SpesPed/backend/.venv/bin/python -m pytest \
/Users/lauritz/Programming/SpesPed/var/review-teaching-gateway/test_assignment_action_probes.py -q --tb=short
```

Result: **4 failed** in 4.87 seconds: SQLite and PostgreSQL for both removed
actions, all failing with `DID NOT RAISE DomainError`. Refresh the retained
assignment action lists before checking them in both branches; fixing only the
platform-specific action check leaves the learner-read branch vulnerable.
This underlying auth query also predates the gateway extension; the finding
concerns its reuse by the new current-result port in a populated consumer
transaction. The source resolver remains an explicit synthetic fixture, so this
finding and any repair do not establish real J06 acceptance.

## Independent shared-authorization repair recheck — 6c96cef

Repair pin: `6c96cef0c65a1a12d8c519b4f7237ae65774ad5d`, archived separately to
`var/review-teaching-gateway/6c96cef`. The original independent probes remain
unchanged. `test_final_repair_probes.py` is a copy changing only the import
isolation assertion's expected archive path. The four previously failing
assignment-action probes were run unchanged against this archive.

**Authorization findings closed at this pin.** Current persisted user, school,
membership, learner and assignment values are refreshed in shared auth helpers,
and the gateway's purpose-specific assignment query also refreshes existing
identities. Both initial user/school cases and both assignment-action branches
now deny access after a committed change. The repair's committed test also
covers a retained membership whose role changes to guardian.

**Overall verdict: one additional P2 requires repair.** The metadata predicate's
no-mutation guarantee fails for pending configuration changes as detailed below.
This is independent of the now-verified shared-authorization repair.

Full pinned verification command:

```sh
PYTHONPATH=/Users/lauritz/Programming/SpesPed/var/review-teaching-gateway/6c96cef/backend:/Users/lauritz/Programming/SpesPed/var/review-teaching-gateway/6c96cef/backend/tests \
SPESPED_TEST_POSTGRES_URL=postgresql+psycopg://spesped_test:synthetic-development-only@127.0.0.1:55432/spesped_test \
/Users/lauritz/Programming/SpesPed/backend/.venv/bin/python -m pytest \
/Users/lauritz/Programming/SpesPed/var/review-teaching-gateway/test_final_repair_probes.py \
/Users/lauritz/Programming/SpesPed/var/review-teaching-gateway/test_assignment_action_probes.py \
backend/tests/test_teaching_gateway.py backend/tests/test_ai_gateway.py \
backend/tests/test_context_integration.py backend/tests/test_intake_structuring.py \
backend/tests/test_foundation.py -q --tb=short
```

Result: **248 passed, 10 expected SQLite skips** in 296.24 seconds. These include
the existing source/configuration recalls, exact intake source bindings,
idempotency, metadata output-selection boundaries and transaction checks, plus
broader foundation authentication and permission regressions. The same existing
TestClient deprecation warning remains.

Additional independent replay probe:
`var/review-teaching-gateway/test_current_replay_probes.py::test_warm_recall_denies_each_consumer_path`.
With the same archived environment, it reports **6 passed** in 7.24 seconds.
For each of `ai.session_planning` removal, `learner.read` removal and guardian
membership change on SQLite/PostgreSQL, three separate reader sessions retain
their own earlier assignment and membership identities. Following the writer
commit, `current_job`, `get_job` and idempotent `create_job` each deny with 403.

### P2 — Preserve pending configuration edits during metadata checks

Pinned location: `backend/spesped/contexts/platform/service.py:385-396`, where
`job_binding_is_current` disables autoflush and calls `_configuration`; the
configuration queries at lines 109-110 use `populate_existing=True`.

Within a caller-owned session, load the job's active `ProcessingPolicy`, change
`policy.state` to `revoked`, and leave it pending. The policy is in `db.dirty`.
Calling `job_binding_is_current` reloads the persisted active row without
flushing the pending edit, overwrites `policy.state` back to `active`, and clears
that pending edit. A later caller commit silently loses the intended recall.
Thus an ostensibly metadata-only predicate changes caller-owned ORM state and
can discard an intended policy revocation, contrary to its explicit contract.

Independent desired-behavior probe:
`var/review-teaching-gateway/test_metadata_nonmutation_probe.py::test_metadata_check_preserves_pending_policy_recall`.
Run it with the same `6c96cef` archive environment:

```sh
/Users/lauritz/Programming/SpesPed/backend/.venv/bin/python -m pytest \
/Users/lauritz/Programming/SpesPed/var/review-teaching-gateway/test_metadata_nonmutation_probe.py -q --tb=short
```

Result: **2 failed** in 2.82 seconds, on SQLite and PostgreSQL. Both fail the
postcondition `policy.state == 'revoked'` because the actual state is `active`.
Keep fresh persisted binding reads independent of tracked mutable configuration
identities, or fail closed for relevant pending edits without refreshing them
away. Preserve both the dirty value and its pending persistence; do not repair
this by committing or flushing caller changes from the metadata predicate.

All verification used the pinned archive and synthetic localhost wire only.
Separate uncommitted J05/J16 composition and J06 work were excluded. Actual J06
consumer, route and UI acceptance remain outside this review.

## Independent metadata repair recheck — ac55549

Final repair pin: `ac555498c0f8741d77d567075913b2e75a173779`, archived separately to
`var/review-teaching-gateway/ac55549`. All invocations used absolute `PYTHONPATH`
entries for this archive's `backend` and `backend/tests`, the existing Python 3.12
virtualenv executable, synthetic localhost HTTP and unique PostgreSQL schemas.

**Final scoped verdict: accepted; all findings closed.** The original unchanged
two-case nonmutation probe now passes on SQLite and PostgreSQL. Metadata
configuration validation reads Core column projections instead of tracked ORM
identities and rejects pending job/policy/release/evaluation edits or deletions
without flushing, committing, discarding or refreshing them. The default
configuration path retains fresh ORM reads and scopes policy, release and
evaluation to the job's school; independent wrong-school checks pass for both
default and metadata paths.

The final verification covers **104 distinct relevant cases**, all passing after
updating three obsolete optional-module assumptions as explained below. The
preserved metadata probe was additionally repeated twice. The existing TestClient
deprecation warning remains; there were no unexpected skips.

First relevant run:

```sh
PYTHONPATH=/Users/lauritz/Programming/SpesPed/var/review-teaching-gateway/ac55549/backend:/Users/lauritz/Programming/SpesPed/var/review-teaching-gateway/ac55549/backend/tests \
SPESPED_TEST_POSTGRES_URL=postgresql+psycopg://spesped_test:synthetic-development-only@127.0.0.1:55432/spesped_test \
/Users/lauritz/Programming/SpesPed/backend/.venv/bin/python -m pytest \
backend/tests/test_teaching_gateway.py \
/Users/lauritz/Programming/SpesPed/var/review-teaching-gateway/test_metadata_repair_probes.py \
/Users/lauritz/Programming/SpesPed/var/review-teaching-gateway/test_assignment_action_probes.py \
/Users/lauritz/Programming/SpesPed/var/review-teaching-gateway/test_current_replay_probes.py \
/Users/lauritz/Programming/SpesPed/var/review-teaching-gateway/test_metadata_nonmutation_probe.py -q --tb=short
```

Result: **69 passed, 3 failed** in 79.83 seconds. All production-behavior and
preserved nonmutation/authorization cases passed, including the 16 committed
pending-edit/delete cases. The three failures came from original archive probes
asserting that no teaching package was installed. Unlike the initial gateway
pin, `ac55549` includes the committed teaching context and `j06_teaching.py`.
Its module resolved inside the exact archive, not the active shared checkout.
Calling that real context against the gateway fixture's intentionally J04-only
database consequently queried an absent `teaching_bases` table. This was an
obsolete fixture assumption, not evidence of a metadata repair failure.

The original historical probes remain untouched. Only the new copy
`test_metadata_repair_probes.py` now checks that any installed teaching package
resolves inside the frozen archive, and explicitly simulates an unavailable
optional teaching import when testing the 503 guard. Those three updated cases
and the unchanged two-case pending-policy probe were rerun together:
**5 passed** in 4.81 seconds. This simulated import check makes no claim about
actual J06 source authorization or migrations.

Second relevant run, using the same archived environment:

```sh
/Users/lauritz/Programming/SpesPed/backend/.venv/bin/python -m pytest \
/Users/lauritz/Programming/SpesPed/var/review-teaching-gateway/test_metadata_extended_probes.py \
backend/tests/test_ai_gateway.py::test_idempotent_completed_output_requires_current_reviewed_configuration \
backend/tests/test_ai_gateway.py::test_revoked_release_blocks_execution_and_existing_result_retrieval \
backend/tests/test_ai_gateway.py::test_source_authorization_and_revision_rechecked \
backend/tests/test_intake_structuring.py::test_recalled_configuration_blocks_replay_apply_read_and_unconfirmed_fields \
backend/tests/test_intake_structuring.py::test_source_revision_change_prevents_stale_output_and_apply -q --tb=short
```

Result: **32 passed** in 40.17 seconds. Independent extended probes set a pending
recall on each of policy, release, evaluation and job, verify that the predicate
returns false while preserving the dirty value and emitting only SELECTs, then
explicitly flush and commit as the owner. The intended change remains persisted
and subsequent metadata validation remains false. Separate probes verify
wrong-school policy/evaluation rejection in both configuration modes. Existing
gateway/intake tests retain committed configuration and source-revision recall
behavior across reads, replay and proposal application.

Prior wider regression evidence at `6c96cef` (248 passed, 10 expected SQLite
skips, plus 6 independent replay cases) remains applicable to the unchanged
authorization repair. No production files were edited and no commits, pushes
or external AI calls were made by the reviewer. Acceptance remains limited to
the typed teaching gateway and these consumer-validation ports; actual J06
integration and UI require their own independent acceptance.

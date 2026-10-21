# J08 independent backend recheck

Rechecked backend revision: `69c2572944ebb4a5f8ac2fc7d18cf5e0f24d253d`.

Verdict: **no remaining actionable finding in this reviewed backend subset**. Both findings below are independently resolved. This accepts the bounded gateway implementation changes; it does not declare F33, the wider J08 product workflow or production AI deployment complete.

The recheck includes the platform HTTP subprocess worker, shared result-visibility gate, persisted synthetic evaluation artifacts, operator-only artifact retrieval, artifact digest/review binding, models and revised migration. Subsequent HEAD advanced through unrelated governance and integration-test commits to `974833166854f74ce89ada5d6c8730fbc08719d8`; `git diff 69c2572 HEAD -- backend/spesped/contexts/platform backend/tests/test_ai_gateway.py backend/migrations/versions/j08_platform.py` was empty after verification. Platform code/tests/migration therefore match the exact pinned revision. No implementation/shared-contract files were edited by this reviewer.

## Resolved findings and new evaluation contract

- **P1 recall bypass resolved:** all three existing-job creation/replay branches and the obsolete-worker return now use `_require_visible`, which rechecks actor/source authorization and current reviewed configuration before returning stored output. Existing completed-result withdrawal tests cover policy/release revocation, missing provider, changed template and changed local processing boundary. Independent probes separately re-ran the original policy/release recall and PostgreSQL expired-worker/new-result scenarios, now expecting explicit rejection. They passed and no recalled output was returned.
- **P2 overall deadline resolved:** the parent enforces an elapsed deadline around the isolated HTTP process, kills and reaps it on timeout or caller interruption, and closes private pipes. The child also has an inherited absolute Unix alarm. Independent real-socket slow-header verification returned `provider_timeout` after **1.00 s**; caller interruption returned after **0.51 s**. In both cases the peer observed connection closure, the child had exited and was reaped, and stdin/stdout were closed. The baseline also verifies slow body, silent peer, interruption, and concurrent worker cleanup. No abandoned HTTP thread or socket was observed.
- **Private child boundary verified:** independent probes inspected every child launch during generation/OCR/speech/embedding evaluations. The synthetic API token appeared only in the private stdin request and intended local HTTP Authorization header, never argv or child environment. An unrelated secret environment variable and configured HTTP proxy were absent from the child environment. stderr is discarded; errors return fixed safe codes. Source content and credentials are absent from process arguments.
- **Reviewable evaluation artifacts verified:** exact synthetic text/binary inputs, source digests, successful output, failure code/state and timings are persisted separately from operational metrics. Inputs/outputs have aggregate budgets and suites have a case cap. Authorized operators retrieve the artifact through the exact school/evaluation endpoint; the paginated list excludes content. The reviewed release binds the artifact digest, and altered evidence blocks output visibility. Independent evaluations exercised all four actual local protocols and verified UTF-8/base64 input preservation, nonempty output, digest binding and professional review. Root integration tests retrieve exact inputs/outputs before requesting review.

## Recheck commands and results

The synthetic PostgreSQL test DSN remains the one recorded in the original evidence below. Commands ran from the repository root:

```sh
PYTHONPATH=backend backend/.venv/bin/pytest -q backend/tests/test_ai_gateway.py
PYTHONPATH=backend backend/.venv/bin/pytest -q var/review-j08/test_recheck_gateway.py
PYTHONPATH=backend backend/.venv/bin/python var/review-j08/probe_deadline_recheck.py
PYTHONPATH=backend backend/.venv/bin/python var/review-j08/probe_migration.py
```

- Gateway suite: **94 passed, 7 skipped**, 86.76 s. Skips are SQLite counterparts of PostgreSQL concurrency checks; the PostgreSQL variants passed.
- Independent updated recall/resolver/media/artifact/child-boundary checks: **23 passed, 1 skipped**, 20.99 s. The skipped variant requires PostgreSQL and passed there.
- Independent deadline probe: slow headers **1.00 s**, caller interruption **0.51 s**; both confirmed peer closure, child reaping and closed pipes.
- Isolated PostgreSQL `j08_platform -> a9e1f00151e4 -> j08_platform` roundtrip passed again with the revised artifact columns.
- Existing Starlette/httpx TestClient deprecation is the only test warning.

The old defect-positive probes in `var/review-j08/test_independent_gateway.py` are retained as historical evidence and intentionally assert the old behavior. Current verification uses `test_recheck_gateway.py`; the historical probe suite is not a current passing acceptance suite.

The root assembly/source resolver now has its own separate independent review in `docs/reviews/context-integration-review.md`. Actual production hardware, local model quality, school-approved fixture adequacy, professional review quality and the complete UI/workflow remain outside this software-boundary verdict. Pre-attribution AI structuring, an owned clarification queue, dictated-audio and protected-case source adapters remain explicit future work.

---

## Archived initial review: 9f8ca976

Reviewed revision: `9f8ca976dbf03c261e3e33e2f0ebc04a7a762f2c` (HEAD verified before and after review).

Verdict: **changes required**. Two reproducible findings block acceptance of the intrinsic backend gateway. Passing tests do not establish F33 completion or production model quality.

## Scope and requirements

Read `AGENTS.md`, complete F33 in `docs/features.json` (including workspace, stateBehavior, automationBoundary and recovery), and `docs/09-domain-implementation.en.md`. Inspected platform contracts/models/providers/service/router/exports, `j08_platform` migration, and gateway tests. Actual adverse verification used synthetic localhost HTTP servers and isolated PostgreSQL schemas in the test database. No external AI call, real pupil data, shared demo schema, implementation edit, commit or push occurred.

The production source resolver and application configuration are a separately owned root integration candidate, outside this revision. The tests here exercise the public resolver contract and trusted synthetic provenance boundary; they do not establish that an arbitrary implementation of that port authorizes evidence/intake correctly. Runtime unavailable without a configured resolver/provider/synthetic suite is intentional.

## Findings

### [P1] Recheck configuration before returning previously completed output

Location: `backend/spesped/contexts/platform/service.py:241-248` (also lines 255-260, IntegrityError replay at 291-299, and obsolete-worker return at 391-397).

`get_job` blocks a completed result when its processing policy/release is revoked or its reviewed configuration is unavailable. The existing-job returns in `create_job` only call `_current_sources`, then return the entire ORM job, which the POST router serializes with `output`. A caller can therefore replay the same logical creation command and obtain a recalled model's output even though normal GET rejects it. This is a practical bypass of model/policy withdrawal, using an ordinary supported idempotent retry.

Reproduced independently for both release and policy revocation on SQLite and isolated PostgreSQL: create and run a successful job, revoke the configuration, observe GET service rejection, replay the identical `GenerationRequest`, and observe the original successful output returned. The independent test deliberately asserts the defective observed behavior, so its passing result proves reproduction rather than correctness.

A second PostgreSQL reproduction covers `run_job`: keep attempt 1 waiting in a real HTTP request; expire its lease; let attempt 2 succeed; revoke the release; resume attempt 1. The obsolete-worker branch returns attempt 2's successful output without `_configuration`, although GET rejects that exact output. The run router includes output whenever the returned job state is `succeeded`.

All output-return paths need the same current source/actor and reviewed-configuration visibility gate. Preserve idempotency/budget semantics and ensure rejected replay does not expose output. Test release/policy revocation and changed/unavailable runtime configuration, including the expired-worker/retry branch.

### [P2] Enforce the elapsed deadline while response headers arrive

Location: `backend/spesped/contexts/platform/providers.py:64-77`.

The configured `httpx.Timeout` limits inactivity for individual I/O operations. The elapsed-time checks begin only after `client.stream(...)` has received the complete response headers. A server can send a header every fraction of a second and retain the worker indefinitely despite `timeout_seconds`; the job lease does not terminate that blocked request.

A raw synthetic localhost server sent `HTTP/1.1 200 OK`, then eight header lines spaced 350 ms apart, then a two-byte JSON body. `_post(timeout=1)` returned `provider_timeout` only after **2.86 seconds**. Increasing the number of header lines extends the wait because no elapsed-deadline check runs while headers are being accumulated. A continuously active but unhealthy local provider can therefore pin synchronous request/worker capacity past the configured processing budget.

Apply a real overall deadline covering connection, request write, response headers and body, with cancellation that actually closes network work. Add a real socket slow-header test (and preserve slow-body/ordinary timeout tests); a timeout wrapper that merely abandons a still-running background call would not provide the claimed bound.

## Verification commands and results

Commands ran from `/Users/lauritz/Programming/SpesPed`, with:

```sh
export SPESPED_TEST_POSTGRES_URL='postgresql+psycopg://spesped_test:synthetic-development-only@127.0.0.1:55432/spesped_test'
PYTHONPATH=backend backend/.venv/bin/pytest -q backend/tests/test_ai_gateway.py
PYTHONPATH=backend backend/.venv/bin/pytest -q var/review-j08/test_independent_gateway.py
PYTHONPATH=backend backend/.venv/bin/python var/review-j08/probe_slow_headers.py
PYTHONPATH=backend backend/.venv/bin/python var/review-j08/probe_migration.py
```

- Existing gateway suite: **66 passed, 3 skipped**, 44.23 seconds. The three skipped cases are SQLite-only counterparts of PostgreSQL concurrency tests; their PostgreSQL executions passed.
- Independent probes: **15 passed, 1 skipped**, 11.32 seconds. Four tests prove idempotent output-return bypass after release/policy revocation across both database engines; one PostgreSQL test proves the obsolete-worker bypass. Ten checks confirm malformed resolver results (wrong school, learner, purpose, reference, duplicate return) are rejected across both engines. The sole skip is the intentionally PostgreSQL-only obsolete-worker test's SQLite parameter.
- Slow-header probe: `{"configured_timeout": 1, "actual_elapsed": 2.86, "error": "provider_timeout"}`.
- Independent migration verification: isolated PostgreSQL schema upgrade to `j08_platform`, downgrade to its exact parent `a9e1f00151e4`, and upgrade again passed. All six platform tables were restored; the isolated schema was removed.
- Only warning: existing Starlette/httpx TestClient deprecation, unrelated to these findings.

The existing suite meaningfully exercises real local generation/OCR/speech/embedding wire protocols, model response identity for generation/embeddings, JSON/citation/tool-call rejection, input/output limits, source revision/access checks, infrastructure-only denial, CSRF/session use, claim serialization, daily-budget/idempotency serialization, cancellation, source revocation during work, retry history, explicit expiration, unavailable-provider/manual fallback, transactional outbox and result-read audit behavior. These checks support the reviewed backend boundaries but do not supersede the reproduced gaps.

## Remaining integration/deployment limits

Production hardware, real local model quality, professional fixture adequacy, operational recovery workers, source-context resolver composition and the separate UI remain unverified here. Prompt separation and unconfirmed/citation-requires-review flags are verified structural safeguards; a canned synthetic HTTP server cannot establish that a deployed model resists all injection or grounds factual claims. Evaluation stores suite/release digests and requires an explicit quality review, but actual deployment approval still needs approved synthetic fixtures and human assessment.

The root's proposed intake resolver deliberately requires clean current source revision, exact active learner link and `evidence.intake` authority, restricting intake refs to `evidence_extraction`; pre-attribution AI OCR remains an integration limitation, not a capability proved by this gateway test suite.

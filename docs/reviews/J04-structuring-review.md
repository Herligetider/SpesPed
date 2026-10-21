# J04 intake structuring independent review

Review date: 21 October 2026. Reviewer: `/root/review_intake_structuring`, distinct from the implementation owner and root assembly author.

**Verdict: changes required.** The bounded intake structuring candidate has one independently reproduced model recall bypass. This review does not establish complete delivery of F03–F05 or F33.

## Exact revisions and scope

Implementation candidate: `849dd6342dfd48bcc77e54ec4ee2f36a5a38c30a`. Root schema/model registration followup: `4599b3411d474317dc6e5f05e96f2fa88c16efde`. Accepted base: `0a3883f`.

All execution used a fresh `git archive 4599b3411d474317dc6e5f05e96f2fa88c16efde` at `var/review-intake-structuring/pinned`. Explicit `PYTHONPATH=/Users/lauritz/Programming/SpesPed/var/review-intake-structuring/pinned/backend` avoided the editable environment importing the evolving shared checkout. The migration probe explicitly printed and asserted the pinned paths for `spesped`, assembly, evidence service and gateway service. Tests and Alembic configuration came from that archive. Shared J16 implementation and root manifest changes were left untouched.

Read `AGENTS.md`, complete F03/F04/F05/F33 (including workspace, state behavior, automation boundary and recovery), `docs/09-domain-implementation.en.md`, and the historical J04, J08 and context-integration independent reviews, including their fix rechecks. Inspected assigned assembly, evidence, platform, schemas, models, migration and tests. Reviewed the root `b2_integrate_intake_plans` merge and entitlements/plans model imports for schema composition only. Intrinsic J05 entitlement/plan behavior and its unregistered routers/goal validator belong to the separate J05 review.

## Finding J04-SR1 — P1: manual proposal replay returns recalled model output

Location: `backend/spesped/contexts/evidence/service.py:245–248`; response serialization at `backend/spesped/contexts/evidence/router.py:197–199`.

The manual `propose()` command checks current intake authority, source version and exact span, but its existing-proposal branch returns a model-owned proposal without `require_proposal_model_access()`. The HTTP route serializes the entire proposal, including its generated origin, reviewed value and review reason. Consequently the normal model proposal list and review routes can refuse a recalled result while this supported idempotent manual command returns it.

Independently reproduced through authenticated HTTP on **both PostgreSQL and SQLite**:

1. Evaluate and professionally review the distinct intake structuring model, generate successfully and apply its unconfirmed proposals.
2. Edit the model's `goal` proposal to a synthetic replacement canary with a review reason.
3. Revoke its model release; `GET /intake/{source}/proposals` now returns 503.
4. Fetch the current source version, then `POST /intake/{source}/proposals` using the original goal span, field name and proposed value.
5. The manual command returns **201**, the same model proposal ID and generated-job ID, plus the edited `reviewed_value` and `review_reason` that were not supplied by this replay.

The existing model-proposal return needs the same current visibility gate as other proposal/result paths. Preserve an explicit manual recovery path without laundering a recalled model proposal into a manual response. Merely hiding the field in list queries does not close this route.

Supplemental reproduction: `var/review-intake-structuring/test_adverse_review.py::test_manual_proposal_replay_bypasses_model_recall`. Its assertions intentionally describe the defective observed behavior; a passing reproduction means the defect exists.

## Independent evidence

The distinct `intake-structuring.v1` / `intake-structure.v1` contract uses literal synthetic pages and persists exact evaluation inputs, typed outputs, digests and explicit professional review. It does not relabel generic suggestion output. The resolver requires one current intake source, no learner UUID, current school intake authority, clean/accepted inspection, ready extraction and a preserved original whose bytes match its digest. Model source text is serialized as untrusted data; no tools are offered, and tool-call outputs are rejected. Fields retain exact page/offset/quote, bounded typed values and hours units; mentioned learner names remain unconfirmed text. Generation/application do not create evidence or legal rights, and field review plus explicit scoped evidence confirmation remain separate commands.

The supplied tests exercise current permission/policy/source revision changes during real local HTTP work, current source/result replay gates, denied ordinary pupil-team access to whole intake material, controlled confirmed excerpts, typed invalid outputs, recalled proposal listing, manual fallback, failed-attempt recovery and successful retry, distinct logical applications, owner validation/reassignment, resolution/reopen/history, sibling tasks, confirmation/completion states and rollback/audit/outbox behavior. These software protocol fixtures do not establish professional quality of a real deployed model or comprehensive injection resistance.

Additional reviewer probes independently verify PostgreSQL concurrent application of the same attempt produces one application and two expected tasks; concurrent resolution using one expected version produces one success and one 409, preserving a single transition history. Changed extracted page content invalidates prior results/replays/applications even with the same original source revision. Missing original bytes block previously successful result reads/replays. The recall bypass above is additional to these passing adverse checks.

## Migration verification

In a unique synthetic PostgreSQL schema, Alembic exposes exactly one head, `b2_integrate_intake_plans`. Upgrade creates **76 tables including `alembic_version`**. `command.check()` reports no new upgrade operations, including the registered entitlement/plan metadata. Head → base → head restores the exact table set, and the isolated schema is dropped afterward. Existing proposal-span/outcome and job-state checks remain present; the new subject check enforces null learner only for intake structuring, and clarification state/resolution/span checks remain present.

Probe and log: `var/review-intake-structuring/probe_migration.py`, `var/review-intake-structuring/migration.log`. An initial reviewer probe used guessed table names in an assertion after the successful metadata check; it failed, cleaned up its schema, and was corrected to actual table names before the successful complete roundtrip. This was not a product defect.

## Commands and results

All commands used `/Users/lauritz/Programming/SpesPed/backend/.venv/bin/python` or its `pytest`, explicit pinned `PYTHONPATH`, and synthetic data. PostgreSQL URL: `postgresql+psycopg://spesped_test:synthetic-development-only@127.0.0.1:55432/spesped_test`; every test/probe created and removed its own schema. No demo schema, external model, external messages or real pupil data were used.

The supplied combined run executes from the archive root:

```sh
PYTHONPATH=/Users/lauritz/Programming/SpesPed/var/review-intake-structuring/pinned/backend \
SPESPED_TEST_POSTGRES_URL='postgresql+psycopg://spesped_test:synthetic-development-only@127.0.0.1:55432/spesped_test' \
SPESPED_TEST_CLAMD_SOCKET=/Users/lauritz/Programming/SpesPed/var/clamav/clamd.sock \
SPESPED_TEST_TESSERACT=/opt/homebrew/bin/tesseract \
SPESPED_TEST_PDFTOPPM=/Users/lauritz/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/override/pdftoppm \
SPESPED_TEST_TESSDATA=/Users/lauritz/Programming/SpesPed/var/tessdata \
/Users/lauritz/Programming/SpesPed/backend/.venv/bin/pytest -q \
backend/tests/test_intake_structuring.py backend/tests/test_ai_gateway.py \
backend/tests/test_evidence.py backend/tests/test_context_integration.py
```

- Supplied four-suite run: **183 passed, 8 skipped in 236.41 s**. The eight skips are SQLite counterparts of PostgreSQL concurrency checks; PostgreSQL variants passed. Actual configured clamd clean/EICAR and Tesseract PNG/scanned-PDF processing ran successfully.
- Reviewer adverse probes: **8 passed, 2 skipped in 19.50 s**. Two passing cases positively reproduce J04-SR1; six passing cases exercise the additional boundaries described above. The two skips are SQLite counterparts of the two PostgreSQL row-lock scenarios.
- Shared migration probe: **passed** with clean metadata and the complete head/base/head roundtrip.
- Existing Starlette/httpx TestClient deprecation is the only warning.

From the shared repository root, supplemental commands were:

```sh
PYTHONPATH=/Users/lauritz/Programming/SpesPed/var/review-intake-structuring/pinned/backend \
SPESPED_TEST_POSTGRES_URL='postgresql+psycopg://spesped_test:synthetic-development-only@127.0.0.1:55432/spesped_test' \
backend/.venv/bin/pytest -q -s var/review-intake-structuring/test_adverse_review.py
PYTHONPATH=/Users/lauritz/Programming/SpesPed/var/review-intake-structuring/pinned/backend \
SPESPED_TEST_POSTGRES_URL='postgresql+psycopg://spesped_test:synthetic-development-only@127.0.0.1:55432/spesped_test' \
backend/.venv/bin/python var/review-intake-structuring/probe_migration.py
```

Logs are in `var/review-intake-structuring/baseline.log`, `adverse.log` and `migration.log`.

## Remaining scope

J07 must supply the actual inbox/source review, clarification-owner and correction user flows. Protected-case and dictated-audio source consumer adapters, production local model/hardware quality, and any remaining source-helper ownership refactor remain separate implementation/review work. F05 still requires owned corrective followup for already shared derivative corrections, and real consumers must register/reconcile exact dependencies. This review does not claim those downstream requirements are complete.

The reviewer edited only this tracked report; all probes/archive/logs remain in ignored `var/review-intake-structuring/`. No commit, push or subordinate agent was created.

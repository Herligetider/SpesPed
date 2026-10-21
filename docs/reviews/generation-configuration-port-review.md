# Generation configuration port — independent review

Candidate: `ca3279b4e85c013c0998cedd9333a0ba98409192`.

**Verdict: accepted within the configuration read-port scope. No actionable findings.**

The reviewer is separate from the implementation author. The reviewed production
change is `validate_generation_configuration` and its identity-model imports in
`backend/spesped/contexts/platform/service.py`; the other candidate file is
`backend/tests/test_generation_configuration_port.py`.

This accepts an authorized configuration snapshot for an owner's durable request.
It does not accept scheduled document enqueue, its consumer transaction, report
generation, disclosure, or a complete feature. Configuration eligibility does not
authorize source processing.

## Exact source and execution

The commit was archived to `var/review-generation-configuration/pin`. Python
3.12.13 from `backend/.venv` ran with absolute frozen backend and test paths in
`PYTHONPATH`, overriding the editable install. `runtime.json` in the artifact
directory records the actual frozen service and fixture imports. Shared later
or uncommitted product changes were not used.

| Checks | Final result | Evidence under `var/review-generation-configuration/` |
| --- | --- | --- |
| Candidate `test_generation_configuration_port.py` and original `test_document_gateway.py` | 101 passed, no skips; 88.47 s | `original-tests.log` |
| Five independent scenarios, each for both document purposes on SQLite and PostgreSQL | 20 passed, no skips; 20.69 s | `independent-recheck.log`, `test_independent_configuration.py` |

Both database-backed sets ran against SQLite and actual PostgreSQL at
`127.0.0.1:55432/spesped_test`, using unique `j08_<uuid>` schemas. The commands used:

```text
PYTHONPATH=/Users/lauritz/Programming/SpesPed/var/review-generation-configuration/pin/backend:/Users/lauritz/Programming/SpesPed/var/review-generation-configuration/pin/backend/tests
SPESPED_TEST_POSTGRES_URL=<existing local synthetic PostgreSQL test DSN>
python=/Users/lauritz/Programming/SpesPed/backend/.venv/bin/python
python -m pytest <the two archived test files above> -q
python -m pytest var/review-generation-configuration/test_independent_configuration.py -q
```

The first independent run produced 16 passes and four failures caused by the
reviewer's incorrect expectation that remote school-data rejection occurred at
`create_job`. The existing gateway queues an authorized request, then rejects the
processing boundary in `run_job` before invoking the provider. The probe was
corrected to exercise that actual boundary and all 20 cases passed. The initial
log is retained as `independent-tests.log`; these were not product findings and
no product change was made to obtain the passing result.

All owned processes were awaited, including the failed probe attempt and final
recheck. Fixture teardown completed. `cleanup.json` independently confirms that
all 20 recorded PostgreSQL schemas from the two independent runs are absent and
all 40 recorded ephemeral loopback fixture ports are closed. The first regression
suite also completed its fixture teardown successfully. No shared listener,
global schema or demo data was changed; ports 8000, 5173 and 18878 were untouched.

The only warnings were the existing Starlette/httpx deprecation and curriculum
Pydantic field-name warning.

## Verified contract

- **No ownership of the caller transaction.** Event listeners observed no DML,
  flush, commit or rollback during normal reads or authorization/configuration
  failures. The original connection transaction remained active. Pending owner
  audit records remained unflushed and preserved. Already flushed, uncommitted
  caller changes remained uncommitted and were rolled back by the caller later.
  An uncommitted account revocation was visible to the reader, proving it used
  the caller's transaction rather than an independent connection.
- **Pending dependencies fail without discarding work.** New, dirty and deleted
  instances of all nine guarded models were independently exercised:
  `AuthorityGrant`, `Learner`, `School`, `SchoolMembership`, `StaffAssignment`,
  `UserAccount`, `ProcessingPolicy`, `ModelRelease`, and `ModelEvaluation`.
  Each returned `dependency_pending` without any SQL query from the port and
  without altering the pending object. Unrelated owner audit work remained
  compatible with the read, as required for atomic enqueue composition.
- **Current rights and configuration override stale caches.** Persisted account,
  school, membership and exact purpose-assignment changes denied reads despite
  caller-held stale objects; the caller objects themselves were not refreshed.
  The candidate tests additionally exercised persisted policy, release,
  evaluation, authority and learner revocation. Wrong school/learner, missing
  learner, unsupported purpose and missing configuration/runtime were denied.
- **Reviewed configuration remains exact.** A release successfully evaluated for
  one document purpose did not satisfy the other purpose. Changed evaluation
  evidence without its matching reviewed digest was rejected, including with a
  stale cached evaluation. Provider replacement and withdrawn private network
  authorization failed. The result contained exactly `policy_version` and
  `release_digest`, with no endpoint, credential, source, evaluation content or
  model output exposed.
- **Configuration does not substitute for source permission.** With a resolver
  that denied all source access, the eligible configuration read still succeeded
  and made no resolver call; actual job creation denied the source. No model
  request resulted from the new port.
- **Local and remote processing remain distinct.** The port rejected remote
  configuration in production and test environments, and in development without
  the explicit synthetic-development setting. A synthetic metadata fixture
  exercised the permitted development branch without contacting an external
  service or asserting a real remote evaluation. Eligible configuration with
  school-data provenance could be recorded, but the actual worker returned
  `remote_processing_forbidden`, no output, and never reached provider
  invocation. Existing document gateway tests exercised local typed generation,
  source freshness, review/evaluation binding and recall.

## Inspection and documentation

Inspection of `platform/service.py:177–220` confirms that the new port uses a
fresh `Session` identity map bound to the caller connection with
`join_transaction_mode='rollback_only'` and autoflush disabled. It delegates
purpose authorization and exact policy/release/evaluation checks to the existing
owner routines, copying the caller's runtime context in `db.info`. Success and
ordinary failure paths do not audit, create jobs, resolve sources or invoke a
provider. The existing gateway functions were not modified by the candidate.

The separately supplied, uncommitted paragraph beginning “Atomic document
scheduling uses” in `docs/09-domain-implementation.en.md` matches this port's
contract, including its transaction behavior and lack of source-processing
authorization. Its exact inspected text and SHA-256 are preserved in
`contract-note.txt` and `contract-note-sha256.txt`. That consistency check is not
acceptance of the scheduling consumer described by the paragraph. No shared
documentation other than this review report was edited.

The consumer must persist the exact returned binding with its own request and
recheck it before using the gateway. The gateway must still enforce current
source authorization, provenance and provider boundaries when processing.
End-to-end scheduled document atomicity, retry behavior, report review, dispatch
and UI are outside this review.

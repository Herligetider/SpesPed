# Reporting goal projection — independent review

Reviewed candidate: `e614152784c6962bbcf7076ec875d2b53d8007fd`.

**Verdict: accepted within the bounded owner read-port scope. No actionable RGP findings.**

The reviewer is separate from the implementation author. This review covers only
the candidate's addition to `backend/spesped/contexts/plans/projections.py` and
`backend/tests/test_reporting_goal_projection.py`. It does not accept the annual
report consumer, its application composition, its UI, or all of F18.

## Isolation and evidence

The exact commit was archived into `var/review-reporting-goals/pin`. All tests used
Python 3.12.13 from `backend/.venv` with **absolute** frozen backend and test paths
in `PYTHONPATH`. `var/review-reporting-goals/runtime.json` confirms that the actual
projection and fixtures imported from that archive, not the shared editable
checkout. Concurrent uncommitted document/administration changes were excluded.

Both SQLite and actual PostgreSQL at `127.0.0.1:55432/spesped_test` ran. Fixtures
created and dropped their own unique `j05_<uuid>` schemas. Both test processes
were awaited to exit code 0, including fixture teardown. No browser/server
listeners were started, no shared ports were touched, and no global schema or
demo data operation was performed.

| Verification | Result | Saved evidence |
| --- | --- | --- |
| Candidate projection tests plus original `test_owned_learning_projections.py` and `test_plans.py` | 83 passed, 3 expected SQLite skips; 130.43 s | `var/review-reporting-goals/original-tests.log` |
| Four additional reviewer scenarios, each on SQLite and PostgreSQL | 8 passed; 15.81 s | `var/review-reporting-goals/independent-tests.log` |

The three skips are the SQLite instances of tests requiring PostgreSQL contention,
row locks, or an actual SQLSTATE 40P01 deadlock. Their PostgreSQL instances passed.
The two warning categories were the existing Starlette/httpx deprecation and the
existing curriculum Pydantic field-name warning.

Reviewer probes are preserved in
`var/review-reporting-goals/test_independent_reporting.py`. The effective commands
used the following frozen environment, followed by `python -m pytest`:

```text
PYTHONPATH=/Users/lauritz/Programming/SpesPed/var/review-reporting-goals/pin/backend:/Users/lauritz/Programming/SpesPed/var/review-reporting-goals/pin/backend/tests
SPESPED_TEST_POSTGRES_URL=<existing local synthetic PostgreSQL test DSN>
python=/Users/lauritz/Programming/SpesPed/backend/.venv/bin/python
```

The first invocation selected the three archived test files named above; the
second selected the preserved reviewer probe file. No production source or
existing test file was changed by the reviewer.

## Verified behavior

- **Normal reads preserve the caller's transaction.** Connection/session event
  listeners observed no DML, flush, commit or rollback during successful and
  denied reads. The original connection transaction remained active. An already
  flushed, uncommitted account revocation was visible to the fresh reader and
  denied access, demonstrating that the reader shares the caller's transaction.
  A caller rollback subsequently restored the persisted account, confirming that
  the projection had not committed the caller's changes.
- **Pending objects are preserved.** New, dirty and deleted context objects each
  produced `dependency_pending` without any SQL query or flush from the projection.
  Their pending state and edited content survived. The candidate intentionally
  rejects pending context objects broadly; it does not silently flush them.
- **Historical dates do not grant historical permission.** Wrong learner and
  school, guardian, assistant and technical-administrator reads were denied.
  Current account, school membership and learner assignment revocations persisted
  by another session were respected despite cached caller objects. Those cached
  objects were not refreshed or overwritten by the projection.
- **IOP dependencies retain protected-case and source gates.** An ordinary
  teacher with plan access could not read an IOP lacking the exact case authority.
  Revoking the reviewer's case-read grant denied the historical read. Withdrawing
  a separate decision-only source blocked both old and new IOP goal revisions,
  even though the plan's own source remained valid and the caller held a stale
  cached source link. The existing tests also verify direct source withdrawal.
- **Imported validity and recorded activation stay separate.** A real imported
  IOP was created, reviewed, approved and activated through native HTTP services.
  A valid past goal instant remained readable before the later activation record.
  A narrower goal interval was returned precisely, including microseconds;
  equivalent offset-aware instants returned the same basis. The lower bound was
  inclusive, one microsecond before it was rejected, and the upper bound was
  exclusive.
- **Replacement keeps exact revision meaning.** A native revision of that same
  IOP retained the original goal's distinct title and revision identity for the
  old period and returned the new title and identity at the new period boundary.
  Activation clipped the old interval exactly. The old goal was rejected at the
  boundary and the new goal accepted. The author's separate-plan replacement
  scenario also passed. The existing teaching projection payload before and after
  report reads and supersession remained equal.

## Code assessment and limits

The new projection at `plans/projections.py:29–61` delegates to the existing
authorized `goal_reference` path through `teaching_goal_basis`. Inspection of that
owner path, plan activation, source binding validation and decision provision
resolution confirms that historical mode retains current actor and source checks,
exact confirmed decision references and reviewed-content digest validation.
`db.info` is copied into the fresh reader so the existing runtime-backed lineage
checks keep their context. The existing teaching port and metadata predicates are
unchanged by the candidate.

The reported interval is the intersection of declared goal and plan validity,
clipped by recorded supersession. `activation_recorded_at` is provenance, not a
replacement for the declared start of an imported plan. This read does not infer
delivery, learning progress, entitlement fulfilment, grades, professional
judgements or approval of report text.

Acceptance assumes the internal caller supplies the required aware `at` instant
and a validated actor under the existing application contract. A consumer must
still select the relevant exact goal revisions over its reporting period, retain
their labels and boundaries, and implement its own report review/disclosure and
currentness checks. This review did not run or accept the separately authored,
uncommitted annual ITO reporting workflow or claim full teaching/reporting feature
completion.

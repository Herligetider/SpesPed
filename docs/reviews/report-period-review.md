# BC03 reviewed reporting coverage — independent review

Candidate: `3be8177dcb38496bf336d92e4fd8ddecd716a38e`.

**Verdict: accepted within the BC03 exact reporting-period review and projection
scope. No actionable findings.**

The reviewer is separate from implementer `/root/j13_report_period`. All six
candidate files were inspected: the migration, governance models, projection
wrapper, new `report_periods.py`, router additions and candidate tests. F06 and
F18 in the pinned `docs/features.json` were used to check the distinction between
reviewed applicability/coverage, reporting content and actual fulfilment.

This acceptance does not close J11-R2 in the report consumer, finalize a report,
establish that a legal duty has been fulfilled, or accept all of F06/F18.

## Frozen source and results

The exact commit was archived to `var/review-report-period/pin`. Python 3.12.13
from `backend/.venv` ran with absolute frozen backend and test directories in
`PYTHONPATH`; the shared editable checkout was not imported. The SHA-256 of each
of the six candidate files, the full pin, Python version, actual implementation
and fixture import paths, and migration head are recorded in
`var/review-report-period/frozen-hashes.json`.

The frozen migration graph has one head, `j13_report_period`, directly following
`j11_documents`. The tests explicitly upgraded the tracked governance fixture to
that migration without any uncommitted J12 communication dependency.

| Checks | Terminal result | Evidence under `var/review-report-period/` |
| --- | --- | --- |
| Frozen `test_report_periods.py` | 47 passed, 1 expected SQLite race skip; 71.67 s | `candidate-tests.log` |
| Six independent scenarios, each on SQLite and PostgreSQL | 12 passed; 24.53 s | `independent-tests.log`, `test_independent_periods.py` |
| Selected original governance regressions | 12 passed, 35 deselected; 16.03 s | `regressions.log` |

Actual PostgreSQL ran at `127.0.0.1:55432/spesped_test` with fixture-owned UUID
schemas. The skipped test requires PostgreSQL locking; its PostgreSQL instance
passed. The two warning categories were the existing Starlette/httpx deprecation
and curriculum Pydantic field-name warning.

All three test handles were awaited to exit code 0, including fixture teardown.
`cleanup.json` independently confirms that the six recorded PostgreSQL schemas
used by the additional probes are absent. No listener was started, no global
schema or demo data was changed, and shared ports 8000, 5173 and 18878 were
untouched. The only tracked file created by this reviewer is this report.

The commands used this environment and `python -m pytest`:

```text
PYTHONPATH=/Users/lauritz/Programming/SpesPed/var/review-report-period/pin/backend:/Users/lauritz/Programming/SpesPed/var/review-report-period/pin/backend/tests
SPESPED_TEST_POSTGRES_URL=<existing local synthetic PostgreSQL test DSN>
python=/Users/lauritz/Programming/SpesPed/backend/.venv/bin/python
```

The original governance selection was:
`unresolved_applicability_inputs or document_is_not_performed_action or
rule_revisions_impact_binding or current_rule_withdrawal or protected_case_grant
or required_document_action_future`.

## Verified behavior

- **Explicit, exact inclusive dates.** Native GET provides a current basis digest
  and ledger version; POST binds the human review to both. The curated read
  requires the exact date pair and document kind. Different years, shortened or
  extended intervals, and a different document kind remain unresolved. A single
  day is valid when it is covered by the reviewed rule/profile. The opaque
  `period_key` and recorded deadline remain context and never supply inferred
  reporting dates. Legacy obligations without a review remain unresolved.
- **Relevant basis versus unrelated task changes.** Timing inputs, applicability
  inputs, the latest applicability decision, rule/profile binding, school kind,
  learner grade, period label and recorded deadline/timezone context are bound in
  the digest. Native timing/input changes invalidate an existing review and reject
  a stale preview. Native assignment, internal reminder, performed-action and
  resulting task-state/version changes did not change coverage. None of these
  operations silently inferred report completion.
- **Current original authority is checked separately.** Source rule withdrawal,
  profile revocation, original rule/profile reviewer authority, and the period
  reviewer's current task authority and learner scope are checked. An additional
  scenario used three different people for rule approval, profile approval and
  period review: withdrawing the profile approver's authority produced its own
  unresolved reason, independently of the period reviewer. Withdrawing the period
  reviewer's task authority then invalidated coverage while an authorized pupil
  reader could still obtain the curated unresolved result.
- **Profile coverage cannot cross supersession.** A native successor profile
  beginning 1 July invalidated full-year coverage on the predecessor. A new review
  for the single day 30 June was accepted; 1 July was not. Revoking the successor
  did not reactivate the predecessor for the successor's period. Old reviews
  remained unchanged in history.
- **Scoped authority and protected cases.** Ordinary current learner readers can
  consume curated metadata without management or AI authority. GET history and
  POST review require both task-management and task-review authority. Wrong
  school/pupil and unauthorized actors are denied. Protected-case obligations
  are denied by the new history, mutation and projection paths; ordinary pupil
  scope does not grant protected-case access.
- **Corrections, revocation and retry stay distinct.** Corrections and revocations
  append a new per-document-kind revision. Reusing the original exact request key
  after revocation returns its historical receipt, while a fresh GET/projection
  remains revoked and unresolved. Changed payloads conflict; expected-revision
  conflicts do not append. PostgreSQL same-key and competing-revision races passed.
- **Reads preserve caller work.** Instrumentation of successful and denied
  projection/history reads observed no DML, flush, commit or rollback. Unflushed
  owner audit/outbox records were retained; flushed caller work stayed within the
  caller transaction and could be rolled back by the caller. An already flushed
  account revocation was visible on that same transaction. Pending new, dirty and
  deleted dependencies were rejected without SQL or mutation. Persisted changes
  were checked through a fresh identity map without overwriting caller caches.
- **Immutable history and atomic writes.** Review, audit, command receipt and
  outbox changes rolled back together after the injected late outbox failure.
  Event revision and actor metadata matched the saved review. ORM update/delete
  guards worked on both databases; PostgreSQL direct SQL update/delete protection
  also passed. The migration preserves existing obligations, matches the mapped
  table, supports an empty round trip, and refuses downgrade with retained reviews
  or even with retained report-period outbox events alone.

## Acceptance limits

Inspection of `report_periods.py:87–128` confirms that coverage is derived from
the reviewed rule/profile and current applicability context, not from task
completion. The native review command at lines 159–193 owns its write transaction;
the fresh read paths preserve the caller transaction. The metadata projection at
lines 196–222 returns unresolved reasons and no usable `report_period` when an
exact review is missing, mismatched, revoked or no longer valid. Human rationale
and source/legal prose are not exported through this curated projection.

Consumers must check the returned state, exact dates and review binding when
building or approving a report. They must still establish relevant historical IOP
goals, actual delivery and professional judgements, handle missing content, bind
human approval to the exact document, and perform separate recipient/disclosure
checks. Those BC10/J11 workflows and any UI are outside this review. No new legal
research or claim of legal completeness was performed.

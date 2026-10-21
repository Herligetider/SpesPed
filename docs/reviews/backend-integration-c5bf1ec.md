# Backend integration run and scoped fixture repair

Run by `/root` on 21 October 2026. This is an integration execution record,
not an independent whole-product review or a feature-completion declaration.

## Frozen baseline

Exact source: `c5bf1ecd51deb98f843196bd62922ca68aaa73a4`, extracted through
`git archive` into `var/backend-integration-c5bf1ec`. Absolute `PYTHONPATH`
selected that archive's backend and tests over the shared editable runtime.
`import-path.log` records the actual imported application path.

With the assigned synthetic PostgreSQL URL in `SPESPED_TEST_POSTGRES_URL`:

```sh
# Working directory: var/backend-integration-c5bf1ec/backend
PYTHONPATH=/Users/lauritz/Programming/SpesPed/var/backend-integration-c5bf1ec/backend:/Users/lauritz/Programming/SpesPed/var/backend-integration-c5bf1ec/backend/tests \
  /Users/lauritz/Programming/SpesPed/backend/.venv/bin/python -m pytest tests -q
```

Completed result: **735 passed, 21 skipped, 4 failed; 90 subtests passed**,
1188.58 seconds. All four failures are the two cases below, each on SQLite and
PostgreSQL. The skips comprise 19 SQLite instances of PostgreSQL concurrency
checks and two optional real ClamAV/Tesseract checks whose prerequisites were
not enabled for this run. The PostgreSQL concurrency instances ran. This run
does not renew earlier real OCR/scanner evidence.

- The evidence missing-goal-validator scenario inherited the newly installed
  native BC05 validator. Its arbitrary UUID received 403, while the test expected
  the 503 that applies when the provider is absent.
- The governance missing-case-resolver scenario inherited the native BC12
  resolver, although its deliberately bounded fixture migrates only through
  governance. After an exact grant it queried an absent safeguarding table,
  rather than exercising the intended unavailable-provider branch.

Full output and exact collected test names are retained locally in
`var/backend-integration-c5bf1ec/full-backend.log` and `collected-tests.log`.
The four failures reproduced independently of test order in
`first-failure-repro.log`. All root-owned execution sessions completed.

## Repair and independent verification

`76f8171aed95a3942dfa993b230bf34271afdebe` changes only those two tests. Each
asserts the native adapter is installed, then explicitly removes it locally for
the unavailable-provider scenario. Their original 503, scoped-success and
revocation assertions remain intact; production code and shared fixture defaults
are unchanged.

Root's four repaired cases plus existing context integration checks passed
**14/14**. An independent reviewer repeated **14/14** at the exact repair pin
and added **four native application probes** covering real goal and protected
case acceptance, wrong-pupil rejection and revoked owning-case rights. See
[the independent review](missing-adapter-test-review.md).

Every failure in this frozen baseline is therefore accounted for by a separately
verified test-fixture repair. The entire suite was not rerun after that repair;
the combined evidence must not be reported as one green full-suite run at the
latest HEAD. Later assessment modules and source projections require their own
verification and independent review.

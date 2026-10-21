# Frozen backend integration checkpoint

Revision: `91558b2c4745d54e84b75d892a8ac79b9a064dc4`.
Run completed on 21 October 2026.

The complete backend suite finished with **1,138 passed, 26 skipped and 90 subtests
passed**, exit code 0, in 2,230.75 seconds. Pytest also reported 21,122 warnings;
warning details were suppressed in this invocation. The skip total is recorded
without treating skipped cases as successful checks.

The root used `git archive` in `var/integration-91558b2/pin` and set absolute paths
to that archive's `backend` and `backend/tests` in `PYTHONPATH`. Four actual
application/fixture import paths and source hashes were recorded before execution,
so the editable development installation did not substitute newer working files.
The Python interpreter was the repository's Python 3.12 environment. The isolated
PostgreSQL test URL was configured, enabling the actual PostgreSQL variants as well
as SQLite cases.

Command from the frozen repository:

```text
SPESPED_TEST_POSTGRES_URL=<isolated synthetic PostgreSQL URL> \
PYTHONPATH=<absolute archive/backend>:<absolute archive/backend/tests> \
<repository>/backend/.venv/bin/python -m pytest backend/tests -q --disable-warnings
```

Local evidence: `var/integration-91558b2/tests.log`, `source-proof.json` and
`import-proof.json`. Root execution session 74710 terminated successfully.

This result covers the pinned backend baseline. Later document choice extensions,
guardian/document UI changes, plan timestamp repairs and recovery metadata work
have separate verification and review records. It is not a whole-product,
browser, deployment, legal-configuration or production-model quality acceptance.

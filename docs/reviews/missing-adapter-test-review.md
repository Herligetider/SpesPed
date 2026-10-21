# Independent missing-adapter test repair review

- Reviewer: `/root/review_j09`, independent of author `/root`.
- Reviewed commit: `76f8171aed95a3942dfa993b230bf34271afdebe`.
- Date: 21 October 2026.
- Verdict: **accepted for the bounded two-test repair. No actionable finding remains.**
- Scope: only changes to `backend/tests/test_evidence.py` and `backend/tests/test_governance.py`. This review does not accept the ongoing broader backend integration run or imply feature completion.

The repair correctly distinguishes an unavailable-provider test from an application whose native adapter is installed. Each changed test first asserts that `create_app` supplied a callable native adapter, then uses its own `monkeypatch` to remove only that adapter for the existing missing-provider branch. Production code and shared fixture defaults are unchanged. Pytest restores the native attribute after each test, including after the test installs its synthetic scoped adapter.

At `test_evidence.py:467–488`, the original goal-linked evidence correction still receives 503 while the validator is explicitly absent. Installing the narrow synthetic validator then verifies the exact school, pupil and goal coordinates and permits the correction. The test no longer confuses rejection of an arbitrary UUID by the real BC05 validator with absence of a provider.

At `test_governance.py:305–328`, a pupil assignment and ordinary governance authority still fail with 403, an exact protected-case governance grant still receives 503 while the owner resolver is explicitly absent, and the narrow scoped resolver permits the intended task. Revoking that exact grant still denies task detail and removes pupil/case/period identifiers from the restricted list projection. The bounded fixture migrates through governance, so it cannot exercise the installed native safeguarding resolver against an unmigrated safeguarding table; native integration is checked separately against databases containing the owning context.

No assertion was weakened to accept a server error or a false authorization success. The 503, exact scoped success, subsequent revocation and redacted projection assertions remain in place. The earlier missing-table failure is consistent with the partial migration fixture and does not establish a production full-schema failure.

The reviewer independently authored two additional native adapter probes, each executed on SQLite and PostgreSQL:

- A fresh actual `create_app` instance, with the default `validate_goal_reference` adapter left installed, uses a live activated BC05 plan/goal and the real BC02 correction API. It accepts the exact pupil's goal reference and returns 403 when the same goal is attributed to another pupil.
- An actual application with the default `resolve_case_learner` adapter left installed creates a real protected case and governance task. Exact owning-case/governance permissions succeed. Even with an exact governance grant for an incorrect pupil, the native resolver rejects the mismatched case linkage. Revoking the owning safeguarding case-read grant also rejects a subsequent governance trigger despite its retained governance grant.

These probes verify behavior beyond merely checking that the default fields are callable, so the test repair does not conceal a regression in those native composition paths.

## Verification

Tests ran from a new frozen `git archive` extraction at `var/review-missing-adapter/frozen`, with absolute `PYTHONPATH` selecting that archive's backend and tests over the shared editable environment. `var/review-missing-adapter/pin.log` confirms that the commit changes exactly the two assigned test files, verifies their bytes plus application/assembly bytes against the commit, and records the frozen imported module paths.

Set `SPESPED_TEST_POSTGRES_URL` to the assigned synthetic test database URL:

```sh
# Working directory: /Users/lauritz/Programming/SpesPed/var/review-missing-adapter/frozen
PYTHONPATH=/Users/lauritz/Programming/SpesPed/var/review-missing-adapter/frozen/backend:/Users/lauritz/Programming/SpesPed/var/review-missing-adapter/frozen/backend/tests \
  /Users/lauritz/Programming/SpesPed/backend/.venv/bin/python -m pytest \
  backend/tests/test_evidence.py::test_goal_references_fail_closed_until_scoped_validator_is_available \
  backend/tests/test_governance.py::test_protected_case_grant_is_exact_and_revoked_scope_denies_existing_owner \
  backend/tests/test_context_integration.py -q

# Working directory: /Users/lauritz/Programming/SpesPed
PYTHONPATH=/Users/lauritz/Programming/SpesPed/var/review-missing-adapter/frozen/backend:/Users/lauritz/Programming/SpesPed/var/review-missing-adapter/frozen/backend/tests \
  backend/.venv/bin/python -m pytest var/review-missing-adapter/test_native_adapters.py -q -s
```

Results:

- Changed scenarios plus existing context integration checks: **14 passed**, 17.21 seconds. Log: `var/review-missing-adapter/focused.log`.
- Independent native composition checks: **4 passed**, 5.78 seconds. Source/log: `var/review-missing-adapter/test_native_adapters.py`, `var/review-missing-adapter/native.log`.
- The native goal probe's first setup used the helper's wrong keyword; correcting that reviewer scaffolding produced the final passing run above. No production failure was inferred from the setup error.
- The two existing warnings remain: Starlette/httpx TestClient deprecation and the explicit `ResourceRights.copy` field shadowing Pydantic's legacy method.

All PostgreSQL tests used fresh unique schemas in the assigned synthetic `spesped_test` database, with fixture teardown limited to those schemas. SQLite used temporary files. The existing integration tests use loopback model servers only. No real pupil data, external messages, demo database access, production edits, commits, pushes or subagents were used. All reviewer-owned execution sessions completed. The parent's ongoing full-suite process was not polled or modified.

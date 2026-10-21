# J12 independent review — candidate 90c93469399c0f91f3c4dce62e57fc885e799518

Verdict: changes requested for one P2 caller-transaction defect. This is a bounded review of BC11 backend communication, native application composition and the loopback HTTPS protocol. It is not acceptance of complete F21, F20, F39, user interfaces or deployed integrations.

## Finding

**[P2] Reject staged caller changes before entering the command rollback scope** — `backend/spesped/contexts/communication/service.py:77` and `:96`.

Every decorated mutation checks for pending context ORM objects inside its `try`, raises `dependency_pending`, and then runs the generic `except Exception: db.rollback()`. Consequently a command that refuses to take ownership of staged dependencies nevertheless discards all the caller's work. This is particularly material when the pending edit is a protective guardian restriction: a service caller can catch the expected 409 and continue, while the protection it had staged has silently disappeared. The read-port guard correctly preserves these edits; the mutation guard must do the same. Reject before entering the rollback scope, or otherwise distinguish failure before transaction ownership. Do not merely catch and ignore dependency_pending after rolling back.

Independent reproduction `var/review-j12-communication/test_adverse.py::test_rejected_command_preserves_callers_pending_relationship` loads the synthetic guardian relationship, stages `restrictions='Synthetic pending protective restriction'`, invokes `revoke_recipient` with a well-formed command, catches the expected staged-dependency DomainError, and asserts that the edit and dirty transaction survive. It fails on both SQLite and actual PostgreSQL: restrictions is reset to the persisted empty string. No candidate assertion or monkeypatch causes this failure. See `var/review-j12-communication/adverse-tests.log`: **2 failed in 5.32s**.

## Pin and inspection

Reviewed all 19 candidate files, AGENTS.md, complete F20/F21/F39 feature records, the strategic domain model and implementation contracts, and relevant identity/document owner services. The independent archive is `var/review-j12-communication/pin`, created using `git archive 90c93469399c0f91f3c4dce62e57fc885e799518`. All 19 SHA-256 hashes exactly match the orchestrator's `var/j12-communication/root-verified-hashes.json`. Saved evidence is `var/review-j12-communication/hash-import-proof.json` and includes seven absolute package/module/fixture paths inside this archive. The editable installation does not supply reviewed code.

All test commands used `/Users/lauritz/Programming/SpesPed/backend/.venv/bin/python3.12` and the absolute override:

```
PYTHONPATH=/Users/lauritz/Programming/SpesPed/var/review-j12-communication/pin/backend:/Users/lauritz/Programming/SpesPed/var/review-j12-communication/pin/backend/tests
SPESPED_TEST_POSTGRES_URL=postgresql+psycopg://spesped_test:synthetic-development-only@127.0.0.1:55432/spesped_test
```

## Verification

- Candidate files `test_communication.py`, `test_communication_ai.py`, `test_communication_concurrency.py`, `test_communication_transport.py`, `test_communication_migration.py`, `test_bc11_application_composition.py`: **50 passed, 1 skipped in 124.54s**. The single skip is the PostgreSQL row-lock race under the SQLite parameter; its actual PostgreSQL parameter passed. Full output: `candidate-tests.log`.
- Independent transport tests in `test_adverse.py`, selected with `-k independent_tls`: **3 passed in 1.94s**. A verified TLS peer returned a chunked body exceeding 16 KiB without a Content-Length, emitted a 256 KiB header, or stalled the TLS handshake. Each result remained unknown within the absolute bound and the subprocess was reaped. Synthetic secret absent from process arguments. Full output: `transport-adverse.log`.
- Owner regressions: `test_documents_migration.py`, BC10 `test_read_contract_preserves_staged_orm_and_transaction`, BC10 `test_prior_background_is_explicit_and_since_last_requires_exact_confirmed_recipient_purpose`, and BC03 `test_period_context_change_needs_new_review_and_read_does_not_rollback_flushed_work`: **10 passed in 17.31s** across SQLite/PostgreSQL where parametrized. Full output: `owner-regressions.log`.

The candidate tests exercised exact reviewed sections and server-rendered attachments, separate content/disclosure signatures, current guardian rights and sourced policy reviews, source/model recall, exact session-scoped portal grants and expiry/revocation, independent read receipts, semantic key conflicts, atomic audit/outbox rollback, durable unknown-before-wire state and completion-loss recovery, explicit same-key reconciliation, concurrent duplicate release/reconciliation, native accepted-history scope, real portal publication across application restart, and 20-table static PostgreSQL migration parity. The migration follows j13_report_period; empty downgrade succeeds and retained rows refuse downgrade before table removal. Transport inspection confirms private stdin pipes, no payload-bearing argv/logging, child and parent total deadline enforcement, disabled redirects/environment proxies, exact response protocol/key/digest binding and explicit empty CA trust without system fallback.

## Limits and cleanup

The initial attachment boundary is selected approved document revisions rendered as UTF-8 text. Arbitrary uploads/PDF, J21 practitioner/guardian screens, named J18 integrations, deployed workers and operator configuration remain required separate work. Passing backend tests cannot establish full-feature delivery or legal/practitioner acceptance.

Only this review document and `var/review-j12-communication/**` were written. No product files, shared tests, dependencies, commits or pushes were changed. No external transmission or real pupil data was used. Database fixtures each created UUID-named schemas and dropped only their own exact schema in teardown; test processes completed and TLS listeners/workers were closed/reaped. Shared servers on 8000/5173/18878 were untouched. Archive and logs are retained for reproduction.

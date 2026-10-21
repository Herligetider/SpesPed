# Intake transport and assignee boundary review

- Reviewed implementation: `22fe0b15c6edc36ec604048ac96019f74eb8b97e`, limited to its four-file parent diff.
- Additional documentation-only review: `86c06f20dc4c6ed89e407c49d7dddfae3fc7da67`, `backend/README.md` only.
- Reviewer: `/root/review_composition`, independent of the root implementation author.
- Review date: 2026-10-21.
- Verdict: **accepted for this bounded backend contract; no blocking findings**.

## Accepted behavior

Both original uploads and replacement revisions accept the explicit `X-Evidence-Filename-Encoding: percent` header. Decoding is one strict UTF-8 pass, with malformed percent escapes, unsupported encoding labels, decoded control characters, path separators and oversized names rejected. Omitting the encoding header preserves legacy literal percent sequences. The decoded filename participates in logical retry identity; different wire encodings of the same literal filename do not create an additional source.

ASCII-escaped metadata JSON supports supplementary Unicode within the existing typed field limits. The independent transport limit is 16 KiB. Invalid metadata/filenames fail without creating source revisions or stored objects. Authorized historical original downloads remain intact after an encoded replacement revision.

The static `GET /intake/assignees` route requires current school-wide intake authority. It returns only IDs and display names for active users with a current membership and matching school-wide grant. Its grant `EXISTS` query avoids duplicates; the unique school/user membership constraint prevents duplicate join rows. Search treats wildcard characters literally; ordering by display name and ID gives stable pagination. Assignment commands retain their separate current-authority check. Reading a choice does not grant, freeze or extend authority.

## Verification

The implementation was archived into `var/review-intake-transport/pin`. Python 3.12 tests used the shared runtime with absolute `PYTHONPATH` entries for that archive's `backend` and `backend/tests`, avoiding the working checkout's editable installation. Both SQLite and actual PostgreSQL ran; PostgreSQL fixtures created and removed unique temporary schemas in the synthetic test database.

Focused pinned command, from the archived repository, with the configured `SPESPED_TEST_POSTGRES_URL`:

```sh
PYTHONPATH=/Users/lauritz/Programming/SpesPed/var/review-intake-transport/pin/backend:/Users/lauritz/Programming/SpesPed/var/review-intake-transport/pin/backend/tests \
  /Users/lauritz/Programming/SpesPed/backend/.venv/bin/python -m pytest -q \
  backend/tests/test_intake_transport.py \
  backend/tests/test_evidence.py::test_dedup_retry_conflict_source_versions_and_injection_as_data \
  backend/tests/test_evidence.py::test_real_local_pdf_docx_eml_attachments_and_text_extraction \
  backend/tests/test_evidence.py::test_quarantine_retries_fail_closed_types_size_archives_and_missing_ocr \
  backend/tests/test_evidence.py::test_original_cross_school_denial_expired_intake_and_public_scanner_bypass_absent \
  backend/tests/test_intake_structuring.py::test_owned_tasks_resolution_reopen_scope_and_sibling_semantics \
  backend/tests/test_intake_structuring.py::test_apply_assignee_conflicting_replay_and_atomic_rollback
```

Result: **18 passed**, no skips, in 32.75 seconds. This covered the new transport tests and relevant existing extraction, revision/retry, quarantine, scope and clarification-assignment behavior.

Independent probes are retained in the ignored artifact `var/review-intake-transport/test_transport_adverse.py`. All **10 cases passed**, five scenarios on each database:

1. A 200-character supplementary-Unicode filename and metadata at every typed string maximum persist correctly; historical original bytes remain retrievable. Exactly 16,384 metadata-header characters are accepted, 16,385 are rejected, and typed limits/extra-field rejection remain enforced.
2. Encoded and legacy wire representations of the same literal percent-containing filename share retry identity. Changed filenames conflict under an existing request key. Replacement retries remain one revision and preserve original bytes.
3. Invalid UTF-8, truncated escapes, control characters, encoded/legacy path separators and unsupported encoding labels return 422 without source, storage-object or successful audit mutation.
4. Expired/future memberships, disabled accounts and revoked memberships are excluded. Grants valid through today remain eligible. Duplicate grants and equal display names preserve exact totals and stable ID tie-breaking; literal percent/underscore searches, bounds, foreign-school denial and metadata-only read auditing behave as intended.
5. Revoking a listed colleague's grant removes the choice and denies a subsequent clarification assignment, creating no task. A warmed service session also rechecks a caller whose intake grant was revoked by another committed session.

Six transport cases passed on the first independent run. Four authorization cases initially stopped in the reviewer's fixture because the membership insert had not been flushed before a dependent grant insert; correcting that fixture ordering produced four passes on the targeted rerun. No application code was changed for the review. The only test warning was the existing FastAPI/Starlette TestClient deprecation.

These transport fixtures deliberately use the existing synthetic scanner; this review does not claim a new verification of actual malware scanning or production OCR. No external model, mailbox or message service was used.

## Documentation follow-up

The README-only diff at `86c06f20dc4c6ed89e407c49d7dddfae3fc7da67` accurately reflects the accepted `30fe563` application composition and this transport contract: protected-case routes/adapters and the goal validator are present, their separate scope checks remain required, `b1_integrate_contexts` is the initial migration merge rather than the current head, and filename encoding/legacy behavior is explicit. It retains the limits on feature completeness and production readiness. No behavioral test rerun was needed for this documentation-only change.

## Limits

Acceptance covers these backend headers, filename validation and assignee choices, plus the stated README corrections. It does not accept the browser intake UI, the complete intake feature, all earlier context behavior, later code changes or deployment proxy/header configuration. Browser behavior will receive its separate real-browser review. Full-feature and production acceptance remain separate work.

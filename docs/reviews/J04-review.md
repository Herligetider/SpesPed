# J04 independent backend review

Review date: 21 October 2026. Reviewer: `/root/review_j04`, separate from the J04 implementer.

**Verdict: changes required.** The supplied verification passes, including actual local malware scanning and OCR, but three independently reproduced defects remain. The first prevents correcting an accidental disclosure of another pupil's source text.

## Revision and scope

Pinned implementation revision: `2efa896941aa171d11d28ce7635b7342c64b28be`.

Reviewed `backend/spesped/contexts/evidence/**`, `backend/tests/test_evidence.py`, `backend/migrations/versions/j04_evidence.py`, and the locked Pillow addition in `backend/pyproject.toml` / `backend/uv.lock`. At review start the shared checkout HEAD was `9f8ca976dbf03c261e3e33e2f0ebc04a7a762f2c`; `git diff --quiet 2efa896941aa171d11d28ce7635b7342c64b28be -- backend/spesped/contexts/evidence backend/tests/test_evidence.py backend/migrations/versions/j04_evidence.py backend/pyproject.toml backend/uv.lock` returned 0, also checked after testing. Thus the assigned implementation files tested were the pinned versions. Unrelated concurrent work was left untouched.

Read `AGENTS.md`, F03/F04/F05 in `docs/features.json`, including `workspace`, `stateBehavior`, `automationBoundary`, and `recovery`, and `docs/09-domain-implementation.en.md`. This review covers the J04 backend boundary; J07 UI and future consumer contexts are outside its implementation scope.

## Findings

### J04-R1 — P1: corrections cannot retract an accidentally overbroad source excerpt

Locations: `backend/spesped/contexts/evidence/service.py:347–352`; `backend/spesped/contexts/evidence/schemas.py:100–102`.

`CorrectEvidence` accepts corrected content and attribution but no replacement source span or revocation command. `correct()` revokes the old link, then creates a new current link containing exactly the old excerpt and span. Consequently correcting the evidence content cannot remove mistakenly released sibling information. There is also no other exposed withdrawal/deletion command that can stop the erroneous current excerpt being available to that pupil team.

Reproduced through HTTP on PostgreSQL and SQLite:

1. Import `Synthetic pupil A reads well.\nSynthetic sibling B private concern.`
2. Review A's paragraph and confirm it for A with an accidentally overbroad excerpt covering the whole source page.
3. Correct the item to `Synthetic pupil A reads well.` with reason `Remove accidentally included sibling information`.
4. Log in as `teacher`, who has access to A only, and request the correction response's new source link.
5. The request returns 200 and the excerpt still contains `Synthetic sibling B private concern.`. The old link is revoked, but the new link republishes its entire contents.

The correction API must support an authorized, validated replacement excerpt or explicit withdrawal of the mistaken release, with appropriate old-link revocation and derivative effects. Reassignment likewise needs an explicit review of what excerpt will be exposed to the new pupil team. This is required for F03's controlled multi-pupil excerpts and F05's recovery from incorrect pupil attribution/access; changing the displayed summary alone does not correct the underlying release.

Supplemental repro: `var/review-j04/test_review.py::test_correction_cannot_remove_overbroad_excerpt` (fails for both database fixtures).

### J04-R2 — P2: intake completion does not reflect outstanding confirmation work

Locations: `backend/spesped/contexts/evidence/service.py:228–246`, `:290–293`.

The only completion transition is in `confirm()`, and its query checks solely whether any proposal has `outcome='pending'`. Reviewed but unconfirmed accepted/edited fields therefore do not prevent `done`. Conversely, rejecting every proposal never updates the source status, so fully rejected intake remains `needs_review` indefinitely.

Both cases reproduced through HTTP on PostgreSQL and SQLite:

- Import two paragraphs, accept both fields, then confirm only the first. `GET /intake/{id}` reports `state='done'`, although the second accepted field is not confirmed or assigned to any pupil.
- Import one paragraph and reject its sole proposal. The source remains `state='needs_review'`, with no remaining actionable pending field and no completion command.

Compute intake status consistently after review, confirmation and new proposal creation, distinguishing reviewed fields awaiting pupil confirmation from rejected/confirmed fields. This is material to F03/F04's completed versus partially reviewed states and avoids hiding unfinished release decisions in the processed inbox.

Supplemental repros: `test_unconfirmed_accepted_field_keeps_intake_unfinished` and `test_reject_all_finishes_intake` (each fails for both database fixtures).

### J04-R3 — P2: valid saved MIME emails with non-UTF-8 8-bit bodies are rejected

Location: `backend/spesped/contexts/evidence/processing.py:148–155`.

`inspect_type()` applies whole-file UTF-8 decoding to `.eml` files. A valid MIME email can contain an 8-bit body using its declared charset. The downstream email extractor already decodes individual text parts using that charset, but this branch rejects the file before scanning or extraction.

Reproduced a saved email with ordinary From/To/Subject headers, `Content-Type: text/plain; charset=iso-8859-1`, `Content-Transfer-Encoding: 8bit`, and the synthetic body `Syntetisk elev trenger støtte.` encoded accordingly. Upload returns HTTP 422 with `file_signature` on both databases. The original is not retained as an intake item. This is a practical failure for F03's saved-email import path, particularly Norwegian text from older mail clients.

Validate the MIME envelope without requiring the entire serialized message to be UTF-8; retain scanner enforcement and bounded, charset-aware MIME parsing.

Supplemental repro: `test_valid_8bit_saved_email` (fails for both database fixtures).

## Commands and results

All commands ran at `/Users/lauritz/Programming/SpesPed` using synthetic data only. No demo database, external service, external message, or AI extraction was used. The test fixture creates/drops unique PostgreSQL schemas in `spesped_test`.

The supplied suite was independently run with the actual configured local adapters:

```sh
SPESPED_TEST_POSTGRES_URL='postgresql+psycopg://spesped_test:synthetic-development-only@127.0.0.1:55432/spesped_test' \
SPESPED_TEST_CLAMD_SOCKET='/Users/lauritz/Programming/SpesPed/var/clamav/clamd.sock' \
SPESPED_TEST_TESSERACT='/opt/homebrew/bin/tesseract' \
SPESPED_TEST_PDFTOPPM='/Users/lauritz/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/override/pdftoppm' \
SPESPED_TEST_TESSDATA='/Users/lauritz/Programming/SpesPed/var/tessdata' \
backend/.venv/bin/pytest backend/tests/test_evidence.py -q
```

Result: **29 passed, 1 skipped in 29.64s**. The skip is the SQLite counterpart of the PostgreSQL contention test. Actual clamd clean/EICAR classification and actual Tesseract extraction from a Norwegian PNG and scanned PDF both ran successfully on both database fixtures. There is one unrelated Starlette TestClient deprecation warning.

Supplemental adverse-path HTTP tests:

```sh
SPESPED_TEST_POSTGRES_URL='postgresql+psycopg://spesped_test:synthetic-development-only@127.0.0.1:55432/spesped_test' \
backend/.venv/bin/pytest var/review-j04/test_review.py -q
```

At this run the file contained the four adverse tests above. Result: **8 failed in 5.82s**, comprising each reproduced adverse case on PostgreSQL and SQLite. These assertions describe the required corrected behavior; failures are product findings, not infrastructure failures.

After adding a supplemental actual PostgreSQL correction-versus-derivative registration contention test:

```sh
SPESPED_TEST_POSTGRES_URL='postgresql+psycopg://spesped_test:synthetic-development-only@127.0.0.1:55432/spesped_test' \
backend/.venv/bin/pytest var/review-j04/test_review.py -q -k race
```

Result: **1 passed, 1 skipped, 8 deselected in 1.52s**. The SQLite counterpart was skipped deliberately. Concurrent registration either precedes the correction and is marked stale, or is rejected after correction; no draft remains supported by a stale evidence revision in this exercised interleaving.

The supplied suite also exercised real parser extraction for text/PDF/DOCX/EML with an attachment; unsafe signatures, archive expansion limits, upload size, missing OCR/scanner recovery, quarantine, source digest integrity, source revisions, exact literal excerpts, typed hours, rejected/stale review, occurrence/recording dates, search escaping, dispute history, cross-school/expired/technical-administrator access denial, immutable source versions, reassignment revocation, derivative impacts, audit/outbox rollback, source identity contention and migration downgrade/re-upgrade. This evidence supports those exercised paths, not blanket completion of F03–F05.

## Boundaries and limitations

- Migration verification explicitly used `j04_evidence`, descending from `a9e1f00151e4`, in isolated schemas. It did not invoke the shared multi-branch `head`; final migration composition remains the orchestrator's work.
- Goal references fail closed with HTTP 503 until a scoped `evidence_goal_validator` is provided. The suite checked this and a local test validator. Real J05 goal scope integration remains unfinished.
- Router/storage/scanner/OCR deployment wiring and configuration remain an assembly/deployment responsibility. Tests use the real API in a test application with explicit local ports. No production deployment or pupil data is approved by these results.
- J07 must supply the inbox, split-excerpt selection, side-by-side source review, open clarification handling, timeline and correction-impact user flows. They have not been visually/browser reviewed here.
- Derivative registration and correction-impact rows/outbox metadata are available, and local stale/shared-review states were exercised. Real document/session/search consumers must register exact dependencies, enforce target scope, consume/reconcile correction events and prevent stale use. This review does not establish that those future consumers or already shared external documents are updated.
- Extraction is bounded local literal content proposal generation, with manually typed field proposals; it does not infer pupil identity, dates, goals or measures automatically. Imported text does not execute instructions or send anything. Detailed document-field automation and a full clarification-owner workflow are not established by this review.
- Parser limits were inspected and exercised for the supplied size/archive cases. This is not a broad parser fuzzing campaign or a deployment-scale load test.

Implementation files were not edited. Supplemental tests remain only in ignored `var/review-j04/`. The reviewer is available for independent verification of the fixes.

## Independent fix recheck — 21 October 2026

**Candidate:** `62446cee4520cb58920a45524c5f4de34fd49c63`.

**Recheck verdict: R1, R2 and R3 closed for this backend candidate.** No additional blocker was observed in the bounded fix scope. This verdict supersedes the initial changes-required verdict for those three findings; the initial evidence and findings above remain preserved. It does not declare all of F03–F05 complete.

The reviewer inspected the candidate diff independently. It changes evidence processing, router, schemas, service and owned tests only. At recheck start HEAD was exactly the candidate. HEAD advanced to `c1720fc2a9b0a499517fd91b871a01bfeebd8e61` during testing; the assigned evidence implementation and test paths still matched the candidate when checked after testing. Concurrent root assembly/configuration/platform/migration work was left untouched and is outside this recheck. The tests continued to migrate isolated schemas to `j04_evidence`, not a shared composed head.

### R1 verification

The correction schema now accepts a complete validated replacement excerpt span. An ordinary correction without an explicit replacement narrows incidental surrounding text to the originally reviewed field, without widening a previously corrected span. Explicit narrowing inside already released text is available to the current pupil team. Widening or moving outside the released span requires the independent intake authority. Reassignment requires that authority, write scope for both pupils, and an explicitly selected source span.

The original unchanged overbroad-sibling repro now passes on PostgreSQL and SQLite. Additional reviewer-authored HTTP checks in `var/review-j04/test_recheck.py` verified:

- An A-only teacher can explicitly narrow A's released excerpt. The old link returns 403 and the new link contains the exact selected substring.
- Both registered derivative types become `stale` / `shared_review_required`; two correction-impact rows are retained.
- Attempted re-expansion by the teacher returns 403 and leaves the current link usable.
- A reviewer with current write access to **both** pupils but a revoked intake grant receives 403 when attempting reassignment. Restoring intake authority permits the command only with a complete explicit replacement span.
- Missing or partial reassignment spans return 422, preserving the existing revision/link. Valid reassignment revokes the prior link and changes which team can read the new exact excerpt.
- The old A team loses item/timeline/source access; the B team receives B's selected text only. Three immutable evidence revisions and two revoked historical links remain in the database. Historical A revisions are not exposed to B through the history endpoint.

The original PostgreSQL correction-versus-derivative contention probe also passes in the combined run. Real downstream derivative consumers remain an integration boundary, as described above.

### R2 verification

`review_progress()` now distinguishes pending, reviewed-unconfirmed, confirmed and rejected fields. `update_intake_completion()` runs after proposal creation, review and confirmation. Reviewed-but-unconfirmed fields keep the source in `awaiting_confirmation`; rejecting all fields produces `done`; adding a new pending field reopens `needs_review`.

Both original unchanged completion repros pass on both databases. The owned regression additionally exercised partial confirmation counts, final completion, reopening a completed source with a manual proposal and completion after rejecting that proposal.

### R3 verification

`.eml` type inspection now validates the bounded header envelope rather than decoding the entire serialized MIME message as UTF-8. Decoding remains part-specific after scanning. The original unchanged ISO-8859-1 / 8-bit repro passes on both databases. The owned regression verifies exact original-byte preservation, correct Norwegian text decoding, and scanner-unavailable quarantine.

The additional reviewer probe used an actual `ClamdScanner` with a Windows-1252 8-bit message containing both `ø` and an en dash. Both databases preserved the original raw bytes exactly and returned `støtte – avtalt.` in the extracted page. A NUL-bearing body was quarantined with rejected extraction, and an unavailable actual scanner socket produced an unavailable scan/quarantined source. Actual standalone EICAR classification and Norwegian PNG/scanned-PDF Tesseract OCR also ran successfully in the combined owned suite.

### Recheck commands and results

Run from `/Users/lauritz/Programming/SpesPed`:

```sh
SPESPED_TEST_POSTGRES_URL='postgresql+psycopg://spesped_test:synthetic-development-only@127.0.0.1:55432/spesped_test' \
SPESPED_TEST_CLAMD_SOCKET='/Users/lauritz/Programming/SpesPed/var/clamav/clamd.sock' \
SPESPED_TEST_TESSERACT='/opt/homebrew/bin/tesseract' \
SPESPED_TEST_PDFTOPPM='/Users/lauritz/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/override/pdftoppm' \
SPESPED_TEST_TESSDATA='/Users/lauritz/Programming/SpesPed/var/tessdata' \
backend/.venv/bin/pytest backend/tests/test_evidence.py var/review-j04/test_review.py -q
```

Result: **44 passed, 2 skipped in 48.06s**. The skips are the SQLite counterparts of actual PostgreSQL contention scenarios. All four originally failing adverse cases now pass unchanged.

```sh
SPESPED_TEST_POSTGRES_URL='postgresql+psycopg://spesped_test:synthetic-development-only@127.0.0.1:55432/spesped_test' \
SPESPED_TEST_CLAMD_SOCKET='/Users/lauritz/Programming/SpesPed/var/clamav/clamd.sock' \
backend/.venv/bin/pytest var/review-j04/test_recheck.py -q
```

Result: **4 passed in 4.52s**. The same Starlette TestClient deprecation warning remains. An earlier draft of the supplementary MIME probe incorrectly expected a standalone EICAR test signature appended after unrelated body text to be classified as infected; that assertion failed in both database variants and was removed as an invalid scanner-fixture assumption, not reported as a product defect. The final probe tests real scanner unavailability instead; the owned suite separately exercises the standard exact EICAR fixture.

### Remaining scope limits

The repaired paths provide controlled excerpt correction, explicit review/confirmation progress and charset-aware saved-email import. They do not establish the broader F04 semantics: extraction remains deterministic literal content proposals plus manually entered typed proposals, rather than inferred learner/date/goal/measure fields. A durable clarification workflow with a specific responsible owner, clarification note and resolution lifecycle is still not implemented by these fixes. UI confirmation/recovery behavior remains J07 work, and actual J05 goal validation plus downstream document/session/search consumers require their own integration verification. Root composition and its separate integration-test claims were not independently accepted by this recheck.

No implementation or shared assembly files were edited by the reviewer. Only this report was appended; additional reviewer tests remain under ignored `var/review-j04/`.

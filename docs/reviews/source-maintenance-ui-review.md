# Independent source-maintenance UI review

Candidate: `0b726b8ebc4231d29118535b114bb0acd1023251`  
Reviewed: 2026-10-21  
Reviewer: independent agent; implementation author was the root agent.

**Verdict: accepted within the bounded source-replacement and source-reinspection scope. No actionable findings were identified.** This is not acceptance of all F03/F04, all J07, production readiness, or the complete intake workflow. AI intake, timeline work, clarification reassignment and other remaining requirements are outside this change.

## Scope and inspected boundaries

Reviewed all seven changed files: `SourceMaintenance.tsx`, its tests, intake workspace integration and fixture, the `IntakeSource` type, the additive native `source_view` identity fields, and `test_intake_source_maintenance.py`.

The new UI consumes the existing native revision and inspection commands. Replacement captures the actual File, source/version, metadata and request key for retry. A real conflict retains the file and fields but requires a refreshed source and explicit adoption of its revision before a new command. A known mutation success remains separate from a failed subsequent source read. Current source authority is distinct from proposal-list availability.

Inspection uses expected-version concurrency, not a receipt-based idempotency contract. The UI retries the original expected version after an uncertain response. A changed fresh record can be explicitly adopted without claiming that it proves which request produced the change; an unchanged record remains uncertain. A registered processing attempt with unavailable extraction is not presented as a ready document.

The added `external_scope` and `external_id` come from the persisted source. Every `source_view` call remains behind the existing school-wide intake/source authorization boundary. No new raw-byte, storage-key, email-directory or secret projection was introduced. Native commands still validate source identity and current authorization. The parent workspace keys identity/client/school scope; the source component is keyed by source ID and ignores completed operations after unmounting.

## Meaningful verification

The exact candidate was archived to `var/review-source-maintenance/pin`. `exact-files.json` confirms all seven changed files match their Git blobs. Installed web dependencies were linked into the archive, but application sources were frozen. The archive's production bundle was built independently and served by its actual FastAPI application. Python used these absolute import paths:

```text
/Users/lauritz/Programming/SpesPed/var/review-source-maintenance/pin/backend
/Users/lauritz/Programming/SpesPed/var/review-source-maintenance/pin/backend/tests
```

`import-origins.txt` records the archived application. Browser checks used actual Chromium with `Europe/Oslo`, native authentication/CSRF, protected local original storage and actual PostgreSQL in reviewer-owned unique schemas. The scanner was the importable synthetic test adapter; normal bounded parsing and the native endpoints remained in use. All source content and identities were synthetic.

| Completed verification | Result | Evidence under `var/review-source-maintenance/` |
| --- | --- | --- |
| Archived `npm test -- --reporter=verbose` | 134 passed, 10 files, 5.63 s | `web-tests.log` |
| Archived `npm run build` | TypeScript and production build passed, 56 modules | `build.log` |
| `python -m pytest` for archived `test_intake_source_maintenance.py` and `test_intake_transport.py`, with absolute imports and actual PostgreSQL test URL | 10 passed across SQLite/PostgreSQL, 19.97 s | `api-tests.log` |
| `node var/review-source-maintenance/final/author-replay.mjs` | Six workflows/checks passed; no page exceptions | `final/author-replay.log`, `final/browser-evidence.json` |
| `node var/review-source-maintenance/final/independent.mjs` | Seven independent checks passed; no findings or page exceptions | `final/independent.log`, `final/independent-evidence.json` |

The author-scenario replay ran against the reviewer's independently archived application and fresh database. It verified Unicode replacement, stable source identity, preserved old original bytes, exact document timestamps, a real committed reply lost before reaching the UI, identical retry bytes/metadata/key and a single resulting revision, concurrent replacement with explicit new-base adoption, usable status-read recovery after a recorded success, and honest reconciliation of a committed inspection whose retry receives a version conflict. The 390px layout had no horizontal overflow; `final/maintenance-mobile.png` was visually inspected. This is visual/browser checking, not timed practitioner usability acceptance.

The independently authored final probe verified:

1. An imported repeated-hour timestamp retains its selected second occurrence and `.000123` precision through real Chromium and a native replacement. Unicode and a literal `%20` filename retain their identity, as do the persisted source identity fields.
2. A nonexistent Oslo local time shows an actionable error without sending a mutation. Explicitly choosing the first repeated-hour occurrence stores that different intended instant.
3. Failed model-proposal and manual-fallback reads do not incorrectly revoke a separately successful current-source authorization read or prevent source maintenance.
4. A real committed replacement reply held across navigation to another source cannot refresh that source's panel or clear its newly selected file and typed sender.
5. After a pre-dispatch network loss, revoking the actual synthetic intake grant causes the source read to return 403 and disables command retry. Status-read retry remains usable. Restoring the grant and observing unchanged state does not falsely resolve the unknown outcome; retry sends the identical file bytes, metadata/request key and expected version.
6. An inspection aborted before dispatch remains uncertain after an unchanged fresh status read. Retrying preserves the original expected version. The native processor records a new attempt for a supported text original with no extractable content, preserves its original revision/digest, and the UI correctly says it is still not ready.
7. A real inspection reply held across a school switch cannot place the old source or success message in the new school, or clear its draft. Native lookup of the old source under the new school is denied.

The existing component suite also covers preserving a newer locally selected file/typed field when an older operation finishes. That test changes component state while the request is pending; it is not presented as a physical-browser typing scenario through disabled controls.

## Harness corrections, cleanup and limits

Early independent attempts corrected reviewer-harness issues: the fold selector was addressed by its accessible combobox name, an unsupported `.bin` fixture was correctly rejected and replaced with a supported text file containing no extractable text, and the selected school was explicitly restored after a page reload. These were not application repairs or processing bypasses. Initial evidence and logs are preserved. The final directory used a new unique schema and completed both replay and independent script without interruption.

All test/browser processes were awaited. Only reviewer listeners 18912/18913 (PIDs 73268/75249) were stopped. Signal termination left their temporary schemas, so the reviewer removed only the exact recorded namespaces:

- `review_source_maintenance_ac711c225045456caaca161b94a92d8b`
- `review_source_maintenance_bb480bca37db4368b70e488604247bc8`

`cleanup.json` verifies both listeners stopped and both schemas absent. Ports 8000, 5173, 18878 and other agents' listeners were untouched. The synthetic grant used for the revocation probe was restored before cleanup. Only this new report and ignored reviewer artifacts were written; no production edits, commits, pushes or subagents.

Acceptance is limited to these source-maintenance contracts and UI paths. It does not establish all document formats, production scanning/OCR availability, full localization, complete accessibility, real-user usability, legal compliance or the remaining intake features. Legal sources were not re-researched.

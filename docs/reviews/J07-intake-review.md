# J07 intake UI independent review

Reviewed candidate: `53e79b98eb02d6f9e7d8e920ee13f21a4fe55bb8` (2026-10-21).

Decision: **changes required**. The intake subset supports a real persisted normal path, but the findings below prevent accepting it. This review does not accept all J07 or F03–F05.

## Scope and independence

Reviewed the seven changed `web/src` files against the candidate's actual evidence schemas/routes/services, existing shell authentication/race handling, F03–F05 in `docs/features.json`, and `docs/08-first-workflow-review.no.md`. Used a pinned `git archive` at `var/review-j07-intake`; backend imports used that archive's absolute `backend` and, for fixture reuse, `backend/tests` paths. Shared uncommitted gateway, safeguarding and J06 teaching changes were excluded. No production files were changed, committed or pushed by this reviewer. The only tracked review output is this file.

## Findings

### J07-R1 · P1 · Reset all intake content when the selected school changes

Locations: `web/src/App.tsx:202` (unkeyed `IntakeWorkspace`), `web/src/IntakeWorkspace.tsx:40` (school effect), and state at lines 14–28.

Open a school A source, enter a manual field, then select school B in the existing sidebar. The same component remains mounted; its school effect reloads only the inbox and learners. The source header, original blob, extracted text, proposal prose, clarification content and manual edit remain visible under the school B header. Subsequent actions combine the new school ID with the retained A source/field identifiers. This is a wrong-scope display and transaction context even when both schools were initially authorized; it does not establish a backend authorization bypass.

Reproduced independently in jsdom and real Chromium against PostgreSQL. `browser-evidence.json` records `cross_school_render`; `cross-school.png` shows “SYNTHETIC SCHOOL B” above A's source, confirmed field and clarification. The manual value remained `SYNTHETIC A EDIT`.

Reset or remount the entire workspace on school/auth scope changes, revoke its blobs, clear all associated form/prose state, and invalidate requests started in the prior scope.

### J07-R2 · P1 · Bind asynchronous source/page results and drafts to their source

Locations: `web/src/IntakeWorkspace.tsx:31–40`, with back navigation at line 55.

`openSource`, `loadPage`, inbox and learner loading have no cancellation or generation check. Start opening A, return to the inbox, open B, then resolve A's delayed source request: A replaces the already loaded B. A delayed page 1 response also rolls a completed page 2 selection back to page 1. Independent adverse tests reproduce both. Unlike the existing learner/profile shell, these responses are applied without checking current scope/selection.

Separately, enter a manual field value on A, return, and open B: A's value is retained while the source, page and span are reset to B. A normal save can therefore create A's interpretation against B's source. Clarification owner/detail and other source-local state are likewise not reset at navigation. The manual carryover is independently reproduced.

Give each navigation/page load a generation bound to school, source and revision; ignore superseded completions, including errors. Store any intentionally retained drafts under that identity, and make restore/discard explicit when changing sources.

### J07-R3 · P1 · Show the reviewed value that confirmation will actually persist

Location: `web/src/IntakeWorkspace.tsx:61`, `.proposal-value`.

The field always renders `field.proposed_value`. After “Lagre retting”, the edit control disappears and the card is labelled “Rettet”, but the persisted `reviewed_value` is never shown. Confirmation uses that hidden reviewed value through the backend. The same incorrect display persists after confirmation and browser reload.

An independent fixture reproduces OCR `80`, reviewed `30`, with only `80` rendered next to the confirmation form. The real browser flow separately saved `SYNTHETIC browser corrected note: 30 hours reading support.`, while both the pre-confirmation and reloaded confirmed cards displayed the original note. A real HTTP timeline response proved the corrected value was stored (`edited_render`, `real_confirmation`, `reload_persistence` in `browser-evidence.json`). This defeats exact-content human review.

Render the reviewed value as the current value for edited/accepted/confirmed fields. If the original proposal is useful, label it separately. Show the actual final interpretation and selected source excerpt before confirmation.

### J07-R4 · P1 · Load independent manual proposals after model recall

Locations: `web/src/api.ts:87–88`; `web/src/IntakeWorkspace.tsx:35–36,62` and `ManualRecovery` at lines 74–78.

After a model release/policy is recalled, the unfiltered proposal endpoint fails closed if any model-owned proposal is present. Manual recovery succeeds and creates an independent pending manual proposal, but `onDone` calls `openSource`, which requests the same unfiltered list. It still fails. The recovered field never gets a “Godta”/edit/reject/confirm control, despite the notice “Manuelt felt er lagret og kan vurderes uavhengig.” The ordinary manual-field path has the same list obstruction while recalled model rows exist.

Verified independently twice: a UI reproduction and a new API test running on both SQLite and PostgreSQL. After successful recovery, `GET .../proposals?revision=1&limit=100` remained 503, whereas adding `origin=manual` returned 200 and included the recovered proposal. The actual backend already supports that filter; the UI never requests it. `recall-test.log`: 2 passed.

When model results are unavailable, explicitly load and render independent manual proposals while retaining a separate recall message. Verify create → review → confirm → reload through the UI while the model remains recalled.

### J07-R5 · P1 · Reuse a note's identity after an ambiguous save result

Locations: `web/src/IntakeWorkspace.tsx:43–44`.

Every note submission generates both a fresh request key and fresh external source ID. A retry after the server commits but the response is lost therefore creates a second durable source instead of replaying the first command.

The real browser test let `route.fetch()` complete a real 201 transaction, then aborted delivery of that response. The UI showed its network error and retained the note. Clicking “Lagre notat” again produced a second 201 with a different source ID. The inbox total increased by two; both IDs and received times are recorded in `ambiguous_retry_duplicates` in `browser-evidence.json`. This violates the specified uncertain-save recovery workflow. Uploads have a user-entered external ID, but notes have no stable identity across retries.

Keep the exact command identity and submitted payload until the outcome is known. Reuse them for retries; allocate a new identity only for an intentional new note or revised command. Make an unknown save outcome distinct from a confirmed failure.

### J07-R6 · P2 · Keep the stale-version conflict visible and the user's edit recoverable

Locations: `web/src/IntakeWorkspace.tsx:42` and `openSource` at line 31.

On a 409, `perform` first sets the error notice and then calls `openSource`, which immediately clears it. If another tab has already reviewed the field, the pending edit control disappears on refresh. The user's replacement remains only in inaccessible component state and there is no conflict explanation or merge/recovery action.

Reproduced over real HTTP: type `SYNTHETIC UNSAVED HUMAN EDIT`, accept the old value through a competing request, then click the original tab's “Lagre retting”. The server correctly returned 409. After refresh, there were zero status notices and no edit input or visible replacement; the card showed the competitor's accepted original. Recorded in `followup-browser-evidence.json` (`stale_conflict`) and `stale-conflict.png`.

Preserve the conflict notice across refresh and present both the latest reviewed value and the retained replacement with a deliberate resolution path. Do not represent the refresh as successful completion of the attempted edit.

### J07-R7 · P2 · Encode Unicode filenames and metadata before putting them in HTTP headers

Locations: `web/src/api.ts:99–103`, including the newly exposed upload path.

The upload passes `file.name` and `JSON.stringify(metadata)` directly to `new Headers`. Browser header values are ByteStrings; characters above U+00FF cannot be represented this way. Selecting a normal local filename such as `synthetic–review.txt` (en dash) fails before any HTTP request and shows only the generic error. The same problem affects non-Latin metadata names/text.

Reproduced in real Chromium with the actual upload form: the inbox total did not change and the visible result was “Noe gikk galt. Prøv igjen, eller kontakt systemansvarlig.” A control upload with `møte.txt` and `Foresatt Ødegård` succeeded, so this finding specifically concerns characters beyond the single-byte range. See `unicode_upload_error`, `norwegian_upload` and `upload-unicode.png`.

Use a defined encoding that the backend decodes, or a body/multipart metadata contract that supports Unicode. Coordinate any transport-contract change. Surface actionable validation errors instead of a generic failure.

### J07-R8 · P2 · Use the backend's character-offset convention for default spans

Location: `web/src/IntakeWorkspace.tsx:39`, `data.text.length`.

Loading a page sets the manual span end to JavaScript's UTF-16 code-unit length. The Python backend validates/slices Unicode character offsets. A source containing a supplementary character therefore starts with an invalid, automatically supplied manual range.

Real browser/HTTP reproduction: source `SYNTHETIC 😀 source` has 18 Unicode characters but the default “Til tegn” was 19. Select a different field type and enter a value without changing that automatic range: save returns 422 `source_span` / “Select an exact span within a source page.” See `surrogate_default` and `surrogate_submit` in `followup-browser-evidence.json`.

Use one shared offset definition and calculate the default accordingly. A source-text selection control should translate selections to that convention and visibly preview the resulting excerpt.

### J07-R9 · P2 · Do not silently substitute the current UTC clock for an occurrence time

Location: `web/src/IntakeWorkspace.tsx:61` (attribution defaults), submitted at line 47.

Selecting a learner automatically fills `Hendelsestidspunkt` using `new Date().toISOString().slice(0,16)`. That UTC wall time is displayed in a `datetime-local` input and later parsed as local time. In the Europe/Oslo browser at approximately 15:20 local, choosing the learner populated `2026-10-21T13:20`; submitting it unchanged would record approximately 11:20 UTC. In addition, the occurrence is automatically replaced with today's date even when the source concerns an earlier event. The intake form always sends `original_at:null` and does not expose an original document date.

The actual default is recorded in `browser-evidence.json` as `default_occurrence`. The normal-path test deliberately replaced it with 15 September, and the HTTP response correctly preserved that chosen occurrence separately from October's recording time. The enum/time schema itself accepts the explicit form values.

Leave unknown occurrence time unfilled until the person establishes it, or offer a clearly labelled source-derived/local-time suggestion requiring review. Convert between local and UTC without discarding the offset.

## Human workflow and remaining product scope

The real desktop browser could create a note, review it, confirm a learner excerpt, create/resolve/reopen a clarification and reopen persisted state after reload. The form's current claim types, certainty values and attribution command match the real backend contract. Confirmation persisted the selected September occurrence independently of the October recording time. File upload with a Latin-1 Norwegian filename and sender worked using a synthetic clean scanner. These are verified capabilities of this subset.

The practical review workload remains substantial: source spans and controlled excerpts require manually entering character offsets in an unnumbered, unhighlighted text block; “Vis kildeutsnitt” loads a whole page without highlighting the field's span. Assigning a clarification requires an opaque UUID copied from a “school user overview” that this app shell does not provide. I completed that path using test fixture IDs, which an ordinary staff user would not possess from these screens. These gaps should be resolved before claiming the intended time-saving first workflow is usable. The Unicode offset error above is one concrete failure of the numeric-span approach.

Lists are fixed to their first 100 inbox sources, learners, proposals, recovery candidates and clarifications, with no load-more/page/search controls. `total` is only displayed for the inbox; it is not used to reach subsequent records. This is a source-inspection finding, not a performed 101-record browser test. Reaching older sources and all authorized learners needs explicit pagination/search before a whole-school completeness claim.

The candidate does **not** expose AI job creation/application, a learner evidence timeline, source/correction-history screens, correction commands, derivative impact review, revision replacement/reprocessing, field conflict filters or clarification reassignment. API helper methods alone do not implement these screens. The first workflow's teaching, assistant and post-session steps are outside this candidate. No F03–F05 or whole-J07 completion is established.

## Independent evidence and commands

All artifacts below are ignored under `var/review-j07-intake/`, except this report.

- `git archive 53e79b9 | tar -x -C var/review-j07-intake`: pinned candidate; node_modules reused via a symlink to the repository's installed locked dependencies.
- In the pinned `web`: `npm test -- --reporter=verbose` → **26 passed**: original 20 plus six independent adverse reproductions in `src/reviewer.adverse.test.tsx`. Those six assert the observed incorrect behaviors; their passing is evidence of reproduction, not acceptance. Full results: `adverse.log`.
- In the pinned `web`: `npm run build` → TypeScript and Vite build passed (`build.log`).
- `PYTHONPATH=<absolute archive>/backend:<absolute archive>/backend/tests SPESPED_TEST_POSTGRES_URL=<synthetic PostgreSQL DSN> <repo>/backend/.venv/bin/python -m pytest reviewer_recall_test.py -q` → **2 passed**, one per SQLite/PostgreSQL backend; reused the pinned synthetic fixture and local protocol server, adding independent post-recovery list assertions (`recall-test.log`). No external model/service was contacted.
- `PYTHONPATH=<absolute archive>/backend <repo>/backend/.venv/bin/python reviewer_server.py`: isolated actual FastAPI HTTP server at `127.0.0.1:18847`, production-built candidate web, uniquely named synthetic PostgreSQL schema, private original storage and synthetic scanner.
- `node reviewer_browser.mjs` → completed all normal-path/persistence, wrong-school, response-loss retry and Unicode upload assertions (`browser-evidence.json`, `browser.log`, screenshots).
- `node reviewer_followup_browser.mjs` → completed real stale-review 409 and supplementary-character span assertions (`followup-browser-evidence.json`, `followup-browser.log`, screenshot).
- Browser: bundled Playwright core with installed Chromium **156.0.8078.4**, headless, Europe/Oslo timezone; the main workflow used a 1440×1100 viewport.

The review server was stopped and its synthetic schemas removed (`cleanup.log`). The initial ad-hoc server fixture seeded at module import; Python extraction subprocess imports consequently created additional isolated synthetic schemas. That fixture was guarded against subprocess imports and all its schemas were cleaned. This was a review-harness issue, not a production finding. Existing services on 8000/5173 were left alone.

Limits: no real pupil data, external integrations or remote AI; no deployed ClamAV/OCR quality claim; no full PDF/Word/.eml/attachment review in a browser; no assistive-technology, full mobile or complete 100-plus-record exercise. Recall API verification uses FastAPI TestClient plus its actual local model-protocol HTTP fixture; its UI failure is independently reproduced with jsdom. This report requires author fixes and reviewer re-verification before acceptance.

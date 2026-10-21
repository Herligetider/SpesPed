# J07 intake UI independent review

Current candidate: `278613efb0fdbef7e93b88d86b542c204a75d671` (2026-10-21), including UI repair `29bcbc0bf5d03afe0ea250bd8acfc6f119171328` and the separately reviewed backend transport/assignee contract.

Current decision: **accepted for the bounded document-intake and source-review UI; no remaining blocking findings in this reviewed subset**. All nine original findings and the two follow-up save/retry findings below were independently rechecked. This is not acceptance of whole J07, complete F03–F05, the teaching workflow or production deployment.

## Current recheck and evidence

The exact candidates were archived separately at `var/review-j07-recheck` (`29bcbc0`) and `var/review-j07-final` (`278613e`). Shared uncommitted IEP, gateway, plans and teaching work was excluded. Backend imports used only each archive's absolute `backend` / `backend/tests` paths. These rechecks changed no production source and made no commits or pushes.

| Finding | Verified final behavior |
|---|---|
| R1: school scope | Selecting another school removes original blobs, text, fields, tasks and drafts. A delayed A source response cannot replace the loaded B source. |
| R2: navigation/page/write races | Actual delayed source, page and committed-write responses do not replace the later source/page, disturb its new draft, refresh it or add a stale success notice. |
| R3: reviewed content | The corrected value is the current displayed and confirmed value; the original proposal is separately labelled, and the literal source excerpt is visible. |
| R4: model recall | With the model list still returning 503, an independent same-span manual field can be created, reviewed, confirmed and reopened after browser reload. Recalled generated prose remains unavailable. |
| R5: unknown note save | A committed response can be dropped and retried with exactly the same JSON, request key and source identity. Only one matching source is stored; a newer draft is preserved. |
| R6: stale edit | The actual 409 stays visible. Explicit refresh retains the attempted replacement next to the competing current value, and can carry it deliberately into a clarification. |
| R7: Unicode transport | A real upload named `independent–東京😀.txt` with Japanese/emoji sender metadata succeeds and retains its explicit original date. |
| R8: Unicode excerpts | Keyboard source selection produces the displayed literal excerpt and backend code-point offsets, including supplementary Unicode. Manual submission succeeds. |
| R9: dates | Occurrence starts blank; explicit Europe/Oslo local input is stored as the correct UTC instant, separately from recording time. Original document dates are entered, persisted and shown. |
| R10: resolved file retry | Explicit successful retry clears an unchanged file. Native required-file validation blocks an additional import click; there are two HTTP attempts and one durable source. |
| R11: edits while saving | A newer note, file, file metadata or review edit survives the earlier response. Confirmation's seven attribution controls are disabled while the exact confirmation is pending. |

The `29bcbc0` recheck independently passed the original nine checks, 32 web tests/build and actual pagination, but found two additional P2 problems. These were passed to the root author before the final repair:

- **R10, historical P2, now fixed:** `retryFile()` at `29bcbc0` lines 308–313 retained the unchanged selected file after resolving an ambiguous save. Clicking Import again created a second source. `var/review-j07-recheck/independent-races.json` records `fileStillSelected:1` and `duplicateCount:2`. The final native-browser repeat records selection zero, one source, two requests and a required-field validation block.
- **R11, historical P2, now fixed:** `review()` at `29bcbc0` line 318 unconditionally deleted a replacement typed while the first correction response was delayed. `independent-pagination-edits.json` in that archive records an enabled input followed by no visible newer edit or comparison control. The final pin retains the newer value in “Din beholdte retting” beside the saved value. Its conditional reset also preserves changed note/file drafts; attribution writes prevent concurrent control edits.

On the final pin, independent real-browser checks additionally replaced an upload's selected File with a different File having **the same name, size and lastModified**, while the original normal save and explicit retry responses were held. The new `BBBB` bytes remained selected and natively valid; authorized original downloads proved the server had saved the submitted `AAAA` bytes. Changed sender metadata with the same File was also retained. This validates actual Chromium File identity and form validity in addition to jsdom tests.

Named authorized assignees now replace the UUID input. Source and learner excerpt selection replace numeric offset entry; “Vis kildeutsnitt” also presents the chosen literal excerpt. An isolated PostgreSQL fixture added 101 synthetic sources, learners and eligible colleagues. The browser reached **all 117 final sources** through “Vis flere kilder”, and loaded **102 actual learners and 102 actual eligible assignees** (103 options each including the empty choice), including the last named entries. The intermediate recheck independently reached 111 sources with the same people pagination. Fixture rows were restricted to the reviewer's unique schema.

Final verification commands/artifacts, all under ignored `var/review-j07-final`:

- `git archive 278613efb0fdbef7e93b88d86b542c204a75d671 | tar -x -C var/review-j07-final`.
- Pinned `web`: `npm test -- --reporter=verbose` → **38 passed**, and `npm run build` → TypeScript/Vite passed (`web-tests.log`, `web-build.log`).
- `PYTHONPATH=<absolute final archive>/backend:<absolute final archive>/backend/tests <repo>/backend/.venv/bin/python reviewer_server.py`: actual FastAPI HTTP and production-built pinned web on isolated port **18877**, with a unique synthetic PostgreSQL schema, private original storage, synthetic scanner and recalled local-protocol model fixture. The independent intermediate server used 18867.
- `node reviewer_browser.mjs` → all original workflow, Unicode, date, confirmation, named-assignee, stale-edit, identical retry and recalled-manual persistence assertions completed (`independent-browser.json`).
- `node reviewer_races.mjs` → delayed source/school/page/committed-write guards and native unchanged-file retry clearing completed (`independent-races.json`).
- `node reviewer_pending_saves.mjs` → newer note/file metadata/replacement File/review preservation and locked pending attribution completed (`independent-pending-saves.json`).
- Absolute pinned-backend `reviewer_seed_pagination.py`, followed by `node reviewer_pagination_edits.mjs` → actual 100-plus pagination and repeated delayed-edit preservation completed (`pagination-seed.log`, `independent-pagination-edits.json`).

These are independently written reviewer probes retained from the first review and expanded for the repairs; the author's browser result files were context, not the acceptance evidence. Browser: installed Chromium **156.0.8078.4**, bundled Playwright core, Europe/Oslo timezone. One final normal-flow probe initially used a global inbox-total difference while another independent probe was creating its own source; that harness assertion was corrected to count its unique sender, and the rerun completed. One intermediate pagination wait originally waited for a closed select's option to be visible; waiting for its attachment corrected that harness issue. Neither required an application change.

Review servers 18867/18877 were stopped and their synthetic schemas removed; existing services on 8000/5173 were left alone. Original probes and evidence remain under `var/review-j07-intake`. No real pupil data or external model/mail/message service was used.

## Acceptance boundary and remaining scope

Accepted behavior covers manual notes/file intake, original/text review, typed manual fields, individual proposal review, explicit learner excerpt/attribution confirmation, named clarification creation/resolution/reopening, recall-safe manual recovery, pagination and the tested error/retry/race paths. Backend transport/assignee acceptance is separately documented in `docs/reviews/intake-transport-review.md`.

There is still no intake UI for AI job creation/application, a learner evidence timeline and its filters, correction/source revision history, correction commands and derivative impact review, source replacement/reprocessing, or clarification reassignment. The later teaching, assistant and post-session workflow screens are outside this subset. The baseline “remaining product scope” below is historical; source selection, named assignees and bounded list reachability have since been addressed as described above. None of these improvements establishes whole-J07/F03–F05 completion.

No deployed ClamAV/OCR-quality, external integration, assistive-technology, full mobile or complete PDF/Word/.eml attachment usability acceptance is made. Real browser file clearing, a synthetic two-page Word extraction, source selection and actual PostgreSQL persistence were exercised; the synthetic scanner remains a test adapter. These limits do not block this bounded intake repair, and remain separate delivery work.

## Historical baseline review — 53e79b9

Historical candidate: `53e79b98eb02d6f9e7d8e920ee13f21a4fe55bb8` (2026-10-21).

Historical decision: **changes required**. The intake subset supports a real persisted normal path, but the findings below prevent accepting it. This review does not accept all J07 or F03–F05.

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

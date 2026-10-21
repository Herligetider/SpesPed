# J07 teaching UI and application composition review

- Candidate: `5a71ed187afb9b0067f08dc3c85b94c3eb53e49e`; its 16-file parent diff plus the shared authenticated transport introduced by `9be7672` as present at the candidate.
- Reviewer: `/root/review_composition`, independent of the implementation authors.
- Date: 2026-10-21.
- Verdict: **changes required** for J07-TE-R1 through J07-TE-R4. Teaching/UI acceptance is withheld. Findings were sent to the orchestrator before this report; no repair is included in this verdict.

## Findings

### J07-TE-R1 — P1: recalled assistant guidance and reconciliation prose remain visible

Locations: `web/src/features/teaching/Assignments.tsx:324`, `:405–418`, `:546–553`.

The message command's conflict handler reloads only `assignment`. A successful fresh assignment response with `content: null` hides the brief but leaves the separately cached `messages` and `actuals` projections rendered. The message text, current review reason and historical review reasons are not gated by that fresh redaction.

Reproduction in actual Chromium against the frozen backend and a unique PostgreSQL schema:

1. Generate and accept a session field through the evaluated local synthetic model; review/approve the session, review/assign its assistant brief, and record guidance plus a reconciled assistant input.
2. Open the assistant assignment, loading those projections.
3. Revoke the actual model release using the authenticated backend.
4. Submit a question from the already open assistant panel. The backend rejects the now-stale brief; the conflict refresh correctly returns a redacted assignment.
5. The panel says that source-derived instructions are unavailable, yet still shows `INDEPENDENT RECALLED GUIDANCE`, the earlier answer, and the reconciliation review text. An independent backend message read now returns `text: null` for all three messages.

Evidence: `var/review-j07-teaching/independent-evidence.json`, `independent.mjs`, and the visually inspected `recall-assistant-retained.png`. The screenshot also preserves the old reconciliation reason after brief redaction. This is a UI projection-cache defect; the backend correctly redacts fresh reads.

Required behavior: invalidate or suppress every source-derived dependent projection when current assignment/source validation is lost. Refreshing only the main card is insufficient. Preserve independently recorded actual facts and local user input under their own access rules without redisplaying recalled guidance or review prose. Cover both successful redaction and partial refresh failure.

### J07-TE-R2 — P2: correcting an existing observation silently changes its session linkage

Location: `web/src/features/teaching/Observations.tsx:124–129`.

The correction payload prefers `props.session.revision_id` over `existing.session_revision_id`. Thus simply having a session selected changes the factual association of an existing observation, even when the user edits only support text. The form offers no explicit choice or confirmation for that reassociation.

Reproduction: create a saved observation with `session_revision_id: null`, select a teaching session, open Observations, choose “Rett eget notat”, and change only the support description and correction reason. The real correction succeeds and stores the selected session revision ID in place of `null`. The independent probe records the original and new references in `independent-evidence.json` (`observation_rebound`). The same precedence can replace an existing different-session reference or cause an otherwise valid correction to fail against that session's goals.

Required behavior: keep the original observation's session/assignment references during an ordinary correction, including an intentional null. Any association change must be explicit and validated. A selected planning context must not silently rewrite an already recorded fact.

### J07-TE-R3 — P2: internal teaching tabs discard unsaved work

Locations: `web/src/features/teaching/TeachingWorkspace.tsx:585–633`, `:634–647`.

The teaching tabs conditionally mount their complete panels. Moving away from “Undervisningsøkter” unmounts `CurrentSession` and its draft state; returning initializes it from the saved row without warning. The application shell preserves outer learner-workspace drafts, but this does not protect the internal teaching workflow.

Reproduction: open an existing session, change preparation to `INDEPENDENT UNSAVED PREPARATION`, visit “Observasjoner” to consult a note, and return to “Undervisningsøkter”. Preparation has reverted to the saved `Finn frem tre syntetiske kort`. The same probe first switches to “Grunnlag og planer” and back and confirms that outer switching preserves the draft, isolating the failure to the teaching tab lifetime.

Evidence: `independent-evidence.json` (`draft_lost`) and `independent.mjs`.

Required behavior: retain scoped draft/uncertain-command state across internal tabs, or explicitly guard navigation before discarding it. Switching learner, school, identity or API client must still dispose of the previous scope.

### J07-TE-R4 — P2: app integration discards actionable local validation errors

Locations: `web/src/App.tsx:41–44`; callers include `web/src/features/teaching/CreateSession.tsx:186–187` and `runtime.tsx:248–275`.

The newly integrated workspaces receive `App.displayError`, which maps every non-`ApiError` to a generic failure. Teaching's trusted local validators intentionally throw ordinary `Error` values with precise correction instructions, so their messages are lost in the real application even though isolated component tests pass a formatter that displays them.

Reproduction: enter `2027-03-28T02:30` as a planned time in `Europe/Oslo`, provide an arena and confirm the basis. This local time does not exist during the spring transition. `instant` rejects it with an explicit time-zone explanation, but Chromium displays only “Noe gikk galt. Prøv igjen, eller kontakt systemansvarlig.” Retrying the same input cannot resolve it. The same boundary handles other local date and qualification-state guidance.

Evidence: `boundary-evidence.json` (`dstErrors`), `recovery-boundaries.mjs`, `local-validation.png`.

Required behavior: preserve/localize trusted client validation messages through the root formatter, while retaining generic handling for unexpected failures. Test through the actual `App` integration rather than only a permissive test formatter.

## Isolation and completed verification

Read `AGENTS.md`. Created `var/review-j07-teaching/pin` with `git archive` of the exact candidate. Archived `web/node_modules` links only to installed dependencies; application sources are frozen. The reviewer independently built its production bundle and served that bundle with the archived real FastAPI application. Absolute Python imports were:

```text
/Users/lauritz/Programming/SpesPed/var/review-j07-teaching/pin/backend
/Users/lauritz/Programming/SpesPed/var/review-j07-teaching/pin/backend/tests
```

`import-origins.txt` confirms the archived backend. `exact-files.log` confirms all 16 candidate files plus `web/src/api.ts` match the pinned Git blobs byte-for-byte after verification. The backend used the shared Python 3.12 runtime, synthetic identities, actual loopback PostgreSQL, and the reviewer-owned unique schema `j05_860048bcc8ac48f493a87b995ff507c2`. Chromium used `Europe/Oslo`; the model service was the synthetic local loopback fixture. No real pupil data, external model or external messaging was used.

| Verification | Result | Evidence under `var/review-j07-teaching/` |
| --- | --- | --- |
| `npm test -- --reporter=verbose` from archived `web` | 67 passed, six files | `web-tests.log` |
| `npm run build` from archived `web` | TypeScript and production build passed | `build.log` |
| Real normal browser workflow in fresh reviewer environment | Completed, exit 0 | `normal-replay.mjs`, `normal-replay.log`, `evidence.json` |
| Independently authored adverse browser probes | Completed; records TE-R1/R2/R3 | `independent.mjs`, `independent.log`, `independent-evidence.json` |
| Real manual recovery after model recall | Completed, exit 0 | `recovery-replay.mjs`, `recovery-replay.log`, `repair-evidence.json` |
| Independent retry, unassessed ITO, group-scope and local-validation probes | Completed, exit 0 after reviewer assertion correction; records TE-R4 | `recovery-boundaries.mjs`, `boundary-recheck.log`, `boundary-evidence.json` |

Each browser command used `node var/review-j07-teaching/<script>.mjs`. The normal and manual-recovery scripts replay author scenarios against the reviewer's separately built application/database; they are not represented as independently authored scenarios. The adverse and boundary scripts are independent. Their exit 0 indicates completed evidence collection, not absence of findings. All processes were awaited and logs inspected.

The normal browser run exercised manual exact-goal basis/session creation; a real evaluated model job and support-only field merge; separate exact human review and approval; brief review and dated named-assistant assignment; assistant inbox without ordinary learner reads; question/answer, actual input and observation; exact delivery reconciliation; two pupils with 30 minutes each versus one employee's 30 minutes; observation reuse in the next basis; and a 390px layout without horizontal overflow.

Independent checks additionally established:

- Outer learner workspace switching preserves a teaching draft, and scoped component tests cover late learner responses and client identity replacement.
- An untouched occurrence containing `.000123` retains all microseconds through a real Chromium correction despite native input normalization. Existing tests cover ambiguous/nonexistent times and inclusive date intervals across DST; TE-R4 concerns their presentation through `App`.
- A response aborted after the server committed an observation can be retried with identical body/key and produces exactly one saved fact.
- Actual ITO entered without a qualification adapter remains `unassessed`, requires partial status/cause and a persisted named follow-up, and does not turn a staff role label into qualification evidence.
- A teacher with only learner A's scope sees neither learner B nor group narrative and receives 403 for full group delivery.
- After actual model recall, fresh session reads are redacted. Explicit independent manual replacement with a new basis clears only declared model lineage; old historical generated content and the previous assistant brief stay redacted.

One initial browser launch preceded fixture readiness and was rerun after `ids.json` existed. The boundary probe initially expected an unassessed delivery's gated follow-up projection to expose its owner; it was corrected to verify the persisted follow-up task under that task's own authorized endpoint. The rerun passed; no application changes were made. The reviewer listener was stopped. Signal termination left its temporary schema, so the reviewer explicitly removed only that recorded schema and verified its absence (`cleanup.log`). Probes and screenshots remain for repair verification.

## Separate baseline and required remaining work

The planning module's separate review already withholds acceptance for J07-PL-R1 (P2, repeated-hour/microsecond editing) and J07-PL-R2 (P1, recalled current-plan prose in history after partial refresh failure). Those are independent baseline findings, not duplicate teaching findings or repairs covered here. The integrated root UI cannot be accepted while either module's blocking findings remain unresolved.

Passing checks do not establish whole-feature completion. Durable model-job listing/resume, full Nynorsk, timed practitioner/assistant usability, the production qualification adapter, and assessed provision-comparison UI remain required work. Legal sources were not re-researched. No production files were edited, and the reviewer did not commit, push or spawn agents.

## Independent repair recheck — `280bdcc43a04d3a65ffe88f9f2c60eea97016bd6`

Rechecked on 2026-10-21 by the same independent reviewer. The original review above is preserved. This recheck covers the 12 repair files only; it excludes the concurrently developed proposal-recovery UI and other later changes.

**Verdict: R1, R2 and R4 are verified fixed at this pin. R3 remains partially fixed, with two independently reproduced P2 gaps below. Overall teaching acceptance remains withheld.**

### Verified repairs

- **J07-TE-R1:** Assignment access revisions now invalidate dependent message/actual-input reads together. Fresh current-access validation gates retained views, and a redacted brief gates message text, review reasons and historical review reasons. In real Chromium, the original post-recall question receives 409 and no cached guidance or reconciliation prose remains visible. A separate assistant context received an intentionally failed current-assignment GET while two pre-recall child responses were held. All retained views were hidden during that failed validation. After actual model release revocation, retry returned a redacted assignment; releasing the held old message/input responses still exposed no recalled guidance or review text. Independently recorded actual activity remained visible under its own access rules. This verifies the original finding and the partial-refresh/late-response branch.
- **J07-TE-R2:** Real prose-only corrections preserve both an original null session/assignment pair and an original exact session/assignment pair while a different session is selected. The probe also confirms that `.000123` occurrence precision and revision history are retained.
- **J07-TE-R4:** The actual `App` displays `LocalValidationError` instructions for the nonexistent Oslo time without sending a basis command. The exact-pin app tests also pass the unassessed-ITO corrective-message case and the unexpected-error case, which keeps an arbitrary diagnostic private behind the generic fallback. Code inspection confirms the typed exception is the only new ordinary-error disclosure branch.
- **J07-TE-R3, original simple case:** Local session, observation and delivery drafts now survive ordinary internal tab round trips when their saved backing records remain unchanged. This does not cover the two remaining cases below.

### J07-TE-R3 — P2 remains: concurrent refresh still destroys the local session draft

Repair locations: `web/src/features/teaching/TeachingWorkspace.tsx:555–560`, `:593–595`, `:647–648`.

Returning to sessions correctly fetches the current record, but a newer saved revision immediately replaces `retainedCurrent` and changes the `CurrentSession` key. React therefore destroys the local draft rather than showing it alongside the competing revision for an explicit decision.

Independent real-browser reproduction:

1. Open a manual session and type `INDEPENDENT PRESERVED SESSION DRAFT` into preparation.
2. Move to another teaching tab.
3. Save a real parallel revision through the authenticated API with preparation `INDEPENDENT CONCURRENT SAVED PREPARATION`.
4. Return to sessions. The automatic refresh displays revision 2 and the editor contains the concurrent text; the user's unsaved preparation is gone without warning or an explicit comparison/rebase decision.

Evidence: `var/review-j07-teaching-repair/independent-evidence.json` (`R3_concurrent_refresh_destroys_draft`), `independent-recheck.mjs`, `draft-freshness.png`.

Required behavior: separate current server projection from the scoped local edit buffer. A fresh competing revision should invalidate approval/write assumptions and offer a deliberate comparison/rebase; it must not silently replace the local buffer. Recalled source/model prose must continue to remain hidden while resolving this state.

### J07-TE-R3 — P2 remains: preserved basis drafts do not refresh reusable observations

Repair locations: `web/src/features/teaching/TeachingWorkspace.tsx:622`; `web/src/features/teaching/CreateSession.tsx:123–130`.

The new-session form now stays mounted while hidden, but receives no active-tab signal and its observation-choice read depends only on client/school/learner. Returning to the tab refreshes the session list/current session, not the basis choices.

Independent real-browser reproduction:

1. Open “Planlegg ny økt”, enter a planned time and arena, choose an active goal, and open reusable observations.
2. Move to Observasjoner and save `INDEPENDENT NEW NOTE WHILE BASIS OPEN` through the UI.
3. Return to sessions. The arena and goal draft survive, but the new confirmed observation is absent from the selectable basis choices. An authoritative observation-list GET confirms it exists. There is no successful-read refresh control in that choice section; closing/reopening the new-session form loses its draft.

Evidence: the same independent script/JSON records `R3_choices_not_refreshed` with `newObservationExists: true` and `visibleChoiceCount: 0`.

Required behavior: refresh current reusable choices when a retained basis form is reactivated, without dropping typed values or exact selections. Revalidate selected IDs against those fresh choices before use. Check the equivalent retained source/profile and staff choices where applicable.

### Recheck method, results and cleanup

Created a fresh archive at `var/review-j07-teaching-repair/pin` and independently built its full application. Python used absolute archived `backend` and `backend/tests` imports; `import-origins.txt` confirms the archived application. Real FastAPI served only the archived production bundle on the reviewer listener. Actual PostgreSQL used a new synthetic schema, `j05_626a7a6efb2f439eba26b7a7c5a664c2`, separate from the first review and author fixtures. All 12 repair files were subsequently checked byte-for-byte against the exact commit (`exact-files.log`).

- Archived `npm test -- --reporter=verbose`: **77 passed**, six files, 3.29 s (`web-tests.log`).
- Archived `npm run build`: TypeScript and production build passed, 53 modules (`build.log`).
- `node var/review-j07-teaching-repair/normal-replay.mjs`: replay of the author normal scenario against the independently frozen full app completed all 11 workflow steps, including actual local model execution, human approvals, assistant input/reconciliation, group counting, next-basis reuse and narrow viewport (`normal-replay.log`, `evidence.json`).
- `node var/review-j07-teaching-repair/independent-recheck.mjs`: independently authored original-finding and combined adverse probes completed; verified repairs and both remaining R3 violations are recorded in `independent-evidence.json`. Exit 0 means evidence collection completed, not overall acceptance.

The initial scaffolding-copy command referenced the author's old browser filename; the reviewer corrected it to `normal.mjs` before running the browser. No application change was made. All test/browser processes were awaited. The reviewer listener was stopped, only its recorded temporary schema was removed after signal termination, and a namespace check verified cleanup (`cleanup.log`). Probes, logs and screenshots remain for the next recheck.

The reviewer appended only this report and wrote ignored review artifacts. No production edits, commits, pushes or subagents. Prior planning-review findings and all previously listed whole-feature limitations remain outside this bounded repair acceptance.

## Independent R3 follow-up — `004e19f935450f3260c4c1036530a4cfec8e6742`

Rechecked on 2026-10-21. This section covers the three-file follow-up (`TeachingWorkspace.tsx`, `CreateSession.tsx`, and `TeachingDraftReactivation.test.tsx`) at the exact pin, preserving the earlier findings and recheck. Concurrent proposal-recovery work and later backend projections are excluded.

**Verdict: both remaining J07-TE-R3 gaps are verified fixed. R1/R2/R4 regressions pass. Overall teaching acceptance remains withheld for the additional independently reproduced P1, J07-TE-R5, below.** This does not accept all of J07 or any whole feature.

### J07-TE-R3 closure and regression evidence

The independent real-application probe now verifies:

- The original unsaved session preparation survives a real concurrent revision while another teaching tab is active. The current revision is displayed separately; saving remains disabled until explicit comparison. A second writer then changes the record after that comparison. The ensuing real HTTP 409 still preserves the draft and its explanation. A second explicit comparison saves the retained draft against the latest exact expected version, producing revision 4.
- A retained new-session basis offers the observation saved through the other tab while preserving arena and the selected exact goal. Correcting that selected observation subsequently makes the old revision unavailable. The form blocks confirmation, retains the other values, and requires explicit removal of the obsolete selection. It does not silently select the replacement observation.
- An old generated edit buffer is rechecked even when the newer independently authored current revision and its version are unchanged. Actual model release revocation hides the old buffer, including when an earlier authorized history response is released late. Explicit discard adopts the safe current manual content. This verifies the **edit-buffer** gate; the separate saved-history presentation has the R5 defect below.
- The earlier simple internal session/observation/delivery draft round trips pass. R1's actual recall, failed current-assignment refresh and held old message/input responses remain gated; independently recorded actual facts remain available. R2 corrections retain both original null and exact session/assignment links, including `.000123` occurrence precision. R4's real App shows the trusted nonexistent-time instruction without sending a basis command.

The exact-pin 88-test suite additionally passes the late-own-success buffer test, explicit discard, historical-read failure, stale selected profile/source cases, named staff refresh, and generic unexpected-error handling. The late-own-success test changes local state using the component test harness while a response is pending; it is not represented as a separate physical-browser typing scenario.

Evidence: `var/review-j07-r3-final/independent-recheck.mjs`, `independent-evidence.json` (nine completed checks, no findings in that probe), `draft-freshness.png`, `historical-recall.png`, and `late-recall-redaction.png`.

### J07-TE-R5 — P1: saved revision history retains recalled generated prose when the current manual revision is unchanged

Exact-pin locations: `web/src/features/teaching/TeachingWorkspace.tsx:215–224` and `:405–408`.

`SessionHistory` fetches saved revisions using dependencies that omit tab reactivation and the fresh current-access read. Its component key also remains unchanged when the current revision ID and source status are unchanged. A model dependency can be revoked for an older revision while an independently authored newer revision remains current. Refreshing that current record therefore leaves the old history projection mounted and authorized only by its earlier read.

Independent Chromium/FastAPI/PostgreSQL reproduction:

1. Create a real local-model proposal, merge its support field into session revision 2, and complete the normal exact review/approval workflow.
2. Save revision 3 with explicitly independent manual support and the `support` manual-replacement declaration. The backend confirms the current support no longer carries the old model lineage.
3. Select revision 3 and expand **Lagret revisjonshistorikk**. Revision 2 currently shows `Synthetic AI visual support`.
4. Move to Observasjoner and revoke the actual evaluated model release through the authenticated API.
5. Return to Undervisningsøkter. Current revision 3 remains available with the same revision ID and version. A fresh authoritative revision-history GET returns `content: null` for revision 2, but the open history panel still visibly renders `Synthetic AI visual support` and its earlier approval presentation.
6. Click **Kontroller lagrede økter på nytt**. The recalled historical prose remains visible.

This is not an inferred backend defect: fresh backend history is correctly redacted. It is a retained browser projection after a current-access refresh. The reproduction does not require an unsaved edit buffer, so the new buffer-source gate cannot protect this path.

Evidence: `var/review-j07-r3-final/history-edge/history-probe.mjs`, `history-evidence.json`, and visually inspected `history-recall.png`. The evidence records one visible recalled text instance both after reactivation and after explicit refresh, alongside a null authoritative historical content value and unchanged current revision ID/version.

Required repair: revalidate the saved-history projection on the same relevant access/activation refresh boundaries, suppress its previous source-derived rows while validation is pending or fails, and ignore obsolete late responses. Do not infer historical authority from a still-authorized current manual revision. Recheck the original sequence, explicit refresh, partial history-read failure, and a held pre-recall history response; retain the successful R3 draft behavior.

### Exact-pin verification, isolation and cleanup

`var/review-j07-r3-final/pin` is a Git archive of the exact candidate. `exact-files.json` checks all three changed files byte-for-byte against Git. The shared dependency directory supplies installed packages only. The full application production bundle was independently built from the archive. Both actual FastAPI listeners imported the archived backend using absolute paths:

```text
/Users/lauritz/Programming/SpesPed/var/review-j07-r3-final/pin/backend
/Users/lauritz/Programming/SpesPed/var/review-j07-r3-final/pin/backend/tests
```

| Completed check | Result | Evidence under `var/review-j07-r3-final/` |
| --- | --- | --- |
| Archived `npm test -- --reporter=verbose` | 88 passed, seven files, 4.11 s | `web-tests.log` |
| Archived `npm run build` | TypeScript and production build passed, 53 modules | `build.log` |
| Real normal workflow replay | All 11 steps completed | `normal-replay.log`, `evidence.json` |
| Independent R3/adverse/regression probe | Nine checks completed | `independent-recheck.log`, `independent-evidence.json` |
| Fresh second real environment and normal replay | All 11 steps completed | `history-edge/normal-replay.log`, `history-edge/evidence.json` |
| Independently authored open-history recall probe | Completed; confirms R5 | `history-edge/history-probe.log`, `history-edge/history-evidence.json` |

The normal scripts replay the previously reviewed author scenario against the separately frozen application; the adverse and history probes are independently authored. Initial probe attempts encountered only reviewer selector mismatches: the first expected an alert with different wording, and the history preparation encountered a strict selector matching both a history definition and an edit field. The corrected probes completed without application edits. Preserved `attempt1-*` evidence and `history-edge/README.txt` describe these corrections and the reusable fresh-fixture reproduction. Passing probe exit codes indicate completed checks/evidence collection, not overall acceptance.

All processes were awaited. The reviewer stopped only its listeners on 18894 and 18895 (PIDs 58411 and 60327), then removed only their recorded synthetic PostgreSQL schemas, `j05_b905a222a39a4f55ba11dba481052a21` and `j05_4e1ca7c6a93441cba4fe6f1242557646`. `cleanup.json` confirms both listeners stopped and both namespaces absent. Ports 8000, 5173 and 18878 were untouched. No real pupil data, external model, production edits, commits, pushes or subagents were used.

Earlier whole-feature limitations and separately reviewed planning work remain outside this bounded recheck. The original R3 repair is closed; R5 must be independently verified after repair before teaching acceptance.

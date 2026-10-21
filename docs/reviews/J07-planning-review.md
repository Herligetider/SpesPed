# J07 planning UI independent review

Candidate: `1bf5ecefcf0d68fe5ade2b16d2d402892cba4814`. Reviewer: independent `review_j05`. Verdict: **changes required** for J07-PL-R1 and J07-PL-R2 below. Both findings were sent to the orchestrator and assigned to the original author; no repair is included in this verdict.

## Scope and isolation

Reviewed the ten candidate files under `web/src/features/planning/`, including the tests, and the directly used `ApiClient` transport at this pin (transport candidate `9be7672`). Reused the previously read F02/F07/F08 and domain contracts and read `AGENTS.md`. This is component acceptance, not acceptance of RootApp integration, teaching UI, or the entire J07/F02/F07/F08 scope. Earlier manual-core and generated-backend review histories are unchanged.

Created `var/review-j07-planning/pinned` with `git archive 1bf5ecefcf0d68fe5ade2b16d2d402892cba4814`. The only dependency link is archived `web/node_modules` to the installed dependencies. A review-only entry mounts the exact archived component with the real archived `ApiClient`. The copied author fixture was adjusted only as scaffolding to use the archived backend, its Alembic configuration, reviewer ports 8093/5293, synthetic identities, and a fresh PostgreSQL schema. No live shared implementation was imported. Absolute `PYTHONPATH` was:

```
/Users/lauritz/Programming/SpesPed/var/review-j07-planning/pinned/backend:/Users/lauritz/Programming/SpesPed/var/review-j07-planning/pinned/backend/tests
```

`import-paths.log` asserts that `spesped.main`, plans service, `plans_fixtures` and `plan_generation_fixtures` resolve under that archive. Backend Python was the shared `.venv/bin/python` runtime only. Database was the permitted loopback PostgreSQL test database on 55432, scoped to `j07_planning_review_0fc110b736cb413795d8675fa4438540`; no demo database or other schema was used. Authentication, CSRF, assignment/case grants, source confirmation, gateway evaluation/release, generation, review and activation were real backend operations. Model responses came from the local synthetic loopback fixture. Browser runs used Chromium with `Europe/Oslo` time zone. Network faults were deliberate Playwright aborts of specified requests, not fabricated successful API responses.

## Findings

### J07-PL-R1 — P2: unchanged microseconds during a repeated local hour invalidate editing

Locations: `web/src/features/planning/shared.tsx:142–153`, `:202–224`, particularly select value `:207` and option values `:220`.

`localValue` preserves an original UTC timestamp with six fractional digits in its hidden suffix. The repeated-hour select, however, only offers `Date.toISOString()` timestamps with three fractional digits. Its controlled value therefore matches no option for an existing instant such as `2026-10-25T01:30:00.123456Z` (second 02:30 occurrence in Oslo). Both the plan and its goal render a required select with an empty DOM value, although the instant is already known exactly. An unrelated title edit cannot be submitted. Choosing an offered occurrence uses the millisecond option value and loses the original microseconds.

Reproduction: real API creates an ordinary teaching plan and goal with that exact instant; open its editor and change only the title. `date-browser.mjs` finds both repeated-hour selects invalid and the form invalid; clicking save sends **zero** revision commands. Desired-behavior assertion fails with `false !== true`. The non-fold microsecond case passes separately, including the real conflict test below, so this is the combined fold/precision branch. Evidence: `date-evidence.json`, `date-browser.log`, `date-fold.png` under the reviewer directory.

Required behavior: preserve the known original exact occurrence and timestamp for unchanged fields; require an occurrence choice when the user enters a new ambiguous local time.

### J07-PL-R2 — P1: history redisplays recalled current plan prose after partial refresh failure

Locations: `web/src/features/planning/PlanWorkspace.tsx:126–128`, `:193`, `:439–457`, especially `:457`.

`PlanDetail` retains the previous current-plan response across refresh failure. Its main view correctly requires a freshly loaded current source status at `:147`, but `History` is rendered outside that gate and receives the retained plan. Once a historical revision is selected, the comparison renders the retained current plan through `PlanView`; its obsolete cached `source_status: current` passes that component's check. The adjacent comparison also receives that stale object.

Reproduction: generate/apply only a title, perform actual review/approval/activation, create a later manual revision, open its history and select the original manual revision. Revoke the actual model release through the authenticated backend. Abort only the next current-plan GET and click “Hent gjeldende plan og kildekontroll”. The revisions GET succeeds and explicitly reports the current revision as `review_required`. An independent authoritative current-plan GET also returns `review_required` with **no title**. Nevertheless, history visibly displays “Syntetisk manuelt revidert plan · revisjon 3” and its full retained content under “Gjeldende lagrede revisjon”. Thus a successful fresh read already establishes redaction while a separate failing read allows the stale protected prose to remain visible.

`history-browser.mjs` fails its desired-behavior assertion: expected zero visible stale headings, observed one. Evidence: `history-evidence.json` records the authoritative redaction, successful history status and visible prose; `history-after-recall.png` and `history-browser.log` preserve the UI result. This is a frontend cache/projection defect; the tested backend correctly redacts the recalled revision. It does not imply unrelated source-permission defects.

Required behavior: gate every current-plan prose/comparison projection on successful current validation, including history. A retained draft can survive without redisplaying stale source/model prose. Previously authorized unaffected historical records can still be independently read.

## Independent verification

Commands executed against the archive (logs and scripts under `var/review-j07-planning/`):

```
# cwd: var/review-j07-planning/pinned/web
/opt/homebrew/bin/node node_modules/vitest/vitest.mjs run src/features/planning/PlanningWorkspace.test.tsx src/api.test.ts
/opt/homebrew/bin/node node_modules/typescript/bin/tsc -b --pretty false
# cwd: repository root; each script uses the frozen review harness
/opt/homebrew/bin/node var/review-j07-planning/normal-browser.mjs
/opt/homebrew/bin/node var/review-j07-planning/date-browser.mjs
/opt/homebrew/bin/node var/review-j07-planning/history-browser.mjs
/opt/homebrew/bin/node var/review-j07-planning/pagination-browser.mjs
/opt/homebrew/bin/node var/review-j07-planning/conflict-browser.mjs
```

- Unit/transport: **24 passed** (13 planning, 11 transport), two files; typecheck **exit 0**. Unit cases include ancillary permission failure/manual fallback, scoped responses, immutable unknown-outcome retries, explicit conflict rebase, selected-goal human dates/curriculum, proposal rejection, and separate precision/fold conversions. Passing tests do not cover the two combined adverse branches above.
- Real normal browser: **exit 0**. Source-backed profile proposed/confirmed; recommendation/decision and separate authorities displayed; actual evaluated model request/run/diff/title-only apply preserves the manual goal and requires human review; review/approve/activate succeeds; committed-but-aborted revision retry sends an identical command and creates only one revision; exact historical comparison works; 390px mobile viewport has no horizontal overflow. Screenshots visually inspected.
- Real pagination/scope browser: **exit 0**. 103 confirmed synthetic profile records are reachable across three pages. The extra rows are fixture-only data tied to the existing source, not a claim of UI authoring all 103 records. A held learner-A response arriving after switching to learner B does not expose A prose. Creating a new B case displays the explicit no-implicit-dossier-access notice, and the protected case listing remains empty without a separate grant.
- Real conflict browser: **exit 0** after correcting fixture setup to assign a new goal identity to a new plan (the initial reused-identity setup was correctly refused with 403). A parallel real revision causes 409; the user's draft survives both rejection and refresh, an explicit comparison/rebase updates the expected version from 1 to 2, and one deliberate new command creates revision 3. Original non-fold `.123456Z` periods remain exact. Arrow-key tab navigation preserves selected/focused state.
- The two adverse scripts intentionally **exit 1** on desired-behavior assertions, with concrete evidence above. All review browser processes were awaited; results are saved, not inferred from in-progress sessions. Both reviewer listeners (8093/5293) are closed and a direct PostgreSQL namespace query confirms the reviewer schema was removed by fixture teardown (`cleanup.log`). All ten archived candidate files were checked byte-for-byte against the pinned commit after testing.

The reviewer changed only this report and ignored review scaffolding/evidence. No production edits, commits, pushes, subagents, external messages or real pupil data were used. Acceptance remains withheld until both fixes are independently verified. Full referral/consent/contact UI, guardian relations, owner/delegation/access administration, decision correction editing, full Nynorsk translation, practitioner usability, RootApp integration and full F08/UI completion remain outside this component verdict; the tests do not establish legal, school or production readiness.


## Independent repair recheck — 2e3c851

Rechecked exact `2e3c85184f08f8ac294a0bc2e778eb32f57070ed`, including the three changed planning files (`shared.tsx`, `PlanWorkspace.tsx`, and the component tests). **J07-PL-R1 and J07-PL-R2 are closed on this pin. Bounded planning-component acceptance; no remaining concrete findings from this recheck.** The original candidate report above remains historical evidence and has not been rewritten.

A fresh `git archive` was extracted to `var/review-j07-planning/recheck/pinned`; all ten planning files were checked byte-for-byte against the repair pin after testing. Absolute `PYTHONPATH` was the new archive's `backend:backend/tests`, overriding the editable installation; `recheck/import-paths.log` verifies main, plans service and both fixture module paths. PostgreSQL used only fresh schema `j07_planning_recheck_24ff40b587024257997dc63072fc6cca` on the authorized loopback 55432 test database. The copied synthetic backend fixture, local model wire and component harness were bound to the new archive. The real RootApp now present in this pin was also exercised through its ordinary `/` entry, login, learner selection and planning navigation; this adds integration evidence for these fixes without replacing the separate RootApp/teaching acceptance review.

Commands (cwd is archived `web` for the first two; repository root for browser scripts):

```
/opt/homebrew/bin/node node_modules/vitest/vitest.mjs run src/features/planning/PlanningWorkspace.test.tsx src/api.test.ts
/opt/homebrew/bin/node node_modules/typescript/bin/tsc -b --pretty false
/opt/homebrew/bin/node var/review-j07-planning/recheck/normal-browser.mjs
/opt/homebrew/bin/node var/review-j07-planning/recheck/date-browser.mjs
/opt/homebrew/bin/node var/review-j07-planning/recheck/history-browser.mjs
/opt/homebrew/bin/node var/review-j07-planning/recheck/conflict-browser.mjs
/opt/homebrew/bin/node var/review-j07-planning/recheck/race-browser.mjs
/opt/homebrew/bin/node var/review-j07-planning/recheck/native-app-browser.mjs
```

Every listed final command completed with **exit 0**; output/evidence files with the matching names are preserved under `var/review-j07-planning/recheck/`. Unit/transport result: **27 passed**, two files (16 planning, 11 transport). Typecheck passed. The original independent desired-behavior assertions were preserved: the copied history probe only adds capture of actual pre-recall responses for the additional race probe.

- **R1 closure:** the original combined microsecond/late-fold probe now finds both required native selectors valid, selected at exact `2026-10-25T01:30:00.123456Z`, with matching six-digit options. A title-only click sends exactly one revision command. Separately, the real RootApp/native form test records an actual 201 response and proves both persisted plan and goal instants remain `2026-10-25T01:30:00.123456+00:00`. Entering a new ambiguous local 02:31 clears the occurrence choice and blocks native submission until the user explicitly selects an occurrence. No extra command is sent while the form is invalid. Evidence: `date-evidence.json`, `native-app-evidence.json` and their logs.
- **R2 closure, original reproduction:** after actual model release recall and aborting only the current-plan GET, fresh history and the authoritative current endpoint both say `review_required`; history renders zero stale current headings and displays the validation warning. The selected unaffected manual historical revision remains readable. Evidence: `history-evidence.json`, `history-after-recall.png`.
- **R2 closure, additional response race:** replayed the actual successful current-plan and history-head payloads captured before recall while allowing the full history request to reach the real backend after recall. The current-plan success is deliberately released only after fresh history has returned `review_required`. Neither that late 200 nor stale head metadata restores current prose; closing/reopening history also cannot restore it. The independently authorized manual historical revision stays visible. There were two stale current successes and two stale head successes in this probe; these are deliberately delayed/replayed real responses, not evidence that the recalled backend emits current prose. Evidence: `race-evidence.json`, `race.png`.
- **Draft and normal behavior:** the real RootApp editor retains the user's manual draft in its hidden DOM during failed validation and restores the same draft when a fresh read succeeds. The real 409 test again preserves the draft and requires explicit rebase before a new command. The normal source/profile, comparison, evaluated title-only generation, human review/approval/activation, identical unknown-outcome retry, history and mobile checks all pass again. Two initial RootApp probe attempts timed out because the accessibility-role locator correctly excluded the hidden textbox; their evidence is preserved as `.initial` and `.initial2`. Only the probe was corrected to inspect the hidden DOM input directly. The final probe passed; this was not an implementation failure.

All browser/test processes were awaited. Reviewer listeners 8093/5293 are closed, and a direct PostgreSQL namespace query confirms fixture teardown removed the unique reviewer schema (`cleanup.log`). No production files, commits, pushes, other schemas or other services were changed by the reviewer. The original scope exclusions and full-feature/production-readiness limits still apply.

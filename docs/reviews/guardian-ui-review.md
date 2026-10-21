# Guardian UI independent review — 83699e5b389d04157f177998d7ca26aa40f23286

Verdict: **changes requested** for one P2 withdrawal race. This review covers the eight candidate web files and their existing API/App composition. It does not accept complete F21, J21, accessibility coverage, production operations or provider integrations. The accepted BC11 backend boundary in `docs/reviews/J12-review.md`, including its transaction ownership repair, remains separate evidence.

## Finding

**[P2] Invalidate an in-flight open when a successful refresh removes its grant** — `web/src/features/guardian/GuardianPortal.tsx:66–69` (late assignment at line 113).

`runOpen` clears `selectedRef` before awaiting the command and payload, and sets it again only once both finish. Successful list refresh invalidation checks only `selectedRef.current`. If the backend removes this grant while its payload response is in flight, a focus/manual refresh can return an empty accessible list without changing the operation scope. The late response then passes its scope guard and redisplays the withdrawn letter body and attachment controls. A pre-withdrawal request may legitimately have been served before revocation but complete in the browser after the newer list response. The UI has already learned that no letters are accessible and must not restore the older response.

Independent reproduction is `var/review-guardian-ui/guardian-adverse.test.tsx`, test `does not redisplay a late payload after a successful refresh removes its in-flight grant`: list one active grant; open it and hold the payload promise; dispatch window focus and return `{items: [], total: 0}`; wait for “Du har ingen tilgjengelige brev nå.”; complete the held payload. The protected body remains rendered, failing the absence assertion. Track/invalidate the pending grant as well as the displayed grant when a same-page authorization refresh removes it, while retaining the existing valid-open-during-focus-refresh behavior. Distinguish pagination from an authorization refresh if using the page list to establish grant presence. Original author repair and independent recheck are required.

## Pin and inspection

Created with `git archive 83699e5b389d04157f177998d7ca26aa40f23286 | tar -x -C var/review-guardian-ui/pin`. The archive is ignored by Git. Frozen source imports use the archive; `pin/web/node_modules` is a symlink to installed `/Users/lauritz/Programming/SpesPed/web/node_modules`. No mutable checkout product file supplied the reviewed behavior. The independent test imports `./pin/web/src/features/guardian/GuardianPortal`; its own Vitest configuration uses `./pin/web/src/test-setup.ts`. No backend suite or editable Python import was used.

Read all eight candidate files, AGENTS.md, the docs/10 review/model policy, J12 acceptance/recheck, full API transport and native App session handlers, and BC11 portal retrieval/command/access code. App guardian routing suppresses learner list/profile calls and staff navigation for the selected guardian school. Component keying and inactive-operation guards protect identity/school/client transitions and close/unmount. Open binding and explicit read acknowledgment remain distinct. Server rights checks continue to protect attachment retrieval; this finding concerns restoring already-returned content after newer withdrawal information. Bodies render as text. Buttons have accessible names, status/error announcements and visible keyboard focus; Nynorsk controls were exercised independently. This is not a complete browser, screen-reader, translation or accessibility audit.

All eight archive SHA-256 values exactly matched `git show <revision>:<path>` bytes. Full machine-readable comparison: `var/review-guardian-ui/hash-proof.json`.

| File | SHA-256 |
| --- | --- |
| web/src/App.tsx | 7957125f001eb30f884068ffb39acfac95c0152c65e3f563a4a7c1fe51c7dc98 |
| web/src/App.workspaces.test.tsx | 2626701b6a10c776dc2b6734d62d4ca7981260dd1689b421b888d8beda34e55b |
| web/src/api.test.ts | e727ee2757dc04c83a05089f9ba555d0614ad57341f1f3fbb4fa4050aeb62127 |
| web/src/api.ts | 6faa1d8a9d5b92d79f6e8cb9ee87e7f772ee088d50801be132aadfd2a9ea6d21 |
| web/src/features/guardian/GuardianPortal.test.tsx | 25d2a7c543fe1055f564dfb0fe9a6527037dc323114082813f73eaaa4fb4ee7e |
| web/src/features/guardian/GuardianPortal.tsx | 550ed15c852b0d03d850edd845649c88aa0ec06acc6ed0c8a3314f79c1f13f86 |
| web/src/features/guardian/guardian.css | d0f42e142059ba9f79bc186c0b3d148c1702df017568b4118903e3432e927d85 |
| web/src/features/guardian/types.ts | b1f74fa2943b018f02be87fd62e641dd7e59d1b7dbaf3567acb07562872dd006 |

## Commands and results

From `/Users/lauritz/Programming/SpesPed/var/review-guardian-ui/pin/web`:

```sh
npm test -- src/features/guardian/GuardianPortal.test.tsx src/api.test.ts src/App.test.tsx src/App.workspaces.test.tsx
npm run typecheck
npm run build
```

The focused candidate suite passed **35 tests in four files**. Typecheck and production build passed. Logs: `candidate-tests.log`, `typecheck.log`, `build.log` under `var/review-guardian-ui`.

From `/Users/lauritz/Programming/SpesPed/var/review-guardian-ui`:

```sh
./node_modules/.bin/vitest run --config vitest.config.ts
```

Independent result: **1 failed, 2 passed**. Failure is the finding above. Passing probes verify that closing a letter discards an outstanding attachment response before any blob URL is created, and that Nynorsk controls work with a download filename stripped of path/control characters plus eventual object URL revocation. Evidence: `guardian-adverse.test.tsx`, `vitest.config.ts`, `adverse-tests.log`.

Only this report and ignored `var/review-guardian-ui/**` were written. Product code, shared tests, dependencies, servers, database schemas and commits were not changed. Synthetic content only. The orchestrator's independent PostgreSQL/browser harness is separate and not claimed by this report.

## Guardian UI R1 recheck — c6e0ad87bc6c403e331a7e2408c51b8e4dd30ea6

The original **P2 withdrawal finding is resolved** at this exact repair. Overall bounded verdict remains **changes requested** for the new P3 locale finding below. Full F21/J21/J25 and deployment acceptance remain outside this review.

Fresh archive: `var/review-guardian-ui/repair-pin`, created with `git archive c6e0ad87bc6c403e331a7e2408c51b8e4dd30ea6`. Frozen web dependencies remain symlinked to installed dependencies. All eight reviewed archive files match their exact Git blobs; `repair-hash-proof.json` records the eight SHA-256 hashes and comparison with the original candidate. All four guardian-file hashes also match the author's `var/j21-guardian-ui/repair-hashes.json`. Changed guardian hashes:

- GuardianPortal.tsx: `55d21603dd933e43119670042ccfedafc251bfdf5933cf746136a1add607c72a`
- GuardianPortal.test.tsx: `a5d4da489b1390dd86d6fba10dd8f3b18e12d362f7a80f5f6d4bffb1915142bc`

The exact repair archive also includes intervening orchestrator document-tab integration in App.tsx (`2017a07c8500739a55698dd3ec38cd49939bd3e9dd97296b72fd9e390ff738c6`) and App.workspaces.test.tsx (`ecdd7c8af3fef82daf2207da365528a918ce2c2c41c0b2fec6dafc70831bbb6c`). Inspected these small composition deltas and reran the focused shell suite; this is not an independent acceptance of the separate document workspace implementation. API, API test, guardian CSS and types retain the original hashes.

`pendingGrantRef` tracks the opening grant even before a payload is selected, is cleared with the content, and is checked by successful same-page refreshes. Removal increments the operation scope; both late command and late payload completions are discarded. A genuine page change is distinguished from a same-page refresh.

Commands from repair-pin/web:

```sh
npm test -- src/features/guardian/GuardianPortal.test.tsx src/api.test.ts src/App.test.tsx src/App.workspaces.test.tsx
npm run typecheck
npm run build
```

Result: **36 tests passed in four files**, typecheck and build passed. Logs: `repair-candidate-tests.log`, `repair-typecheck.log`, `repair-build.log`.

From `var/review-guardian-ui`:

```sh
./node_modules/.bin/vitest run --config vitest.repair.config.ts
```

Result: **6 independent tests passed** (`repair-adverse-tests.log`). `guardian-repair-adverse.test.tsx` retains the original failed assertions unchanged except for importing repair-pin. The original withdrawal race now passes. Other passing probes cover close during an attachment request, sanitized download/object URL cleanup/Nynorsk controls, same-page focus refresh retaining a valid held payload, a genuine pagination change retaining a pending open, and refresh withdrawal while the open command itself is still pending (no payload request follows). Original failing pin and probe are preserved.

### New finding: Norwegian date fallback

**[P3] Supply a Norwegian fallback when Nynorsk date formatting is unsupported** — `web/src/features/guardian/GuardianPortal.tsx:19`.

The formatter requests scalar `nn-NO`. The bundled Chromium does not support that locale, so selecting Nynorsk renders received/expiry dates in default English 12-hour notation: `October 21, 2026 at 8:41 PM`, although labels are Nynorsk and `nb-NO` is supported. The actual native 390px guardian screenshot `var/document-guardian-browser/guardian-mobile.png` shows this defect. This is a language consistency defect, without an authorization or timestamp integrity issue. Supply ordered locale preferences such as `['nn-NO', 'nb-NO']` for Nynorsk and test the fallback when the primary locale is unsupported.

Independent reproduction launched a fresh bundled Chromium process with no app/server/database contact:

```sh
cd /Users/lauritz/Programming/SpesPed/var/review-guardian-ui
node locale-probe.mjs
```

Saved `locale-probe.json` shows `Intl.DateTimeFormat.supportedLocalesOf(['nn-NO'])` returns `[]`; the current formatter resolves `en-US` with `hourCycle: h12` and outputs the English value above. `nb-NO` is supported, resolves `nb` with `hourCycle: h23`, and outputs `21. oktober 2026 kl. 20:41` for the same instant and Europe/Oslo timezone. The fresh browser was closed in finally. Original author repair and narrow independent recheck remain required for P3.

The orchestrator separately supplied native PostgreSQL/browser evidence at `d15671bf89ce4f2e5d88388da5df7f9d4636a300`: keyboard open, authenticated attachment, explicit persisted read acknowledgment, mobile layout and reopen after reload. Those normal-flow results are not evidence at the later repair revision and do not replace the frozen repair tests here. No product/shared-test/dependency/server/database/commit edits were made by this review; only this report and ignored review evidence were written.

## Guardian UI R2 final recheck — f78ca34b40afb20c5d89809642980dcc38d6de54

Current bounded verdict: **accepted**. The original P2 withdrawal race remains resolved and the P3 Norwegian date fallback finding is now resolved. This supersedes the earlier changes-requested verdicts for this guardian portal boundary only. Practitioner disclosure composition, full F21/J21/J25, deployed identity/provider/operations configuration and whole-feature completion remain required separate work.

Created another exact `git archive f78ca34b40afb20c5d89809642980dcc38d6de54` at `var/review-guardian-ui/locale-pin`; its web/node_modules symlink uses installed dependencies. All eight reviewed web files match their exact Git blobs. Six retain their R1 hashes; the two locale repair hashes are:

- GuardianPortal.tsx: `ce769e7eaf0bb1d51815d44e01d60f84dbf7c88dd269aacd0a2a30520ccf3267`
- GuardianPortal.test.tsx: `a80a024c563b50cd51c07dc4a83c9cc88c18d6d3d30121bccbd80250a95d8e73`

All four guardian hashes match the author's `var/j21-guardian-ui/locale-hashes.json`. Machine-readable proof for all eight: `var/review-guardian-ui/locale-hash-proof.json`. Inspected the exact two-file repair: Nynorsk preferences are ordered nn-NO then nb-NO, supported locales are selected before constructing the date formatter, and the focused fallback test simulates absence of Nynorsk locale data.

From `/Users/lauritz/Programming/SpesPed/var/review-guardian-ui/locale-pin/web`:

```sh
npm test -- src/features/guardian/GuardianPortal.test.tsx src/api.test.ts src/App.test.tsx src/App.workspaces.test.tsx
npm run typecheck
npm run build
```

Result: **37 focused tests passed in four files**, explicit full web typecheck passed, production build passed. These are complete frozen-project commands, not isolated TypeScript assertions or checks of the mutable working tree. Logs: `locale-candidate-tests.log`, `locale-typecheck.log`, `locale-build.log`.

From `/Users/lauritz/Programming/SpesPed/var/review-guardian-ui`:

```sh
./node_modules/.bin/vitest run --config vitest.locale.config.ts
node locale-repair-browser.mjs
```

All **6 independent R1 regression probes passed** against locale-pin (`locale-adverse-tests.log`). The unchanged original withdrawal assertions, valid focus refresh, genuine pagination, withdrawal before the command resolves, late download cancellation and sanitized filename/object URL cleanup remain green.

The independent browser probe extracts the exact dateLabel function from the frozen GuardianPortal.tsx, removes TypeScript annotations using the installed TypeScript compiler, and evaluates that function in a newly launched real bundled Chromium process. It does not mock Intl or copy the author's expected formatting expression. `locale-repair-browser.json` records the frozen source path, matching SHA-256, complete extracted function and browser outputs: nn-NO unsupported; nb-NO supported; both Nynorsk and Bokmål formatting produce **21. oktober 2026 kl. 20:41** for `2026-10-21T18:41:00Z` in Europe/Oslo; invalid input remains blank. The original browser probe and its English output remain available for before/after comparison. The fresh browser closed in finally and contacted no application server or database.

No further actionable finding arose in this narrow final recheck. Only this review report and ignored review evidence were written; no product/shared-test/dependency/database/server/commit edits or real pupil data were introduced.

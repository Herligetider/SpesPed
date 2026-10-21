# J03 independent review and recheck

**Final disposition: ACCEPTED for the scoped J03 authenticated shell at
`a46aef1f6eeafdfcc661be02b72c2cf6e77091ff`.** All seven initial findings and the
additional live-browser native-fetch blocker were repaired and independently
verified. Real browser/API integration was performed against the isolated
PostgreSQL synthetic demo environment. Full F01/F02/F31 remain partial; this is
not production-readiness or a complete accessibility certification. Detailed final
evidence follows the retained initial review below.

Reviewed commit: `7f3d652a20af3465f65fd57cf86c96dd317582d1`.

Review scope: `web/**` and its integration with the currently available identity
HTTP contract. Read `AGENTS.md`, `docs/09-domain-implementation.en.md`, the relevant
F01/F02/F31 specifications, and the concurrent foundation's identity router,
authentication and settings code. The backend was not edited or started. Its
uncommitted implementation is a contract reference, not a reviewed J03 artifact.

**Initial disposition: changes required; actual API/browser integration acceptance gate
remains open.** Passing the checks below does not establish completion of F01,
F02 or F31.

## Findings

1. **P1 — Ignore profile responses from an obsolete learner/session context.**
   `web/src/App.tsx:101–110`: `openProfile` unconditionally applies its response.
   Open Alpha, go back while its request is pending, then open Beta. If Beta
   resolves first and Alpha resolves later, the selected Beta view displays
   Alpha's profile. The same outstanding request can survive school changes,
   logout, and a subsequent login and overwrite another user's current profile.
   Capture and validate a request generation plus user/school/learner identity
   before applying either success or error; invalidate outstanding work on every
   relevant transition. Reproduced using the real App in React/jsdom with deferred
   client promises: `PROFILE_RACE: REPRODUCED: late Alpha response replaced
   selected Beta profile`.

2. **P1 — Apply the school/session request guard to list retries.**
   `web/src/App.tsx:147–149`: retry starts its own request outside the guarded
   effect at lines 47–62. Start an s1 retry, select s2, let s2 load, then resolve
   the s1 retry. The selector says s2 while the list displays s1's learner names.
   This also permits a pending retry to restore a previous user's list after a
   logout/login. Route retry through the same context-bound loader or validate
   its generation before all state updates. Reproduced in React/jsdom:
   `RETRY_RACE: REPRODUCED: old s1 retry overwrote active s2 learner list`.

3. **P2 — Bind session-expiry responses to the authentication generation.**
   `web/src/api.ts:86–88`: any 401 clears the current CSRF token and expires the
   current app session, including a delayed response issued before another login
   succeeded. A deferred old learner request, successful new login, and then old
   401 reproducibly triggers the expiry handler and removes the new login's CSRF
   token. Ignore obsolete authentication responses; also guard restoration in
   `web/src/App.tsx:36–41` against completion after a newer auth transition or
   effect cleanup. This matters especially because `main.tsx` mounts StrictMode,
   which replays the restoration effect during development.

4. **P1 — Keep a school selector available on small screens.**
   `web/src/styles.css:4`: the `max-width:760px` rule sets
   `.sidebar>label,.sidebar>select{display:none}`. This hides the only school
   selector with no mobile replacement. Accounts with multiple schools initially
   select none (`App.tsx:38,79`) and cannot enter a school at phone width or a
   comparable zoomed viewport; users who selected a school on desktop cannot
   change it after narrowing the viewport either.
   Preserve an accessible selector in the responsive layout. Verified statically;
   a real viewport/zoom and keyboard check is still required.

5. **P2 — Make all authorized learner pages reachable.**
   `web/src/api.ts:58–59`, `web/src/App.tsx:56–57,147–149,178–184`: only one list
   request is made and `total` is discarded. The current backend defaults to
   `limit=50` (`identity/router.py:108–132`), so learner 51 onward is unavailable
   and the displayed count incorrectly appears to be the complete list. Add
   bounded pagination or an equivalent complete authorized search/list flow,
   retaining the server total and handling errors on subsequent pages.

6. **P2 — Increase contrast for small supporting text.**
   `web/src/styles.css:1–3`: `--muted:#707b74` gives approximately 4.06:1 against
   the page background `#f6f6f1` and 4.40:1 on white; `#77837a` gives 3.84:1 on
   the sidebar and 3.95:1 on white. These are small, normal-weight descriptions,
   pupil metadata and labels. Darken the text/background pairs and verify the
   rendered states, including the translucent header. Ratios were calculated from
   the declared sRGB colors; no screen-reader or visual-browser audit was run.

7. **P2 — Localize API errors through the selected language.**
   `web/src/api.ts:83,93–95`, `web/src/App.tsx:9,80–81`: errors render the backend
   message verbatim, while the current foundation returns English messages such
   as `The email or password is incorrect.` and `Sign in to continue.`. Network
   and fallback errors are fixed Bokmål even with Nynorsk selected. Map known
   safe API error codes to nb/nn messages and provide a localized fallback so the
   shell's language choice also applies to adverse paths. The skip-link text at
   `App.tsx:118` is likewise fixed Bokmål.

## Commands and verification

Run from `/Users/lauritz/Programming/SpesPed/web`:

- `npm test` — PASS: 2 files, 5 tests.
- `npm run typecheck` — PASS.
- `npm run build` — PASS; Vite 7.3.7, 31 modules transformed.
- `node --input-type=module` with an inline, in-memory TypeScript-transpiled App,
  jsdom, React `act`, and deferred synthetic client promises — PASS as a defect
  reproduction: both profile and list retry races above reproduced. No test or
  implementation files were added by the reviewer.
- A second `node --input-type=module` inline harness imported the transpiled real
  ApiClient, deferred an old learner response, completed a new login, then
  returned the old 401 — defect reproduced: expiry callback fired and the next
  write had no CSRF token (`AUTH_RACE: REPRODUCED`).
- An inline Python sRGB relative-luminance calculation produced the contrast
  ratios in finding 6.
- `git diff <reviewed commit> -- web` was empty when review started; no web
  implementation changes were made during review.

Existing tests are two mock-client App tests and three fake-fetch ApiClient
tests. The test named “supports keyboard sign in” types into controls but clicks
buttons with `user.click`; it does not establish tab order, keyboard-only
navigation, focus transfer or skip-link behavior. There are no existing tests
for concurrent responses, multiple schools/users, pagination, responsive school
selection, Nynorsk errors, actual cookie/Origin/CSRF behavior or backend access
restrictions. The added review probes establish the reported defects, not live
integration correctness.

## Static contract observations and pending acceptance gates

The client uses the agreed same-origin `/api/v1` paths, includes credentials,
retains CSRF only in memory, and sends `X-CSRF-Token` on logout. The Vite dev proxy
targets `localhost:8000`. Login correctly relies on the browser-generated Origin;
the client should not attempt to forge that browser-controlled header. The
backend's default exact allowed origin includes `http://localhost:5173`; a Vite
fallback port, different hostname or deployment origin requires explicit matching
configuration. None of these observations verifies a working browser session.

Before J03 acceptance, after repairs and J01 availability:

- Run the actual React client in a browser against the real API with synthetic
  accounts. Verify invalid login, successful login, HttpOnly cookie handling,
  refresh/restoration, logout, revocation, expired session, missing/wrong CSRF and
  disallowed Origin. Record the exact frontend origin and backend configuration.
- Exercise two schools and two users with delayed/out-of-order success and error
  responses, including restoration and late 401s. Confirm no previous-context
  learner names or profile content reappears.
- Verify authorized lists/profiles and denied access for an unrelated teacher,
  technical administrator, expired assignment and restricted assistant. The
  current UI makes no role-based bypass, but mock tests cannot prove server scope
  enforcement or restrictions on profile fields.
- Verify more than 50 authorized learners, pagination/retry recovery, empty
  membership/list states and backend/network errors in both languages.
- Perform keyboard-only and assistive-technology checks for login, school choice,
  list/profile/back/retry/logout and language controls, including focus after
  navigation, 320px/760px layouts and zoom, after contrast fixes.
- The current identity detail endpoint returns only the basic learner fields.
  Optional pedagogical fields in `LearnerProfile` and their mocked test values do
  not establish a working sourced pedagogical profile or F02 completion. Keep
  unavailable detail distinct from confirmed absence as that integration lands.

At the initial review, only `docs/reviews/J03-review.md` was added. Concurrent
backend and orchestrator changes in the shared checkout were left untouched.

## Independent repair recheck and live integration — 21 October 2026

Final reviewed web candidate:
`a46aef1f6eeafdfcc661be02b72c2cf6e77091ff`, including initial candidate
`7f3d652a20af3465f65fd57cf86c96dd317582d1`, fixes `afa7247`, explicit loopback
proxy `9ac02a2`, native-fetch repair `b8ccfa2`, and final mobile CSS `a46aef1`.
The final command
`git diff --exit-code a46aef1f6eeafdfcc661be02b72c2cf6e77091ff -- web`
ran from the repository root and passed with no output. Concurrent unrelated
domain/backend work is excluded from this review's candidate equality.

### Resolution of the seven original findings

1. **Resolved:** `App.tsx:135–161` increments and checks profile generations for
   open/back/school/auth transitions. The original independent in-memory
   reproducer now keeps Beta after late Alpha success. Chromium checks held an
   actual authorized profile response, selected another pupil, then released the
   earlier response: the selected profile remained correct. A second real
   response approved under the leader's session was held through logout and a
   different teacher login/profile open; it did not overwrite that teacher's
   profile. The repaired suite also covers rejected stale profile requests.
2. **Resolved:** retry now changes `listReload` and runs through the same guarded
   effect (`App.tsx:73–89,198`). Both the original independent deferred-promise
   reproducer and Chromium passed. The browser check injected one connection
   reset, retried against the real school-one endpoint, delayed its real response,
   switched to school two, then released it. School two retained its correct
   empty authorized list. Automated regressions cover a retry resolving after a
   different-user login as well.
3. **Resolved:** `api.ts:19,31–56,76,94–98` binds requests and token updates to an
   authentication generation; restoration also checks effect lifetime and app
   generation (`App.tsx:40–71`). In Chromium, an old learner request retained its
   original cookie and was delayed until a new login rotated/revoked that session.
   The real backend returned 401 for the old cookie; the newer client login was
   not expired, and its retained CSRF token completed a successful logout. Actual
   UI refresh/restoration and externally revoked-session recovery also passed.
4. **Resolved:** the school selector is visible and usable at both 320px and
   760px. The synthetic teacher now has two memberships and could select each;
   school one showed only the assigned pupil and school two correctly showed an
   empty list. Final CSS additionally fixes stretched mobile rows and language
   control placement. At 320px the sidebar measures 244px high; the language label
   precedes its select, then logout, and school → language → logout is the actual
   keyboard tab order. No horizontal page overflow occurred, including the
   52-learner paginated leader view at 320px.
5. **Resolved:** `api.ts:64–66` sends bounded offset/limit parameters; the UI keeps
   the server total and provides previous/next controls (`App.tsx:228–240`). The
   real leader list with 52 pupils rendered 50 on page one and two on page two,
   with correct totals and disabled next on the last page. The final pupil's real
   detail opened; back retained page two; previous returned to page one. Enter
   activated next. Paging also passed after the final CSS change at 320px.
6. **Resolved:** final computed browser colors are muted `#536057` and eyebrow
   `#4f5d53`. Measured contrast is 6.09:1 for muted text against the page, 6.61:1
   against white, and 6.70:1 for eyebrow text against the composited translucent
   header. The reviewer inspected the final 320px screenshot; controls and learner
   content remain legible and usable. The orchestrator independently inspected
   the desktop/mobile screenshots and requested the final mobile CSS refinement.
7. **Resolved for the current API contract:** known safe codes map to nb/nn
   messages and the skip link is translated. Actual invalid-credential responses
   showed `E-postadressen eller passordet er feil.` in Bokmål and
   `E-postadressa eller passordet er feil.` in Nynorsk. A real offline browser
   login attempt showed the Nynorsk network message. The document `lang` became
   `nn`. A real revoked-session response showed the localized re-login notice.
   Future endpoint codes still require language entries as those modules land.

### Additional integration defects found and repaired

- **Resolved P1 native browser transport blocker:** at `9ac02a2`, `api.ts` stored
  raw browser `fetch` and called it as `this.fetcher(...)`. Chromium threw
  `Failed to execute 'fetch' on 'Window': Illegal invocation` before sending any
  request, while all 15 mocked tests passed. Independently confirmed that the
  default client returned `NETWORK_ERROR`/0 whereas a correctly bound client
  reached the API and received 401. `b8ccfa2` wraps `globalThis.fetch` with the
  correct receiver and adds a default-transport regression. Actual UI login,
  restoration, reads and logout now work with the default client.
- **Resolved development proxy ambiguity:** the orchestrator found that
  `localhost:8000` reached an unrelated IPv6 listener on this host. `9ac02a2`
  explicitly targets `127.0.0.1:8000`. The reviewer independently confirmed
  `/api/v1/health` through `http://localhost:5173` returns 200/`{status:'ok'}` and
  used that proxy for all subsequent UI checks.

### Exact verification environment and checks

The frontend was `http://localhost:5173`, proxying to the local FastAPI service at
`127.0.0.1:8000`. The environment file was read programmatically without printing
its secrets; its permission mode was confirmed as 0600. Before writing fixtures,
the configured DSN was checked to name `spesped_demo`, separate from the test
database. No real data or external messages were used. With explicit assignment
authorization, the reviewer created 50 additional synthetic pupils through the
real API and one teacher membership in the other synthetic school. There are now
52 pupils in the primary demo school. The extra membership grants no pupil read
rights. These review fixtures remain in the isolated demo database.

Final commands from `web/`:

- `npm test` — PASS, 2 files / **16 tests**.
- `npm run typecheck` — PASS.
- `npm run build` — PASS, 31 modules transformed.

Independent ephemeral Node here-doc harnesses used the installed Playwright at
`/Users/lauritz/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright`
and explicit cached Chromium headless shell 1248, reporting Chromium
`156.0.8078.4`. The default Playwright executable lookup initially failed because
its expected revision was absent; selecting the already installed revision
resolved the harness setup. No dependency/lockfile changes were made. Native
select typeahead was used for the actual keyboard school-choice check because
this macOS headless shell did not commit ArrowDown popup selection.

The following actual API/browser checks passed:

- Real browser-generated login Origin was exactly `http://localhost:5173`.
  Login without Origin was rejected 403. Logout without CSRF, with wrong CSRF,
  and with valid CSRF but disallowed Origin was rejected 403, preserving the
  legitimate session. The actual browser logout request carried CSRF, returned
  204, and subsequent `/auth/me` returned 401. Cookie properties were
  HttpOnly/SameSite=Lax/path `/api`; Secure is intentionally disabled in this
  local HTTP development environment.
- Teacher list/detail for its assigned pupil returned 200; unrelated detail and
  access to the other school before the extra membership returned 403.
  Assistant, technical administrator and guardian each received an empty learner
  list and 403 for direct pupil detail. These checks use the actual backend and
  cookie sessions, not caller-provided role headers.
- Keyboard-only teacher login (initial email focus, Tab, password, Tab, Enter),
  school choice via native typeahead, pupil activation, back and logout passed.
  Browser accessible role/name snapshots exposed the school combobox, main
  landmark and buttons. Both viewport sizes and the final mobile control tab
  order were checked. No page exceptions occurred in the main browser flow.
- Refresh restored the real cookie session and authorized pupil list. Revoking
  the same session through the real API, then changing school in the still-open
  page, returned the UI to login with an expiry notice and no learner rows.
- Real login/error/offline, 52-pupil pagination, two-school switching, and delayed
  actual response checks passed as detailed above. The connection-reset probe
  was explicitly injected browser transport failure; subsequent delayed list and
  profile bodies were fetched from the real API. The old-session 401 was also a
  genuine backend rejection.
- Optional pedagogical fields remain unavailable from the current identity
  endpoint. The profile now explicitly says they are not shown yet rather than
  claiming confirmed absence. No sourced F02 pedagogical profile is claimed.

Final synthetic screenshots, refreshed after `a46aef1`, are ignored local files:

- `var/review-j03/desktop-1280.png`
- `var/review-j03/mobile-320.png`

### Acceptance boundary

There are no remaining actionable findings in this reviewed J03 scope. The real
browser/API acceptance gate is now met for this private, synthetic development
environment. This acceptance does not cover full F01 school/user/authority
administration, full F02 pedagogical and guardian workflows, full F31 document
accessibility/translation workflows, production deployment/TLS/cookie settings,
or a human VoiceOver/NVDA session. The reviewer checked browser accessibility
roles and real keyboard use, which is narrower than assistive-technology
certification. Assignment expiry and deeper foundation enforcement belong to the
separate backend review, not a claim inferred from these shell checks.

The reviewer changed only this review document, created the explicitly requested
ignored screenshots, and exercised authorized synthetic demo fixtures. No
implementation, lockfile, other documentation or unrelated working changes were
edited or committed by the reviewer.

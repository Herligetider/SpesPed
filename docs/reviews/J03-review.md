# J03 independent review

Reviewed commit: `7f3d652a20af3465f65fd57cf86c96dd317582d1`.

Review scope: `web/**` and its integration with the currently available identity
HTTP contract. Read `AGENTS.md`, `docs/09-domain-implementation.en.md`, the relevant
F01/F02/F31 specifications, and the concurrent foundation's identity router,
authentication and settings code. The backend was not edited or started. Its
uncommitted implementation is a contract reference, not a reviewed J03 artifact.

**Disposition: changes required; actual API/browser integration acceptance gate
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

Only `docs/reviews/J03-review.md` was added by this review. Concurrent backend and
orchestrator changes in the shared checkout were left untouched.

# Main integration checkpoint

21 October 2026. The user requested pushing all current project work and merging
it into `main`. This integrates a development application; it does not declare
all 40 features complete or authorize a production deployment.

## Final recovery delta

Implementation revision: `487fe316e6c9235e203bd10968e0dafb055fe517`.
The independent [final recovery review](document-recovery-final-review.md)
accepts both bounded changes and pins every source hash. It records 60 native
backend passes (30 SQLite and 30 PostgreSQL), 31 component/App passes and four
additional adverse component passes. Earlier editor, gap and rebuild residuals
are closed. Existing feature and production release gates remain in effect.

## Root verification

- Full web suite: **172 tests passed across 12 files** (`npm test -- --run`).
- `npm run typecheck` and `npm run build` passed. The existing bundle-size advisory
  remains: the JavaScript chunk is about 515 kB before gzip.
- Native same-origin Chromium journey passed against the actual application on
  an isolated PostgreSQL schema: selected-interval guardian draft creation,
  manual revision preserving gap explanations, exact review and approval with
  no dispatch, persisted approved revision reopened after a new login, and
  explicit approval recall. No JavaScript page errors were observed.
- Browser source was Git archive `b8a7a71` plus the seven exact frozen files,
  confirmed identical to the implementation revision above. Static assets came
  from the tested current production build. Evidence is retained locally under
  `var/document-guardian-final/`, including source hashes and native responses.
- The first browser script reached approval but its exact label selector timed
  out at recall. The existing accessible textbox-role selector succeeded on a
  fresh login and the persisted document. Both attempts are retained; this is a
  harness limitation, not a claim that the first script completed.
- The owned browser server exited with code 0 and its exact temporary PostgreSQL
  schema was confirmed absent after fixture cleanup. Other development servers
  and databases were not removed.
- [Local setup instructions](../11-local-development.no.md) were checked with a
  new private `.env`, fresh SQLite migration, synthetic seed and successful login
  from the documented origin. The two Python blocks also passed syntax checks.
- Traceability and deterministic documentation rendering preserve 40 features,
  86 acceptance examples, 28 jobs, 90 requirements and 71 sources. No feature
  completion was inferred from those structural checks.

The earlier full backend run at `91558b2` remains separately documented in
[its baseline report](backend-integration-91558b2.md): 1,138 passed, 26 skipped and
90 subtests passed. It is not represented as a full-suite run on this new revision.
The focused final recovery review covers the later pending delta.

## Local execution and Git scope

The inspected host identifies itself as **Lauritz’s Mac mini**, model `Mac16,10`.
Its checkout is `/Users/lauritz/Programming/SpesPed`. Starting a server there does
not serve the MacBook Air's loopback address. The new setup guide explains how
to fetch `main`, install locked dependencies and run both services on the Air.

Only source, tests and documentation are committed. `.env`, local credentials,
databases, `var/`, installed dependencies and build output remain ignored.
The minimal CLI demo provides explicit basic authorities; extra synthetic
workflows or authorities created on the development host are not transported
through Git. Configured AI, scanning, integrations and production operations
still require their separately documented setup.

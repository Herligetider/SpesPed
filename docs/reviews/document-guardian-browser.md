# Native document and guardian browser checkpoint

Revision: `d15671bf89ce4f2e5d88388da5df7f9d4636a300`.
Date: 21 October 2026. Orchestrator verification, separate from the independent
document and guardian reviews. This is partial workflow evidence, not feature
completion or a production deployment check.

The root extracted the exact revision, built its web client with the installed
locked dependencies, and ran Chromium against its native `create_app` and an
isolated PostgreSQL schema. Fixture setup supplied synthetic users, explicit
assignments and original document bytes. The application used its native source,
authority, document-history and portal adapters; fixture substitute authority
adapters were not copied into the serving application. A synthetic approved
letter and disclosure package were prepared through the native HTTP endpoints.
No external messages or real pupil data were used.

## Observed results

- Guardian login requested no learner list or dossier. Keyboard activation opened
  the exact approved letter through the session-bound grant.
- The authenticated attachment download contained the expected synthetic text.
  Explicit read acknowledgement succeeded separately from opening the letter.
- The saved grant reopened after a browser reload. The Nynorsk controls remained
  usable at 390 pixels without horizontal overflow; the page had one main
  landmark. Visual inspection subsequently identified English date fallback in
  Chromium, independently reproduced and tracked in the guardian review.
- A teacher created a guardian email draft for 1–21 October, including both dates,
  through the native endpoint (201). The stored period used Europe/Oslo boundaries,
  and the stored dispatch state was `not_requested` with automatic sending false.
  The absence of confirmed observations remained an explicit evidence gap.
- The automatically selected existing document showed an empty subject editor
  despite its saved subject. Selecting the document explicitly and attempting a
  manual revision returned 422 for missing `body.document.request_key`. These
  confirm findings 1 and 2 in the independent document UI review. Revision,
  missing-evidence handling and approval require a fresh browser run after repair.

The initial native server harness required a Python multiprocessing entry guard;
that harness correction is not a product change. Browser creation selectors were
also corrected before the successful 201 run. There were no browser JavaScript
errors in the recorded guardian/revision journey.

## Reproducible local evidence

The ignored `var/document-guardian-browser/` directory contains the frozen source
revision, `build.log`, native `server.py`, `imports.json`, owned `schema.txt`,
`browser.mjs`, `evidence.json`, `create.mjs`, `create-evidence.json`, and screenshots.
The serving process uses port 18970 and owns only its generated schema; teardown
must target that exact process/schema and preserve other agents' servers.

Commands: `npm --prefix var/document-guardian-browser/pin/web run build`,
`node var/document-guardian-browser/browser.mjs`, and
`node var/document-guardian-browser/create.mjs`. The server uses absolute frozen
`backend` and `backend/tests` paths in `PYTHONPATH` with the repository Python 3.12
environment, avoiding live editable-package imports.

This checkpoint does not exercise practitioner disclosure screens, external
delivery connectors, arbitrary uploaded attachments, PDF rendering, a deployed
worker, complete accessibility, or production legal/model configuration.

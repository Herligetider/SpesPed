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
The first harness used port 18970 and owned only its generated schema. Cleanup
must target its exact process/schema and preserve other agents' servers.

Commands: `npm --prefix var/document-guardian-browser/pin/web run build`,
`node var/document-guardian-browser/browser.mjs`, and
`node var/document-guardian-browser/create.mjs`. The server uses absolute frozen
`backend` and `backend/tests` paths in `PYTHONPATH` with the repository Python 3.12
environment, avoiding live editable-package imports.

This checkpoint does not exercise practitioner disclosure screens, external
delivery connectors, arbitrary uploaded attachments, PDF rendering, a deployed
worker, complete accessibility, or production legal/model configuration.

## Document repair checkpoint

Root repeated native browser verification at
`d00c118665e6d9acaf1a94c2d173328b1bb3ca31` in a second isolated PostgreSQL schema,
serving the exact archived build on port 18971. Evidence and scripts are in
`var/document-guardian-repair/`; this instance also includes two synthetic,
confirmed evidence records created through the native intake workflow.

The first run confirmed correct initial editor hydration and creation/editing
separation. It then reproduced lost gap explanations: a teacher filled an
explanation before the template inventory finished, but the submitted revision
stored an empty `handled_gaps` object. The response was 201, so schema acceptance
alone did not establish correct behavior. That failure is preserved in
`initial-repair-evidence.json` and independently reproduced by the UI reviewer.

A second run deliberately waited for inventory loading to settle before typing.
It successfully created a chosen-interval guardian draft, saved a manual revision
with explicit gap explanations, reviewed and approved the exact revision, and
retained `not_requested` dispatch with automatic sending false. A new browser login
reopened that persisted document and explicitly recalled its content approval.
The recall used a corrected accessible-role selector after the initial exact-label
selector could not match the populated reason field. Native request/response
bodies and terminal steps are preserved in `evidence.json`; `browser.mjs` and
`recall.mjs` reproduce the sequence. There were no browser JavaScript errors.

Waiting before typing is a verification limitation, not an acceptable product
requirement. The independent recheck still requires fixes for asynchronous editor
overwrites, document-specific rebuild state, empty-basis recovery and obsolete
typed/AI bindings. Those repairs and the narrow recovery metadata read are assigned
separately. This checkpoint does not close those findings or accept the whole
document workflow.

Both root harnesses were subsequently stopped with SIGINT. Their fixture finalizers
completed with exit code 0, and read-only PostgreSQL checks confirmed both exact
owned schemas were absent. Each evidence directory contains `cleanup.json`; other
servers and schemas were preserved.

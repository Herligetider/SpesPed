# Independent final review: document recovery metadata and UI repair

21 October 2026. Reviewer: independent `review_plan_offset` worker, author of neither implementation job.

**Backend recovery metadata: accepted for the bounded development change. UI recovery repair: accepted for the bounded development change. No actionable findings remain in these deltas.** This is a recommendation to integrate the reviewed development work; it does not establish production readiness, complete F18/F20/J20/J21, or complete all 40 features.

## Frozen candidate

Reviewed full source at `b8a7a719e77092e14e1d3d121a1e17ec43f25a5c` plus the seven assigned working changes. Extracted HEAD with Git archive into `var/review-document-recovery-final/archive`, then copied only the frozen candidate paths into that archive. Every entry matched the author manifests before execution and was rechecked against both the live candidate and archive afterward. CSS is an unchanged control file. No implementation, dependency or shared-contract edits were made by this reviewer.

| Path | SHA-256 |
| --- | --- |
| `backend/spesped/contexts/documents/choices.py` | `2acaf3267acb8ae6572c4e51bd301995055f071533bf4a753b9ad687f2c2df15` |
| `backend/spesped/contexts/documents/router.py` | `278a7ad3a6fed2e4e777459c1f23a9a620ae4f3da4286c290d523b3f6c117522` |
| `backend/spesped/contexts/documents/service.py` | `ab4154e47040df1ecdaeede91668bd382cf53235f7902505af0a956a4ee917f3` |
| `backend/tests/test_document_recovery_metadata.py` | `8bb6b7ffabe0284b0a239dcaed7adba3cc2af50d5cd4a8c2222fed397708da1b` |
| `web/src/features/documents/DocumentWorkspace.tsx` | `3f652fd60e2daad994e221f62ea2ffd3f2d1bada07ff2bb3e5a2bfa9f03c43f1` |
| `web/src/features/documents/DocumentWorkspace.test.tsx` | `ea6a35c6265cea45f705f388a418f83b7696a456203ef7f9e065dc2496846ce4` |
| `web/src/features/documents/types.ts` | `8b65a09593cbb95f1b6cade5558832d51fea5e9fbd712d137ad37a8271392286` |
| `web/src/features/documents/documents.css` (unchanged) | `ec657c300139e0e1137fef66438acb6e76ce07eca103df3d37959fa8260e21ce` |

The two source manifests are `var/j11-documents/owned-recovery-metadata-hashes.json` and `var/j20-document-recovery/frozen-hashes.json`. Read AGENTS.md, docs/10-master-plan.en.md, the prior `document-ui-review.md`, both author evidence handoffs, and the owning authorization, transaction, revision, generation and source-projection code.

## Backend decision

The new native GET `/documents/cases/{identity}/recovery` requires current school/pupil `documents.write` access. Reader, approver or contributor access does not substitute. Wrong school, wrong pupil, missing document and revoked cached assignment cases deny access. An authorized writer can obtain structural edit coordinates without acquiring source reading or AI processing rights.

The typed response is limited to document/pupil/kind/state, current version/revision/digest, section keys and generated-field keys. It does not return prior prose, subject, labels, source excerpts/references, configuration, job/basis IDs, reasons or approval records. Model/source recall still withholds old document content, snapshot and lineage. Fresh application route registration works without fixture-only source/model adapters.

The endpoint uses the existing isolated owning-reader contract. Pending staged dependency edits are rejected without flushing or overwriting them; a flushed caller transaction remains open without commit/rollback/flush side effects. Fresh reader identities observe current revision and authority while preserving the caller's cached identities. Native revision commands retain exact version and changed-field severing checks; metadata itself authorizes neither approval nor dispatch.

## Earlier UI residuals

The residuals in `docs/reviews/document-ui-review.md` are closed within the repaired scope:

- **8, late template completion:** editor hydration depends on the selected exact revision/source coordinate. Later successful or failed template inventory responses no longer reset dirty prose, reason or snapshot/section gap explanations. Both ordinary and guardian variants pass.
- **9, rebuild leaking across selection:** rebuild state is tied to one document/revision/source coordinate. Hydration suppresses stale content even if a review-required response contains it. Switching A to B does not expose B's old subject/prose. Late AI diff responses after withholding are discarded. A separate reviewer probe confirms late A recovery metadata cannot replace B's recovery coordinates or fields.
- **10, empty basis:** a writer can save an honest empty-basis draft after recall. Native execution creates a new snapshot with its actual missing-observation gap; a later human explanation permits exact review/approval without inventing evidence or sending anything.
- **11, stale typed dependencies:** rebuild clears old interval/background refs, citations, goals, actual delivery, future plans and discovery flags. Fresh typed inventories remain distinct. Required owner/guardian inventory failures prevent rebuilding; optional denied goal/teaching inventories are visibly unavailable and leave an empty basis. The reviewer separately tested both required-denial cases.
- **12, independent replacement/provenance:** recovery metadata must match document ID, revision ID, version and digest. Each unavailable generated field requires explicit independent-authoring selection and new nonempty text. The outgoing command severs only those selected fields. Native unchanged-field severing returns 422; successful changed replacements after both model and source recall restore readable new content while old history stays withheld. A normal readable unchanged revision preserves provenance. A reviewer unknown-result retry probe confirms identical outer/nested request keys, replacement selections and text are retained.

The earlier fixes for native nested request keys, separate creation/editor state, denied-refresh clearing, period selection invalidation, gap explanations and contribution request races remain covered by the frozen component/App and native regression checks. No send operation was introduced.

## Independent execution

Executed against the frozen archive, using Python 3.12.13 and the assigned synthetic PostgreSQL database. PostgreSQL fixtures use isolated UUID schemas and their own cleanup. Absolute archive `backend:backend/tests` PYTHONPATH entries prevent editable-checkout imports. Installed web node_modules was symlinked; candidate source was not modified. Reviewer probe code lives only under the ignored review archive.

| Check | Result | Evidence under `var/review-document-recovery-final/` |
| --- | --- | --- |
| Metadata, authorization, choices and native application-composition suites | 54 passed | `backend.txt`, `backend.xml` |
| Component-captured command replay through native HTTP, including source/model recall, unchanged sever rejection, honest gaps, exact approval and immutable old history | 6 passed | Same backend log/XML; `test_native_ui_commands.py`, `ui-commands.jsonl`, `native-*.json` |
| Combined native backend execution | **60 passed: 30 SQLite, 30 actual PostgreSQL; no skips/failures** | `backend.xml` |
| Frozen document component and App workspace suites | **31 passed**, 2 files | `ui.txt` |
| Reviewer-only late metadata, owner denial, guardian denial and exact replacement retry probes | **4 passed**; 27 copied original cases deliberately deselected | `reviewer-ui.txt`, archive `DocumentWorkspace.review-final.test.tsx` |
| Candidate whitespace check and manifest hash rechecks | Passed | `git diff --check`; hashes listed above |

The native replay test and captured command inputs were copied into the reviewer evidence directory before final execution so their output files do not overwrite author evidence. Existing schema/dependency/OpenAPI warnings are recorded in the backend log; none were test failures.

Reproduction environment (repository root `/Users/lauritz/Programming/SpesPed`):

```sh
export SPESPED_TEST_POSTGRES_URL='postgresql+psycopg://spesped_test:synthetic-development-only@127.0.0.1:55432/spesped_test'
export PYTHONPATH='/Users/lauritz/Programming/SpesPed/var/review-document-recovery-final/archive/backend:/Users/lauritz/Programming/SpesPed/var/review-document-recovery-final/archive/backend/tests'
# cwd: var/review-document-recovery-final/archive
/Users/lauritz/Programming/SpesPed/backend/.venv/bin/python -m pytest \
  backend/tests/test_document_recovery_metadata.py \
  backend/tests/test_documents_authorization.py backend/tests/test_document_choices.py \
  backend/tests/test_bc10_application_composition.py \
  /Users/lauritz/Programming/SpesPed/var/review-document-recovery-final/test_native_ui_commands.py \
  -q --junitxml=/Users/lauritz/Programming/SpesPed/var/review-document-recovery-final/backend.xml
# cwd: var/review-document-recovery-final/archive/web
npm test -- --run src/features/documents/DocumentWorkspace.test.tsx src/App.workspaces.test.tsx
npm test -- --run src/features/documents/DocumentWorkspace.review-final.test.tsx -t 'reviewer:'
```

## Integration boundary

Accept both bounded frozen jobs for integration with the hashes above. Root separately reports all 172 web tests, typecheck and production build passing, with the existing bundle-size advisory; those are root-owned results. Root also completed the same-origin Chromium/native PostgreSQL journey at `var/document-guardian-final`. I inspected its evidence: `completed:true`, no recorded errors, all seven source hashes matching, and the create/edit/gap explanation/exact approval/no-dispatch/fresh-login recall steps recorded. Its original reason-label selector timeout is documented; recall completed through an accessible textbox selector after fresh login. This review independently executes native HTTP and component behavior, including their captured-command bridge; the browser execution itself remains root-owned.

Configured production infrastructure, complete legal/operational gates, full accessibility/language verification and all-feature completion remain separate work. This review does not authorize external communications or production deployment. The new local development guide and README link are outside these seven implementation deltas and remain root-owned verification scope.

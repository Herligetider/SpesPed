# Durable proposal recovery UI — independent review

Exact candidate: `79158a84a59fa047f10a58e6e55fd53088b18ea0`. Independent reviewer: `review_j05`. **Changes required: REC-UI-R1/P1 and REC-UI-R2/P2. No acceptance until an independent repair recheck.** The separately accepted native source-projection review is not part of this verdict.

## Scope and isolation

Reviewed the eight commit files: shared recovery hook/types/list/status controls, IEP and teaching integrations, the one-line manual-editor gate and associated tests. The backend owner-bound recovery port at `c18a0e0` has its own accepted review; the browser runs here use the full archived backend at this UI pin. The separate teaching 004e19f review is not duplicated. This verdict does not imply full J07/Fxx completion.

Created `var/review-recovery-ui/pinned` by exact `git archive`; all eight candidate files remain byte-identical after testing. Only dependency packages are linked through the installed `node_modules`. Built the actual archived App and served that build through actual archived FastAPI with authenticated native sessions, CSRF and loopback synthetic model providers. Absolute `PYTHONPATH` pointed to this archive's `backend:backend/tests`; both normal and adverse `import-paths.json` files are asserted under the archive in `isolation-cleanup.log`. The author server/browser scripts were copied only as ignored test scaffolding, pointed to the new archive/own build and reviewer port 18898. No shared changing source was imported. Separate fresh unique PostgreSQL schemas were used for normal and adverse runs on the permitted 55432 test database; no demo database or unrelated schema was touched.

## REC-UI-R1 — P1: fresh recall metadata does not refute a delayed successful diff

Locations: `web/src/features/suggestions/useProposalRecovery.ts:160–221`, especially independent `page`/`verified` reads at 213–220 and the unconditional verified result at 211. Rendering sites: `web/src/features/teaching/Suggestions.tsx:160–192` and `web/src/features/planning/PlanSuggestions.tsx:402–416`.

The visible saved list and selected proposal are independently accepted for one refresh. A selected verification chain can resolve list(100) → job → diff before recall, while its last response remains delayed. If the separate list(50) query then returns fresh `review_required`, the hook does not use that contradiction to invalidate the selected chain. Releasing its old successful diff restores model prose and review controls even though the same UI already has fresh metadata saying the model/source is recalled.

Independent reproduction (`adverse/adverse-browser.mjs`): open a real succeeded teaching proposal; trigger its refresh; hold the list(50) request before sending it to the server; let list(100), job and diff execute successfully and hold the actual returned diff; revoke the actual teaching model release through the authenticated configuration endpoint; release list(50), which now returns `review_required`; finally release the previously computed diff response. No synthetic success payload is fabricated. Observed one visible “Synthetic AI visual support” and one visible selected-field review button after the fresh recall metadata. The screenshot also shows the recalled list rows beside the visible proposed text. The desired assertion expects zero visible recalled text and fails `1 !== 0`.

Evidence: `var/review-recovery-ui/adverse/recall-race-evidence.json`, `recall-race.log`, `recall-race.png` (visually inspected). This is a frontend display/authority-race defect, not evidence that the recalled backend emits new usable output or accepts an unauthorized review. Backend preflight remains a separate mutation gate.

Repair requirement: current owner metadata that positively refutes the exact selected job/basis/revision must invalidate prose and action projections and remain effective against older in-flight successful replies. Retain human draft state without displaying refuted source/model prose. Do not treat absence from an unrelated pagination page as proof that a selected job is unavailable.

## REC-UI-R2 — P2: recalled completed run remains stuck as an unknown outcome

Location: `web/src/features/suggestions/useProposalRecovery.ts:423–467`, especially metadata-only reconciliation restricted to `expire` at 428–436, and the `run` reconciliation requiring a non-recalled job GET at 438–451. Retry preservation at 332–335 keeps the unresolved operation afterward.

A fresh owner-list row can confirm that the exact run advanced from queued version 1 to succeeded version 3. If its model/source is recalled before reconciliation, the code appropriately avoids the prose-bearing job GET but then refuses to resolve the run's unknown status. Only lease expiry uses authoritative metadata directly. Retrying performs a fresh availability check and keeps the original attempt uncertain again. The user remains blocked by the pending-operation state and a message saying the outcome is unknown, although the durable metadata already confirms completed execution.

Independent reproduction (`adverse/unknown-recall-browser.mjs`): run a real queued IEP job, let the server commit completion and deliberately abort only the response; revoke the actual IEP model release; click “Avklar mot lagret status”. The owner endpoint returns `succeeded`, version 3 versus original 1, `review_required`. The UI nevertheless says the outcome remains unknown. Clicking the preserved original retry is refused by the fresh recall check and retains the uncertainty fieldset. There is exactly one run POST, so the probe does not claim duplicate model execution. The desired assertion expects the unknown fieldset to clear after reconciliation and fails `1 !== 0`.

Evidence: `adverse/unknown-recall-evidence.json`, `unknown-recall.log`, `unknown-recall.png`.

Repair requirement: reconcile registered execution state from fresh, exact owner-bound metadata when that state/version establishes a transition, while preserving uncertainty if it has not changed. Keep recalled prose hidden and do not issue a job-output GET or another run merely to clear the pending state. State the observed registered outcome without claiming that unrelated activity proves the original command's identity.

## Verification and limits

Commands against the frozen archive (`web` cwd for web tools; repository cwd for browser probes):

```
/opt/homebrew/bin/node node_modules/vitest/vitest.mjs run
/opt/homebrew/bin/node node_modules/typescript/bin/tsc -b --pretty false
/opt/homebrew/bin/node node_modules/vite/bin/vite.js build --outDir /Users/lauritz/Programming/SpesPed/var/review-recovery-ui/web-dist
/opt/homebrew/bin/node var/review-recovery-ui/normal-browser.mjs
/opt/homebrew/bin/node var/review-recovery-ui/adverse/adverse-browser.mjs
/opt/homebrew/bin/node var/review-recovery-ui/adverse/unknown-recall-browser.mjs
```

- **114 tests passed**, eight files, including 26 shared recovery cases (`unit.log`); typecheck and production build exit 0. Unit coverage includes pagination beyond 100, late owner/job replies, exact retries, manual IEP gating, reviewed/cancelled states, recalled lease expiry and unchanged-version uncertainty.
- The copied ten-workflow actual-App browser script independently ran to **exit 0** against this archive/backend (`browser-evidence.json`, `normal-browser.log`, `post-evidence.json`). It verifies reload/new login, saved succeeded/rejected jobs, lost committed run/review/create/cancel replies, exact one-attempt recovery, independent outcomes for sessions sharing a basis, manual teaching draft preservation after recall, early-expiry 409 messaging and lost committed expiry reconciliation with no recalled-job GET. Desktop/mobile evidence is retained; the browser checks 390px horizontal overflow and reports no page errors. These are copied regression workflows, distinct from the two new independent probes above. Real UI pagination beyond 100 is not claimed by that script; the independent backend review and component tests cover that boundary.
- Both new independent adverse probes complete with **exit 1** on the desired-behavior assertions above. Their normal successful responses are actual server responses; network routing only controls delay/loss. The ten normal scenarios and passing unit tests do not cover these two combinations.

All reviewer processes were awaited. The first fixture startup reached StaticFiles before the build directory existed and exited through normal teardown; its log/schema ID are preserved as `.initial`. The restarted normal and adverse services and loopback providers also shut down. The borrowed fixture driver closes a yielded generator, which did not execute its post-yield schema-removal code; the initial namespace assertion detected this scaffold cleanup gap. The reviewer then explicitly removed only the three exact schemas recorded by these runs. Subsequent direct namespace queries verify all three owned schemas are absent and reviewer listener 18898 is closed (`isolation-cleanup.log`). Ports 8000, 5173 and 18878 were untouched. Only this report and ignored scaffolding/evidence were written; no production edits, commits, pushes, agents, external AI/email or real pupil data were used. Full-feature, practitioner, legal and production-readiness claims remain outside this review.


## Independent repair recheck — b6093a3

Exact repaired candidate: `b6093a3cbbc9fbfc2ab4da928d9ef1517d8d56ed`. **REC-UI-R1/P1 and REC-UI-R2/P2 are closed on this pin. Bounded recovery-UI acceptance; no remaining actionable finding from this recheck.** The original report above remains unchanged historical evidence. Native source projections and the separately reviewed teaching work retain their separate verdicts.

Created a fresh exact archive at `var/review-recovery-ui/recheck/pinned`. Reviewed both changed files (`useProposalRecovery.ts`, `ProposalRecovery.test.tsx`) and the directly affected rendering/preflight/reconciliation paths. Actual App was built from this archive and served with its archived FastAPI backend, absolute archived `backend:backend/tests` PYTHONPATH, synthetic loopback models, and fresh unique PostgreSQL schemas on authorized 55432. Shared source-maintenance work was excluded. All actual module paths and both repaired file byte hashes are independently verified in `recheck/isolation-cleanup.log`.

Commands and actual results:

```
# cwd: recheck/pinned/web
/opt/homebrew/bin/node node_modules/vitest/vitest.mjs run
/opt/homebrew/bin/node node_modules/typescript/bin/tsc -b --pretty false
/opt/homebrew/bin/node node_modules/vite/bin/vite.js build --outDir /Users/lauritz/Programming/SpesPed/var/review-recovery-ui/recheck/web-dist
/opt/homebrew/bin/node node_modules/vitest/vitest.mjs run review-probes.test.tsx
# cwd: repository root
/opt/homebrew/bin/node var/review-recovery-ui/recheck/normal-browser.mjs
/opt/homebrew/bin/node var/review-recovery-ui/recheck/adverse/pagination-browser.mjs
/opt/homebrew/bin/node var/review-recovery-ui/recheck/adverse/adverse-browser.mjs
/opt/homebrew/bin/node var/review-recovery-ui/recheck/adverse/unknown-recall-browser.mjs
```

All commands completed with **exit 0** and were awaited. Full frozen web suite: **125 passed**, nine files (`unit.log`); typecheck and production build passed. The 125 count is the actual full pin, including adjacent already-reviewed tests; it is not a claim of re-reviewing that adjacent scope. A separate **26 independent branch cases passed** (`independent-unit.log`) for the two recovery consumers. The new ignored test file reuses synthetic test setup only, importing exact archived production components.

- **R1 original real reproduction now passes:** let real list(100)/job/diff finish before recall, delay the successful diff, revoke the actual model release, let the separate list(50) read return fresh `review_required`, then deliver the old diff. Result: **zero visible recalled prose, zero visible review buttons**. The probe preserves the original desired assertions. Evidence: `adverse/recall-race-evidence.json`, `recall-race.log`, `recall-race.png`.
- **R2 original real reproduction now passes:** let one run commit and abort only its reply, then actually recall the model. Reconciliation sees exact completed version **3 versus original 1**, clears uncertainty, performs **one run POST total** and **zero job-output GETs after recall**, and explicitly describes registered state without proving who caused the change. Evidence: `adverse/unknown-recall-evidence.json`, `unknown-recall.log`, `unknown-recall.png`. The original probe is preserved as `unknown-recall-browser.original.mjs`; synchronization was adapted to the corrected observed-state message and the now-absent retry control, while retaining the final desired no-uncertainty assertion.
- **Positive refutation and older replies:** the independent matrix tests both consumers with exact reviewed, cancelled, advanced-version, changed-basis and changed-owner-revision metadata while an older diff is held. Every branch suppresses the old prose/actions. A separately held older metadata reply also cannot override a later recall observation or trigger a job GET. A later complete, healthy metadata→job→diff verification after a temporary denial works, avoiding permanent rejection of valid content.
- **Changed versus unchanged outcomes:** for both consumers, advanced recalled `running`, `succeeded`, `failed`, `unavailable` and `cancelled` rows resolve to observed persisted status without output reads or another run. Unchanged and regressed versions keep uncertainty. The existing unchanged-failed-job, exact retry, current-scope and lease-expiry tests also pass.
- **Absence is not refutation:** a real saved-proposal list with **107 rows** reaches the third page; the selected first-page proposal remains visible and reviewable on unrelated second/third pages, with no create/run command. The extra 102 rows are explicitly synthetic older metadata fixture clones, not executed model jobs. Evidence: `adverse/pagination-evidence.json`, `pagination-seed.log`, `pagination.log`. The frozen component suite also tests this boundary for both consumers.
- **Regression workflows:** all ten original real-App flows pass again (`browser-evidence.json`, `normal-browser.log`, `post-evidence.json`), including reload/new login, explicit saved selection, unknown create distinction, lost run/review/cancel outcomes, session-specific reviews on shared bases, selected-field preservation, manual draft editing after recall, early lease-expiry 409 correction and lost committed expiry reconciliation without recalled-output reads. The full component suite preserves manual IEP gating and late scope/selection behavior. No automatic generation or application is inferred from opening a saved job.

Own services and loopback providers are stopped. The review fixture driver now resumes the base generator for its normal teardown instead of merely closing it; a direct PostgreSQL namespace read verifies that both uniquely recorded schemas are absent, and reviewer port 18898 is closed. Ports 8000/5173/18878 were untouched. Only this report append and ignored review scaffolding/evidence changed. No production edits, commits, pushes, subagents or external communications occurred. Acceptance remains limited to this assigned recovery-UI job; full J07/Fxx, practitioner usability, legal and production readiness remain outside the verdict.

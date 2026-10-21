# Independent protected-case rule projection review

- Reviewer: `/root/review_j16`, independent of the root implementer and the J16 implementer. No delegated review, implementation edits, commits or pushes.
- Candidate and exact execution pin: `30c656f624a32bb4512f4894388f46afcc2e521d`.
- Date: 21 October 2026.
- Scope: new `backend/spesped/contexts/governance/projections.py`, `backend/tests/test_protected_rule_context.py` and the corresponding `docs/09-domain-implementation.en.md` read-port contract, including their existing governance/identity/safeguarding authorization and source-version dependencies.
- Verdict: **bounded review accepted only. No actionable reproducible finding remained in the assigned read-port scope.** This does not accept a safeguarding adapter, production application composition, UI, legal approval or complete F24/F25/F26 delivery.

## Reviewed behavior

`case_requirements` requires valid UUID school/learner/case identifiers, exact governance case authority and the owning context's live case-to-learner resolver before returning even an empty set. Each recorded obligation must also pass its current owner/management detailed-access check. Inaccessible tasks are omitted without a hidden count, ID, digest or hidden-task-driven overall state. Assignment metadata alone does not expand case access.

The output keeps typed task state/version/applicability and unresolved inputs separate from source profile/rule identities, revisions/digests and source eligibility. It withholds generic required actions/documents when applicability or timing remains unresolved, a source is unreviewed/withdrawn/revoked/ineffective, or the obligation is not applicable. It preserves actual recorded deadlines and multiple real source profiles. It does not infer that a generic action is a notification, create an obligation, record performance or assert legal completeness. Empty or wholly inaccessible sets return unavailable with `coverage=authorized_recorded_obligations_only` and `legal_completeness=not_assessed`.

Source effectiveness is evaluated for the recorded trigger occurrence. A historical task can retain an effective historical source after that profile is superseded for later occurrences. `RuleBinding.state=current` expresses that source eligibility for the recorded obligation; it must not be presented as a claim that the profile is today's active school package or that all current duties have been inventoried. A source recall remains visible and removes actionable content without silently rewriting the task's recorded deadline or fulfillment state.

## Independent evidence

A fresh `git archive` extraction was used at `/Users/lauritz/Programming/SpesPed/var/review-j16/recheck-pinned`; no evolving shared source was reviewed or imported. Explicit import inspection returned:

```text
/Users/lauritz/Programming/SpesPed/var/review-j16/recheck-pinned/backend/spesped/__init__.py
/Users/lauritz/Programming/SpesPed/var/review-j16/recheck-pinned/backend/spesped/contexts/safeguarding/service.py
/Users/lauritz/Programming/SpesPed/var/review-j16/recheck-pinned/backend/spesped/contexts/governance/projections.py
```

The supplied tests build reviewed rules, profiles, protected cases and recorded obligations through real HTTP commands. The port itself is a direct Python read interface and has no registered HTTP endpoint. Independent probes used the same real persisted domain workflow rather than mocks for rules, cases or authorization.

The independent eight scenarios ran on both SQLite and actual PostgreSQL:

1. **Hidden versus empty:** a wholly inaccessible unresolved task produces a projection exactly equal to the original empty projection. Withdrawing its rule leaves that equality unchanged; no task ID, hidden count or recall-driven state appears.
2. **Warm-cache reassignment:** a limited task owner can initially read their detailed obligation after schoolwide task management is revoked. Another authorized manager reassigns it through HTTP. Reusing the original reader's already-loaded session returns an unavailable empty projection, with none of the former task's metadata.
3. **Applicability:** unresolved → reviewed not applicable → reviewed applicable through real input-resolution commands refreshes task versions and actionability in the same session. Non-applicable work returns no required action/document types; the applicable case returns the generic reviewed action and document types. Recorded timing is preserved.
4. **Supersession and multiple profiles:** a later reviewed successor profile does not replace the source of an older occurrence's obligation. The old and new obligations retain distinct actual profile IDs. Revoking the successor removes its actionable content and marks review required while preserving the old obligation's historical effective source/action.
5. **Live scope at empty reads:** missing resolver returns safe 503; wrong learner linkage returns 403. Malformed/missing/nonexistent cases fail closed. Revoking exact governance case authority after warming the session denies the next read.
6. **New accused exclusion:** after a successful warm-session read, another case reviewer identifies the reader as an excluded staff subject through the real protection command. The next read is denied by the owning context despite remaining governance task authority.
7. **Read side effects:** a SQL event listener observed no INSERT/UPDATE/DELETE/DDL across repeated reads. Obligation, applicability-history, governance-event, audit, safeguarding-receipt and safeguarding-event counts remained unchanged; the session had no new/dirty/deleted objects.
8. **Concrete deadline preservation:** an actual seven-calendar-day rule produces a non-null recorded local deadline date and UTC instant. Withdrawing the source in another request makes the warm-session projection review-required and withholds its action, while retaining exactly the stored date/instant and obligation version. No deadline is recalculated at read time.

The supplied suite additionally exercised source rule withdrawal with cached source objects, unresolved inputs, current rule/profile digests, multiple profile recall, wrong school/learner/case scope, and revocation of the owning safeguarding permission. No source prose, action description or protected dossier was added to the metadata projection.

## Commands and results

From `/Users/lauritz/Programming/SpesPed`:

```sh
mkdir -p var/review-j16/recheck-pinned
git archive 30c656f624a32bb4512f4894388f46afcc2e521d | tar -x -C var/review-j16/recheck-pinned
```

Then, from `/Users/lauritz/Programming/SpesPed/var/review-j16/recheck-pinned`:

```sh
PYTHONPATH=/Users/lauritz/Programming/SpesPed/var/review-j16/recheck-pinned/backend:/Users/lauritz/Programming/SpesPed/var/review-j16/recheck-pinned/backend/tests \
SPESPED_TEST_POSTGRES_URL=postgresql+psycopg://spesped_test:synthetic-development-only@127.0.0.1:55432/spesped_test \
/Users/lauritz/Programming/SpesPed/backend/.venv/bin/pytest \
backend/tests/test_safeguarding.py backend/tests/test_protected_rule_context.py -q

PYTHONPATH=/Users/lauritz/Programming/SpesPed/var/review-j16/recheck-pinned/backend:/Users/lauritz/Programming/SpesPed/var/review-j16/recheck-pinned/backend/tests \
SPESPED_TEST_POSTGRES_URL=postgresql+psycopg://spesped_test:synthetic-development-only@127.0.0.1:55432/spesped_test \
/Users/lauritz/Programming/SpesPed/backend/.venv/bin/pytest \
/Users/lauritz/Programming/SpesPed/var/review-j16/test_rule_projection_independent.py -q
```

- Combined repaired J16 and root candidate suites: **84 passed, 1 skipped**, 52.36 seconds. The root candidate contributes **10 passing tests**; the skip belongs to SQLite safeguarding concurrency. Production PostgreSQL concurrency and explicit context migration roundtrips passed.
- Final independent read-port probes: **16 passed**, 9.86 seconds, eight scenarios on each actual database engine.
- Only the existing Starlette TestClient/httpx deprecation warning appeared.
- An initial independent applicability probe omitted the required `timing` command field and correctly received 422 on both engines; the probe was corrected to submit `timing={}` before the final run. That validation response was not treated as an implementation defect.
- Evidence: ignored `var/review-j16/recheck-suite.log`, `rule-projection-independent.log`, and `test_rule_projection_independent.py`. The separate five-finding J16 repair evidence is preserved in `docs/reviews/J16-review.md` and its referenced artifacts.
- Each PostgreSQL case used its own temporary `j16_<uuid>` schema in synthetic `spesped_test`; fixtures dropped those schemas afterward. No demo database, real pupil information or external service was used.

## Explicit remaining boundaries

This helper is not registered as `safeguarding_rule_context`. The existing flat safeguarding `ReviewedRuleContext` still needs an agreed richer adapter contract and actual production composition that preserves per-obligation source/applicability/deadline states and multiple profiles. Missing/recalled/unresolved context must remain visible without making otherwise authorized case access or manual urgent action dependent on successful rule lookup. Nothing in this bounded acceptance verifies that later integration.

Historical source eligibility, recorded task state and an explicit `not_assessed` completeness label must remain distinct in the UI. Empty authorized recorded work is not evidence that no legal duty exists, and generic required actions must not be relabeled as notifications. Current-law review, school-approved configuration, production registration, connector transmission, J23 UI and whole-feature acceptance remain outside this review. No new legal certification or external contact occurred.

Only this report, the appended J16 recheck and ignored review artifacts were written. Review edits stopped after recording the evidence.

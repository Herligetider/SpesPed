# J19 professional authority — independent review

Reviewed commit: `25ac24e2d1440c9000ea41e3f0c2ca4c2d3c253f` (`codex/implement-spesped`).
Review date: 21 October 2026. Reviewer: `/root/review_j19`, independent of the native authority author and root application-integration author.

**Disposition: changes required. J19-R1 and J19-R2 remain open.** This is a bounded review of the professional-authority persistence, native BC07/BC09 adapters, application composition, migration and pending-dependency guards in the 23-file commit. It does not accept the whole J19 job or F01/F11/F19.

## J19-R1 — P2: withdrawn negative determinations remain asserted as current ineligibility

Locations: `backend/spesped/contexts/administration/adapters.py:29` and `backend/spesped/contexts/administration/service.py:101–107`.

`resolve()` returns `ineligible` immediately when the stored check has that outcome, before `current()` and `validate()` recheck the reviewer, exact source revisions and subject person's assignment. The metadata view similarly returns `ineligible` on every `DomainError` whenever the historical outcome was negative. In fact, `current()` defaults to requiring a positive outcome, so the negative metadata path never reaches its dependency validation.

Reproduction, independently exercised on SQLite and PostgreSQL:

1. Persist reviewed qualification and responsibility for a person, and an exact instrument-administration review with outcome `ineligible`.
2. Confirm the native authority port reports `ineligible`.
3. Separately revoke either the referenced qualification, the human reviewer's `professional.review.instrument_administration` grant, or the subject person's pupil assignment.
4. Resolve the exact request again with an independently authorized consumer.

Actual: all six database/scenario combinations still report `ineligible`. Required: report `unresolved` after the current binding is withdrawn, retaining the immutable historical check's `outcome=ineligible`. An unchanged, valid negative determination should continue to report `ineligible`. Both the native consumer result and curated HTTP metadata need this distinction; returning a negative historical outcome must not bypass current reviewer/dependency validation. This does not manufacture positive permission, but it presents an unsupported current professional decision and can block reconciliation using withdrawn authority.

Evidence: [independent probes](/Users/lauritz/Programming/SpesPed/var/review-j19/test_review_j19.py:17), [initial probe results](/Users/lauritz/Programming/SpesPed/var/review-j19/independent-tests.log). Test: `test_negative_decision_rechecks_dependencies`, parameterized by both databases and three withdrawal types. The port assertion fails first; the same metadata flaw is directly visible in `view()`'s exception handling.

## J19-R2 — P2: replay authorizes a newer review purpose instead of the original command

Location: `backend/spesped/contexts/administration/service.py:127–136`.

Review commands contain an exact `revision_id`, but their authorization is selected from the record's current revision. An `assessment_review` revision can change its request purpose while retaining the record's immutable person/pupil coordinates. The receipt branch returns before checking the original revision. Thus authorization for the newer purpose can satisfy a replay of an older professional signing operation whose own authority has been revoked.

Reproduction, independently exercised on SQLite and PostgreSQL:

1. Persist and approve an exact `statement_finalize` professional review; retain its complete successful review command and request key.
2. Revise that record to the `grade_set` purpose for the same statement/person/pupil.
3. Revoke the actor's `professional.review.statement_finalize` grant, retaining their `professional.review.grade_set` grant and ordinary pupil access.
4. Replay the original successful `statement_finalize` review command and key.

Actual: HTTP 200 with the newer draft record. Required: HTTP 403 because the original operation's signing purpose is no longer authorized. Reauthorization must bind the original command's exact revision/purpose in addition to current school/pupil access. Keeping current result projection semantics is compatible with this requirement. No duplicate business mutation was observed; this is an authorization bypass in the semantic replay contract.

Evidence: [independent replay probe](/Users/lauritz/Programming/SpesPed/var/review-j19/test_review_j19.py:139), [replay results](/Users/lauritz/Programming/SpesPed/var/review-j19/replay-tests.log). Test: `test_review_replay_reauthorizes_original_purpose`.

## Isolation, pin and verification

I read `AGENTS.md`, the complete 23-file candidate change, the authority contract in `docs/09-domain-implementation.en.md`, both consumer port definitions, and relevant native identity, teaching, assessment and curriculum owner code. Shared checkout changes belonging to the documents/gateway authors were not used or edited.

A new frozen checkout was produced with:

```sh
git archive 25ac24e2d1440c9000ea41e3f0c2ca4c2d3c253f | tar -x -C var/review-j19
```

Python: root `backend/.venv/bin/python`, version **3.12.13**. Every test used this absolute `PYTHONPATH`:

```text
/Users/lauritz/Programming/SpesPed/var/review-j19/backend:/Users/lauritz/Programming/SpesPed/var/review-j19/backend/tests
```

The working directory was `/Users/lauritz/Programming/SpesPed/var/review-j19`. `spesped`, the administration modules and fixture imports were verified to originate in that archive, not the editable shared checkout. Every one of the 23 changed files was compared byte-for-byte with `git show <pinned-commit>:<path>`; SHA-256 values, byte counts and import origins are retained in [hash-manifest.json](/Users/lauritz/Programming/SpesPed/var/review-j19/hash-manifest.json).

PostgreSQL used only the provided isolated synthetic `spesped_test` database on `127.0.0.1:55432`, supplied via `SPESPED_TEST_POSTGRES_URL`. Tests created UUID-named schemas and their fixture teardown removed them; there were no teardown errors. SQLite used pytest temporary files. No demo listener, database or 18878 harness was altered. This reviewer started no network listener, external model call, HR connection or message.

All commands below used the absolute interpreter and `PYTHONPATH` above, with `SPESPED_TEST_POSTGRES_URL` set to the provided test URL. File paths are relative to the frozen checkout:

| Pytest command suffix | Result | Evidence |
|---|---|---|
| `-m pytest backend/tests/test_professional_authority_native.py backend/tests/test_professional_authority_adverse.py backend/tests/test_professional_authority_consumers.py backend/tests/test_professional_authority_migrations.py backend/tests/test_professional_application_composition.py backend/tests/test_bc09_application_composition.py -q` | **41 passed, 1 skipped**, 66.51 s | [full-j19-tests.log](/Users/lauritz/Programming/SpesPed/var/review-j19/full-j19-tests.log) |
| `-m pytest backend/tests/test_assessment_contracts.py backend/tests/test_assessment_repairs.py backend/tests/test_owned_learning_projections.py backend/tests/test_curriculum_composition.py -q` | **37 passed, 1 skipped**, 72.24 s | [affected-tests.log](/Users/lauritz/Programming/SpesPed/var/review-j19/affected-tests.log) |
| `-m pytest test_review_j19.py -q` (initial 14-case probe set) | **6 failed, 8 passed**, 24.39 s; six J19-R1 reproductions | [independent-tests.log](/Users/lauritz/Programming/SpesPed/var/review-j19/independent-tests.log) |
| `-m pytest test_review_j19.py -k replay -q` | **2 failed**, 7.39 s; two J19-R2 reproductions | [replay-tests.log](/Users/lauritz/Programming/SpesPed/var/review-j19/replay-tests.log) |
| `-m pytest test_review_j19.py -k 'late_transaction or concurrent_source' -q` | **3 passed, 1 skipped**, 5.96 s | [atomic-concurrency-tests.log](/Users/lauritz/Programming/SpesPed/var/review-j19/atomic-concurrency-tests.log) |

Skips were deliberate SQLite concurrency exclusions; real PostgreSQL locking tests ran. Non-blocking warnings concerned the existing curriculum `copy` field and Starlette's httpx deprecation. Independent probe results were collected as the file grew; the final file contains all 20 unique cases: eight failing finding reproductions, eleven passing cases and one SQLite-only skip across those commands.

## What the passing checks establish

Within these tests, production `create_app` registers persisted native authority ports and routes; authority survives a new application instance without synthetic eligibility ports. Positive qualification/responsibility/policy recall invalidates current BC07/BC09 projections while retaining actuals and human judgements. Exact person/pupil/target/digest/period matching, conflicting responsibility reconciliation, current reviewer/assignment revocation, private personnel versus curated metadata access, and source coverage fail closed in the exercised positive paths. Qualification is not inferred from fixture role labels or bootstrap public grants.

Caller pending changes are rejected without flush, DML, commit, rollback or overwriting retained caller identities. Stale sessions re-read persisted revocation. Independently checked consumer versus subject-person access, one-day assignment boundary, private content separation and refused unauthorized professional writes passed on both databases. The final independent failure injection ran after business/audit/outbox/receipt persistence had been staged and confirmed that rollback removed every artifact, with a subsequent retry succeeding.

Committed PostgreSQL concurrency cases exercised same-key duplicates, conflicting semantic keys and expected-version races behind a real held tenant row lock. An additional independent PostgreSQL race between source revision and source revocation produced exactly one success and one conflict; neither resulting draft nor revoked source resurrected eligibility. Static migration metadata, retained prior-school data, empty roundtrip and retained-history downgrade refusal passed on both databases.

## Limits and handoff

Only the new review document and ignored `var/review-j19` evidence were written. No product code, existing test, source commit, branch, worktree state, unrelated author file or shared dependency was changed; no commit/push/reset/stash/spawn was performed.

Return J19-R1/R2 to the original author and re-review a newly pinned repair. The current candidate is not accepted while they remain open. Passing bounded tests do not establish complete school/account/enrollment administration, other administrative workflows, appeals, UI, real external HR reconciliation, dispatch, the whole J19 scope or complete features. Legal sources researched in September 2026 were not newly verified in this review.

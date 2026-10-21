# Application composition review

- Reviewed commit: `30fe56394d916956ccdb0802726f41c944c04dd2`.
- Scope: the eleven files in `30fe563^..30fe563`, connecting the existing plans, entitlements, protected safeguarding and governance contexts through the real application factory.
- Reviewer: `/root/review_composition`, independent of the root implementation author.
- Review date: 2026-10-21.
- Verdict: **accepted for this bounded application composition; no blocking findings**.

## Scope accepted

The actual application registers the support-case, education-plan and safeguarding routers. Application-installed adapters validate evidence goal references through plans, exact protected case/learner scope through safeguarding, and governance evidence references against the current authorized protected snapshot. The safeguarding rule-context adapter preserves separate recorded obligations, rule/profile revisions, applicability uncertainty, deadlines and recall status.

The new strict rule-context contract rejects contradictory availability/actionability claims. Missing, denied or invalid optional governance metadata produces an empty `unavailable` projection after protected-case authorization. This does not grant case permission, reveal inaccessible task identities/counts, suppress an otherwise authorized dossier/export, classify generic actions as notifications, or fulfill obligations. Actual contacts and actions remain distinct from rule metadata.

## Verification

The review used a separate `git archive` of the exact commit under `var/review-composition/pin`. All test commands used the shared Python 3.12 runtime with **absolute** `PYTHONPATH` entries pointing first to that archive's `backend` and `backend/tests`; no later working-tree implementation was imported. PostgreSQL verification used the configured synthetic test database, with unique temporary schemas created and removed by the fixtures. SQLite was also exercised. No external model or message service was used.

Pinned regression command, from the archived repository:

```sh
PYTHONPATH=/Users/lauritz/Programming/SpesPed/var/review-composition/pin/backend:/Users/lauritz/Programming/SpesPed/var/review-composition/pin/backend/tests \
  /Users/lauritz/Programming/SpesPed/backend/.venv/bin/python -m pytest -q \
  backend/tests/test_protected_assembly.py \
  backend/tests/test_plan_assembly.py \
  backend/tests/test_context_integration.py \
  backend/tests/test_safeguarding.py \
  backend/tests/test_protected_rule_context.py
```

With `SPESPED_TEST_POSTGRES_URL` supplied: **106 passed, 1 skipped**, in 83.25 seconds. The skip is the existing SQLite concurrency-only exclusion; the PostgreSQL counterpart ran. The only warning is the existing FastAPI/Starlette TestClient deprecation.

Independent reviewer probes, retained as ignored artifacts:

- `var/review-composition/test_protected_composition_adverse.py`.
- `var/review-composition/test_plan_composition_adverse.py`.

Both were run with the same archived import paths and configured PostgreSQL test URL: **16 passed**, in 16.48 seconds. Each scenario ran on SQLite and PostgreSQL:

1. Revoked optional governance authority leaves authorized case detail/export available, with no rule, profile or task identifiers; revoking the separate protected export authority still denies export.
2. Another authorized case's current snapshot and a foreign school path cannot satisfy the target obligation's evidence reference. Rejected requests create no obligation action and imply no actual contact.
3. Removing task management authority leaves only an explicitly owned obligation visible. Reassignment hides that obligation too, with no hidden count or identifier.
4. Revoking a profile updates the live export's review/source status and removes actionable requirement prose, while preserving immutable case history and recorded obligation state/count.
5. Deliberately malformed model-constructed metadata is revalidated and suppressed. Authorized dossier/export and manual contact recording remain usable.
6. An unactivated goal is rejected without creating confirmed evidence. After exact plan review, approval and activation, the same reviewed proposal can be confirmed against that goal.
7. Goal-bound confirmation rechecks plan read authority and source currency; revoked permission and corrected plan evidence block confirmation.
8. An activated historical goal remains referenceable by its exact old revision after a new revision is activated; the evidence binding is not silently rewritten to the new goal.

The pinned suites also exercised multiple profile histories, unresolved applicability, rule withdrawal, current versus stale protected snapshots, cross-learner goal denial, exact owning-case authorization, and separate actual notification/receipt states.

## Limits

This accepts the composition change, not complete feature delivery, all pre-existing context behavior, later commits, production deployment or legal completeness. It does not review the later teaching implementation or the document-intake UI. User interfaces, reviewed school-specific rule/contact configuration, remaining workflows and broader feature acceptance remain separate work. The legal source registry was not re-researched by this review. No production-ready or full-feature completion conclusion follows from these test results.

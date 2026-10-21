# Generated IEP and teaching application composition review

- Reviewed commit: `ae4496916141bca12475b0f60eaf5e462ffcc5e6`.
- Scope: its four-file parent diff: teaching router registration in `main.py`, the `b5_generated_teaching` merge migration, `test_generated_teaching_integration.py`, and the qualification-port contract text in `docs/09-domain-implementation.en.md`.
- Reviewer: `/root/review_composition`, independent of the root implementation author.
- Review date: 2026-10-21.
- Verdict: **accepted for this bounded application composition; no new composition findings**. The combined workflow is **not** accepted as complete while the separately reported consumer defects and user-interface work remain open.

## Accepted boundary

A fresh application factory installs the teaching router once, alongside the existing plans, evidence and gateway routes. The generated-plan and generated-session APIs retain explicit professional selection/review/approval steps. Producing model output does not activate a goal, approve a session, publish an assistant brief or record delivery. The assigned assistant projection remains separate from the full education plan and session dossier.

The default application leaves the optional qualification port unconfigured. In that state, reported staff roles and permissions do not establish qualification or assessed individually adapted education. Actual work can instead be recorded as unassessed, with a cause and an owned follow-up, and stays separate from assessed entitlement comparison. The documentation accurately describes that boundary and identifies the production qualification source as remaining J19 work; it does not establish full interval coverage or legal completeness.

The merge migration joins the actual `j05_plan_generation` and `j06_teaching_repairs` heads without changing either parent's tables or data. The resulting graph has one head, `b5_generated_teaching`.

## Verification environment

All execution used a separate `git archive` of the exact commit under `var/review-generated-teaching-composition/pin`. The shared Python 3.12 runtime was supplied absolute `PYTHONPATH` entries for that archive's `backend` and `backend/tests`, so later working-tree code was not imported. Tests used synthetic records, loopback HTTP model-protocol servers and unique temporary PostgreSQL schemas in the configured test database. No external AI, mailbox or message delivery service was used.

### Pinned integration tests

From the archived repository, with the configured `SPESPED_TEST_POSTGRES_URL`:

```sh
PYTHONPATH=/Users/lauritz/Programming/SpesPed/var/review-generated-teaching-composition/pin/backend:/Users/lauritz/Programming/SpesPed/var/review-generated-teaching-composition/pin/backend/tests \
  /Users/lauritz/Programming/SpesPed/backend/.venv/bin/python -m pytest -q \
  backend/tests/test_generated_teaching_integration.py
```

Result: **5 passed**, no skips, in 41.24 seconds. This exact file collects one default-route test and two recall scenarios on each of SQLite and PostgreSQL. Its flow covers generated IEP goal selection and activation, local session generation, separately reviewed assistant briefing, assistant observation, unassessed actual support and a subsequent basis/session. Revoking the ancestor IEP release or correcting its expert source hides affected session and assistant-brief content.

### Independent fresh-application probes

Reviewer artifact: `var/review-generated-teaching-composition/test_fresh_application.py`.

Result: **4 passed**, no skips, in 45.43 seconds: two recall scenarios on each database. These probes create a new application using the real `create_app`, independently count the installed router objects, require exactly one teaching router with no duplicate router objects, and replace `include_router` with a rejecting function before the HTTP flow. Fixture route injection therefore cannot supply missing application wiring.

The probes verify that:

- A successful IEP generation job leaves a draft; selected generated goals cannot enter a teaching basis until the exact plan is activated.
- A successful teaching generation job leaves the session draft. Human field selection preserves unselected human content. Direct approval before review and brief creation before session approval are rejected.
- Opening an approved assigned brief does not record completion. The assistant can record an observation while full plan/session access is denied. Neither generating, opening nor observing creates actual-delivery records.
- With no configured qualification port, an assessed ITO delivery is rejected without creating an actual record. Recording it as unassessed persists an open follow-up owned by the responsible professional; summary totals remain unassessed and claim no entitlement fulfilment.
- A saved assistant observation can support a subsequent basis/session. Revoking the ancestor IEP **policy**, or correcting its expert-source learner association, hides content in both affected sessions and the curated assistant brief.

The only test warning was the existing FastAPI/Starlette TestClient deprecation.

### Independent migration verification

Reviewer artifact: `var/review-generated-teaching-composition/schema_probe.py`.

Both **SQLite and PostgreSQL passed**:

1. Upgrade separately to the two parent heads; verify both heads and the complete model schema.
2. Insert a synthetic school sentinel, upgrade to the merge head, and verify the sentinel and schema remain unchanged.
3. Downgrade explicitly to `j05_plan_generation`, which splits this merge into both parent heads without dropping either branch's schema; verify the sentinel is preserved.
4. Reapply the merge and verify the unique head.
5. Perform a complete empty base/head migration cycle and compare metadata again.

Each checked state contains **115 model tables** and no Alembic metadata differences, including types and server defaults. PostgreSQL JSON defaults were compared as parsed literal JSON values because PostgreSQL's `json` type has no equality operator; other default comparisons retain Alembic's normal behavior. Temporary PostgreSQL schemas were removed. Alembic's relative `-1` shorthand was ambiguous at the merge, so the probe uses the explicit parent revision.

The merge-only sentinel test does not claim that every inherited data-bearing downgrade is safe; J06-R7 remains a separate open finding at this pin.

## Inherited defects and remaining work

These findings were already assigned to their owning consumers and are not reclassified as new composition findings:

- [J05 generation review](J05-generation-review.md): the outer generated-goal currency predicate can autoflush, and the inner helper can report current lineage despite a pending source-link revocation.
- [J06 review](J06-review.md), R6: qualification coverage is checked at the start of the recorded occurrence rather than across the full support interval.
- [J06 review](J06-review.md), R7: the inherited downgrade can lose a legacy assistant-reconciliation invalidation token.

Those defects require their own repair and independent recheck before broader workflow acceptance. This review does not certify the full J05/J06 consumers, unfinished UI, professional teaching quality, school-specific qualification configuration, deployment or all forty features. The legal registry was not re-researched. No production code was changed by the reviewer.

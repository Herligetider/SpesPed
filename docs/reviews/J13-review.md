# J13 independent backend review

- Reviewer: `/root/review_j13`, independent of `/root/j13_governance`.
- Reviewed revision: `1c3acfa7e65272994f9b0ddba68875a58b525983`.
- Review date: 21 October 2026.
- Verdict: **changes requested**. Four reproducible findings remain; the passing suite does not establish acceptance.
- Scope: governance models, commands, policies, services, router, `j13_governance` migration and tests; F06/F29/F40 including workspace, stateBehavior, automationBoundary and recovery; shared domain contracts and AGENTS.md.
- Model boundary: deterministic applicability, timing and workload arithmetic are appropriate here. No external AI/model service was used or verified. Review used the independently assigned reviewer, with no model override or delegated reviewer.

## Findings

### J13-R1 — P1: Rule impact returns hidden learner/case obligation metadata

Location: `backend/spesped/contexts/governance/service.py:181–195`, especially 186–192.

`profile_impact` checks only `governance.rules.approve`, then returns individual obligation IDs, current versions and exact rule-version associations across the entire school. It never checks learner/case access. A staff member with that rule authority but no learner assignment receives 403 for the obligation detail and nevertheless receives its ID and rule association in the impact response. Counts and per-task metadata also bypass the small-cohort privacy restrictions applied to the leadership overview. Rule approval is not learner/case content permission under the shared contract.

Reproduction on both databases: `test_rule_approver_without_learner_access_receives_protected_task_id` creates an exactly authorized protected-case learner obligation and replacement profile, grants only `governance.rules.approve` to an unrelated staff member, verifies detail GET=403, then verifies impact GET=200 containing that same hidden obligation ID. The probe uses a protected case and grants the approver neither learner access nor exact case authority.

Required correction: keep the full authorized impact fingerprint for activation correctness while applying current learner/case authorization to identifiable output. Restricted aggregate impact must not reintroduce small-group disclosure. Add adverse tests for an unassigned rule approver and revoked exact case access.

### J13-R2 — P2: Applicability-changing school profile facts produce an empty impact

Location: `backend/spesped/contexts/governance/service.py:184–192`.

Impact comparison considers only requirement-version IDs. A replacement profile can change a reviewed applicability fact while selecting the same rule version, and the impact preview reports no affected tasks. This defeats F06's preactivation review of affected work even though historical tasks correctly remain unchanged.

Reproduction on both databases: `test_changed_profile_school_facts_omitted_from_impact` uses a reviewed condition `curriculum_scheme == A`; the first profile has A and its task is applicable. A replacement profile selects the same rule but school input B. Impact is exactly `items=[]`, `total=0`; activation succeeds with that digest; a fresh occurrence under the new profile becomes `not_applicable`.

Required correction: assess material school-fact/condition/timing effects, not just differing rule identifiers, and present the before/after effect while preserving historical tasks and activation digest binding.

### J13-R3 — P2: Closing a workload study disables voluntary withdrawal

Location: `backend/spesped/contexts/governance/service.py:468–480`, especially 472.

The closed-study guard runs before withdrawal handling. Once a study is closed, a consenting participant cannot withdraw, and their measurements continue contributing to published aggregate results. There is no other withdrawal command. Closing collection should not permanently lock voluntary participation.

Reproduction on both databases: `test_closed_study_cannot_withdraw_consent` records complete matched measurements for three participants and confirms aggregate manual time 30. After closing the study, the participant sends `consent=false` with their current version and receives 400 `closed_study`. Results continue reporting 30 instead of becoming an insufficient two-person sample.

Required correction: permit version-checked withdrawal after closure and re-evaluate aggregate eligibility, while continuing to reject new participation/measurements in a closed study.

### J13-R4 — P2: Remedial-action chronology checks entry time instead of actual action time

Location: `backend/spesped/contexts/governance/service.py:397–408`, especially 403.

Deviation resolution tries to ensure the selected performed action follows the deviation, but compares `recorded_at`. Entering an old action after reporting a current missing-delivery issue therefore satisfies the check, even when the actual action preceded both the deviation and its obligation occurrence. The distinction between occurrence and entry time is lost at the actual-resolution boundary.

Reproduction on both databases: `test_deviation_resolution_accepts_action_before_deviation_report` reports a current missing-delivery deviation, then records an action with `occurred_at` 30 days earlier. Resolution accepts that new record and returns `state=resolved`; the probe prints the actual occurrence and deviation creation instants. No remedial action occurred after the reported current issue. This is a timestamp-validation gap, not a claim that the software can determine the truth of human descriptions.

Required correction: use the actual performed-action time against the relevant deviation/remediation period. If retrospectively reported resolution is a supported workflow, represent its occurrence/effect assessment explicitly rather than treating recent data entry as recent remedial performance.

## Verification

Pinned code was extracted with `git archive` into ignored `var/review-j13/pinned`; no implementation/shared files were changed. Tests use unique temporary PostgreSQL schemas in `spesped_test`, not `spesped_demo`. Migration target was the context's own `j13_governance` revision with parent `a9e1f00151e4`, independently of the uncommitted integration merge.

Commands (from the repository root):

```sh
git archive 1c3acfa7e65272994f9b0ddba68875a58b525983 | tar -x -C var/review-j13/pinned
PYTHONPATH=var/review-j13/pinned/backend SPESPED_TEST_POSTGRES_URL=postgresql+psycopg://spesped_test:synthetic-development-only@127.0.0.1:55432/spesped_test backend/.venv/bin/pytest var/review-j13/pinned/backend/tests/test_governance.py -q
PYTHONPATH=var/review-j13/pinned/backend:var/review-j13/pinned/backend/tests SPESPED_TEST_POSTGRES_URL=postgresql+psycopg://spesped_test:synthetic-development-only@127.0.0.1:55432/spesped_test backend/.venv/bin/pytest var/review-j13/test_adversarial.py -q -s
```

Results:

- Pinned implementation suite: **35 passed**, 13.24 seconds.
- Independent adverse probes: **12 passed**, 5.25 seconds (four observed defects and two additional positive adverse checks, each on SQLite and PostgreSQL). The eight defect reproductions assert the observed buggy behavior; they must change to assert rejection/correct behavior after repair. The four positive checks verify wrong case-to-learner linkage is denied despite an exact grant, and evidence authorization revoked after submission is rechecked at fulfillment with no state change.
- Single warning: Starlette TestClient/httpx deprecation.
- Reproduction source and captured output: `var/review-j13/test_adversarial.py`, `var/review-j13/adversarial.log` (ignored, synthetic only).
- A preliminary shared-checkout run also returned 35 passed, but the pinned extraction is the acceptance evidence above.

The pinned suite meaningfully exercised candidate import of 90 unreviewed baseline entries without automatic activation; reviewed immutable rule/profile versions and PostgreSQL write protection; unresolved applicability; distinct immediate, qualitative and calendar timing including Oslo DST; required document attribution versus performed actions; school/learner/exact-case checks and revocation; owner metadata versus dossier access; per-cell leadership suppression; concurrent PostgreSQL trigger deduplication and changed-key conflict; transaction rollback of business state/audit/outbox; full-cost matched voluntary workload measurement, corrections, quality gates and small samples; and migration downgrade/upgrade on the isolated context branch. Independent review found the exceptions above beyond those checks.

## Remaining boundaries

- Fixes require independent recheck before accepting J13.
- Root-owned, uncommitted application assembly and real J04 evidence adapter are deliberately outside this pinned review. Synthetic evidence hooks verify the port contract and revision reauthorization only; they do not verify actual J04 composition.
- J16 case ownership resolver is not yet available. The reviewed expected boundary is 503 after an exact case grant when unconfigured, and denial of a mismatched case-to-learner result. No actual protected-case integration is claimed.
- J24 browser/calendar/admin UI, organizational delivery integrations and later full feature acceptance remain outside this backend job.
- September legal registry entries remain unreviewed candidates; no current-law research or production legal approval was performed.

## Independent fix recheck — 21 October 2026

**Rechecked revision:** `974833166854f74ce89ada5d6c8730fbc08719d8`.

**Verdict: verified for the assigned J13 backend scope. All four findings above are fixed; no additional reproducible finding remained in this recheck.** The original review and its evidence are preserved above. This verdict does not establish full F06/F29/F40 UI completion or production readiness.

The governance changes since the original candidate are limited to `service.py` and `test_governance.py`. The fixed revision also contains separately integrated work in other contexts; this review does not accept those changes. Tests below used a fresh exact `git archive` extraction at `var/review-j13/fixed-pin`, with the context migration target `j13_governance` and unique synthetic PostgreSQL schemas.

### Finding dispositions

- **J13-R1 fixed** (`service.py:226–269`, activation at 273–278): impact output now requires the same current subject/task authorization as detail retrieval. `items` and `total` describe authorized tasks only. Hidden work remains in the internal activation fingerprint. Tests verified exact case authority revocation removes details, hidden task changes invalidate an older activation digest, and refreshed restricted previews can be activated by the rule approver. An additional independent test compared an empty impact to a single hidden protected-case impact: every response field except the opaque digest was identical. Removing the case ownership resolver also suppressed identifiable output without changing that fingerprint; direct detail correctly remained 503. No hidden cohort count or rule association appeared in the restricted response.
- **J13-R2 fixed** (`service.py:181–249`): impact simulation replaces reviewed school facts, distinguishes removed facts from retained event inputs, and returns before/after applicability and timing. Verified A→B, A→unknown, formerly not-applicable→applicable, changed legal timing with missing start data, and preserved historical task values. An independent overflow probe used recorded start `9999-12-31` with a proposed one-month deadline: the preview returned explicit unresolved timing information rather than failing or inventing a due date, and left historical version/timing unchanged.
- **J13-R3 fixed** (`service.py:547–563`): closed studies permit version-checked withdrawal while prohibiting new consent and measurements. Verified contribution removal from the aggregate, the resulting insufficient two-person sample, preserved measurement history, stale-version rejection, and repeat withdrawal retaining the original withdrawal instant/version.
- **J13-R4 fixed** (`service.py:474–485`): actual action occurrence is checked against the obligation occurrence, deviation creation and most recent reopening. The original month-old action is rejected. Independently exercised three actual remediation cycles separated by two reopenings: each prior action was rejected for the renewed issue, each newly performed action was accepted, and rejected attempts preserved the exact deviation state, version and follow-up history. Source authorization/revision checks remain at resolution.

### Commands and results

From the repository root:

```sh
mkdir -p var/review-j13/fixed-pin
git archive 974833166854f74ce89ada5d6c8730fbc08719d8 | tar -x -C var/review-j13/fixed-pin
PYTHONPATH=var/review-j13/fixed-pin/backend SPESPED_TEST_POSTGRES_URL=postgresql+psycopg://spesped_test:synthetic-development-only@127.0.0.1:55432/spesped_test backend/.venv/bin/pytest var/review-j13/fixed-pin/backend/tests/test_governance.py -q
PYTHONPATH=var/review-j13/fixed-pin/backend:var/review-j13/fixed-pin/backend/tests SPESPED_TEST_POSTGRES_URL=postgresql+psycopg://spesped_test:synthetic-development-only@127.0.0.1:55432/spesped_test backend/.venv/bin/pytest var/review-j13/test_fixed_regressions.py -q
PYTHONPATH=var/review-j13/fixed-pin/backend:var/review-j13/fixed-pin/backend/tests SPESPED_TEST_POSTGRES_URL=postgresql+psycopg://spesped_test:synthetic-development-only@127.0.0.1:55432/spesped_test backend/.venv/bin/pytest var/review-j13/test_fixed_additional.py -q
env -u SPESPED_TEST_POSTGRES_URL PYTHONPATH=var/review-j13/fixed-pin/backend backend/.venv/bin/pytest var/review-j13/fixed-pin/backend/tests/test_governance.py -q -k context_migration_roundtrip_isolated_database
```

- Fixed implementation suite: **47 passed**, 23.75 seconds.
- Original independent probes, stored with corrected success/rejection expectations: **12 passed**, 6.03 seconds. The original defect-reproduction file was preserved.
- Additional independent regressions beyond supplied fixes: **6 passed**, 3.78 seconds.
- Portable no-PostgreSQL-configuration check: **1 passed, 1 skipped, 45 deselected**, 0.61 seconds. PostgreSQL is explicitly skipped when its URL is absent; this is separate from the successful configured PostgreSQL runs above.
- Only the existing TestClient/httpx deprecation warning appeared.
- Captured evidence: ignored `var/review-j13/fixed-suite.log`, `fixed-original-regressions.log`, `fixed-additional.log`, `fixed-portable.log`; probe sources `test_fixed_regressions.py` and `test_fixed_additional.py`.

The original boundaries still apply: real J04 adapter/application composition have their separate review; actual J16 case integration remains unavailable; J24 UI and later full feature acceptance are outstanding; September legal candidates have received no new legal certification. This recheck changed only this review report and ignored review artifacts, and performed no implementation edits, commits, pushes, external AI calls or external messages.

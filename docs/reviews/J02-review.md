# J02 independent review

## Final targeted recheck — accepted within J02 scope

On 21 October 2026, independently rechecked exact candidate **e1588794f63eaaa725875060bf1a602c512bc686**. **No outstanding findings remain in the reviewed J02 scope.** The original three findings and the subsequent empty-period integration finding are verified fixed across the two repair rounds below. This accepts the shared domain-core job, not completion of downstream features or production readiness.

The final repair introduces `EmptySummaryPeriodError`, a `ValueError` subclass raised only for a calendar-label range with no real instants. `DraftRecurrence.next_request()` now catches that specific condition and continues through the existing cadence and end-date policy. The valid Apia 2011-12-31 candidate that would summarize nonexistent December 30 no longer leaves the schedule stuck: the daily request advances to January 1 and summarizes December 31. The monthly day-31 schedule with `MonthEndPolicy.SKIP` also advances correctly through missing November 31 and the empty December summary to January 31, without shifting the anchor. Schedules ending before the next valid draft return `None`; retries return the same logical draft identity. Ordinary validation/type failures continue to propagate. One-day nonexistent manual summaries remain rejected, and draft requests still confer no dispatch authority.

Exact candidate and regression verification commands:

```sh
git rev-parse e158879
git diff --exit-code e158879 -- backend/spesped/domain backend/tests/test_domain_core.py
git diff 65eae8b..e158879 -- backend/spesped/domain backend/tests/test_domain_core.py
PYTHONPATH=backend /opt/homebrew/bin/python3.12 -m unittest discover -s backend/tests -p test_domain_core.py -v
```

Result: working-tree J02 files match the pinned candidate, and **35/35 tests pass independently**. The final diff only changes empty-period signaling/handling and adds three focused regressions. The following additional exact transient command also passed:

```sh
PYTHONPATH=backend /opt/homebrew/bin/python3.12 - <<'PY'
from dataclasses import replace
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo
from unittest.mock import patch
from spesped.domain import *
from spesped.domain.primitives import EmptySummaryPeriodError
UTC=timezone.utc
zone=ZoneInfo('Pacific/Apia')
scope=SubjectScope(SchoolId.new(),LearnerId.new())
r=DraftRecurrence(ScheduleId.new(),RevisionId.new(),scope,DraftCadence.DAYS,date(2011,12,29),zone.key,DraftPeriodSelection(PeriodRule.PREVIOUS_DAYS,1)).activate()
first=r.next_request(datetime(2011,12,28,tzinfo=UTC))
last=r.next_request(first.requested_for)
assert last.requested_for.astimezone(zone).date()==date(2012,1,1)
assert last.period.start==last.period.end==date(2011,12,31)
assert r.next_request(r.next_run(first.requested_for)).idempotency.key==last.idempotency.key
assert not last.authorizes_dispatch
for end in (date(2011,12,30),date(2011,12,31)):
    assert replace(r,end_date=end).next_request(first.requested_for) is None
assert replace(r,end_date=date(2012,1,1)).next_request(first.requested_for)==last
assert replace(r,end_date=date(2012,1,1)).next_request(last.requested_for) is None
monthly=replace(r,cadence=DraftCadence.MONTHS,anchor=date(2011,10,31),month_end_policy=MonthEndPolicy.SKIP)
month_first=monthly.next_request(datetime(2011,10,30,tzinfo=UTC))
month_next=monthly.next_request(month_first.requested_for)
assert month_next.requested_for.astimezone(zone).date()==date(2012,1,31)
assert month_next.period.start==date(2012,1,30)
assert replace(monthly,end_date=date(2011,12,31)).next_request(month_first.requested_for) is None
for error in (ValueError('ordinary validation'),TypeError('unexpected type')):
    with patch.object(DraftPeriodSelection,'resolve',side_effect=error):
        try:r.next_request(first.requested_for)
        except Exception as caught:assert caught is error
        else:raise AssertionError('Nonempty-period failure was swallowed')
try:SummaryPeriod(date(2011,12,30),date(2011,12,30),zone.key)
except EmptySummaryPeriodError:pass
else:raise AssertionError('Nonexistent manual period accepted')
print('PASS: daily/retry/end, monthly skip/end, nonempty-error propagation, manual rejection; no dispatch authority')
PY
```

Final verification limits: this targeted round exercises only the outstanding empty-calendar issue and its regressions; preceding rounds below cover the original fixes and unchanged primitives. Existing limits on live authorization, authoritative decision/reference lookup, durable idempotency, missed-run reporting, application integration, legal configuration, database/PostgreSQL behavior and real dispatch remain. No implementation files or tests were edited, and no commits, pushes or agents were created by this reviewer.

## Recheck of fixes — 21 October 2026

Rechecked exact candidate **65eae8b6f0748a0839592620be38a41fa490bb77** against the three original findings. `git diff --exit-code` confirmed that the shared working-tree domain and domain-test files matched this pin. The updated shared contracts in `docs/09-domain-implementation.en.md` and `docs/04-domain-model.en.md` now describe exact decision/provision identity, first-real-instant boundaries and independent manual requests.

**Current disposition: changes requested for one residual calendar issue.** The decision-identity and one-off manual-request findings are verified fixed. Santiago midnight gaps and Havana repeated midnight are fixed; automatic period selection still fails immediately after a wholly skipped calendar date.

Verified fixes:

- `calendar_date_boundary()` resolves Santiago 2026-09-06 to 04:00 UTC, selects the earlier repeated Havana midnight, and preserves contiguous half-open summary boundaries. Explicit nonexistent occurrence/recorded wall times remain invalid. Entirely nonexistent one-day manually supplied summaries are rejected at construction. The recurrence skips nonexistent run dates.
- `DecisionProvisionReference(scope, DecisionId, RevisionId, DecisionProvisionId)` is required on each `EntitlementQuantity`. Addition now rejects differing school, learner, protected case, decision, decision revision or provision, including identical text labels and matching periods. Compatible hours/minutes still convert correctly. Services must resolve the supplied reference against an authoritative decision; the value object does not establish its existence or access rights.
- `ManualDraftRequest(scope, period, requested_at, logical_request_key)` creates an ordinary request without schedule identity or activation. Retried attempt times preserve identity and fingerprint; changed periods retain command identity but change `request_digest` for conflict detection; a new deliberate command key produces a new identity. It grants no dispatch authority. Application persistence must actually enforce uniqueness and reject fingerprint conflicts, and the future full document command must bind its other semantic inputs as well.

### [P2] Automatic period selection fails after an entirely skipped date

Location at this pin: `backend/spesped/domain/recurrence.py:242-247` (period resolution at line 246).

For an accepted active daily recurrence in `Pacific/Apia`, with `PREVIOUS_DAYS=1` and anchor 2011-12-29, `next_run()` correctly skips nonexistent 2011-12-30 and returns the valid 2011-12-31 run. However, `next_request()` then attempts to construct a summary consisting solely of skipped 2011-12-30. The new `SummaryPeriod` validation raises `ValueError("Summary period contains no real instants")`. Repeatedly asking for the next draft after the preceding completed run therefore remains stuck on this candidate rather than returning a valid next request or explicit non-draft outcome. This is a residual integration issue in the calendar fix, not a request to accept nonexistent manual one-day summaries.

Define and implement an explicit automatic empty-period policy: for example, skip candidates whose resolved calendar window has no instants while respecting the end condition, or return a typed skipped-run outcome for the application to record. Preserve normal nonempty summaries and manual validation. Add a regression exercising `next_request()` rather than only `next_run()` across a wholly skipped date, and verify end-boundary behavior after such a skipped candidate.

Exact recheck verification commands:

```sh
git rev-parse 65eae8b
git diff --exit-code 65eae8b6f0748a0839592620be38a41fa490bb77 -- backend/spesped/domain backend/tests/test_domain_core.py
PYTHONPATH=backend /opt/homebrew/bin/python3.12 -m unittest discover -s backend/tests -p test_domain_core.py -v
```

Result: **32/32 tests pass** independently. A separate transient inline unittest run passed **3/3** additional checks for Santiago start/end membership and contiguity; all six decision/provision identity dimensions plus compatible conversion; and manual command retry, conflicting-period fingerprint, deliberate new order, and absence of dispatch permission. No implementation or test files were edited.

Exact residual reproduction command:

```sh
PYTHONPATH=backend /opt/homebrew/bin/python3.12 - <<'PY'
from datetime import date, datetime, timezone
from spesped.domain import *
from zoneinfo import ZoneInfo
r=DraftRecurrence(ScheduleId.new(),RevisionId.new(),SubjectScope(SchoolId.new(),LearnerId.new()),DraftCadence.DAYS,date(2011,12,29),'Pacific/Apia',DraftPeriodSelection(PeriodRule.PREVIOUS_DAYS,1)).activate()
first=r.next_request(datetime(2011,12,28,tzinfo=timezone.utc))
print('first',first.requested_for,first.period)
print('next_run',r.next_run(first.requested_for))
try:
    print('next_request',r.next_request(first.requested_for))
except Exception as error:
    print(type(error).__name__,error)
PY
```

Observed output:

```text
first 2011-12-29 10:00:00+00:00 SummaryPeriod(start=datetime.date(2011, 12, 28), end=datetime.date(2011, 12, 28), timezone='Pacific/Apia')
next_run 2011-12-30 10:00:00+00:00
ValueError Summary period contains no real instants
```

Recheck limits: calendar examples cover Oslo, Santiago, Havana and Apia, not every historical timezone transition or datetime-range extreme. No durable uniqueness enforcement, authorization, document-service integration, delivery, database/browser or PostgreSQL behavior was exercised. Prior non-calendar domain evidence below remains applicable to unchanged files; the original findings are retained as review history, not three outstanding findings at this pin.

## Original review — retained history

Reviewed on 21 October 2026. Final candidate: **35c613a765f6dfe43e839b3876278068535cf31f**, cumulative J02 diff from `7f3d652`. Initial candidate `bd207c8c3422a0bf56c742953444ca96a1c5be21` was superseded during review by the implementer's additional nonexistent-wall-time guard and regression. The final candidate includes that guard; it is not an outstanding missing-input finding.

Scope: `backend/spesped/domain/**` and `backend/tests/test_domain_core.py`. Read `AGENTS.md`, `docs/09-domain-implementation.en.md`, relevant `docs/04-domain-model.en.md` semantics, and `docs/features.json`, especially F07/F15/F17/F20/F21. No implementation files or test files were changed by this reviewer. Other backend/web work in the shared checkout was excluded.

**Disposition: changes requested.** Three P2 findings below affect accepted period inputs and contracts that later entitlement/document services would otherwise inherit.

## Findings

### [P2] Resolve calendar-day boundaries that fall in a midnight clock gap

Locations: `backend/spesped/domain/primitives.py:144-147`; `backend/spesped/domain/recurrence.py:188-193`.

`SummaryPeriod` and `DraftRecurrence` accept every valid IANA timezone, but create local midnight and pass it through `instant()`, which correctly rejects a nonexistent caller-supplied wall time. In a zone whose daylight-saving transition skips midnight, the domain itself generates that invalid wall time for an otherwise valid date. For `America/Santiago`, a one-day summary for **2026-09-06** is accepted by the constructor but `to_utc()` raises `ValueError`. A daily recurrence anchored on 2026-09-05 likewise raises when advancing to September 6, rather than yielding the next run. This leaves a valid configured schedule stuck and prevents the chosen calendar date from being summarized.

Define a calendar-boundary resolution policy (for example, the first valid instant of the local date) and use it consistently in summaries and recurrences, while continuing to reject invalid explicit occurrence/recorded instants. Alternatively, explicitly constrain accepted school zones before these values are accepted. Verify a midnight transition in addition to Oslo's 02:00/03:00 transitions, including the following boundary and run deduplication.

### [P2] Bind entitlement addition to a decision and subject identity

Location: `backend/spesped/domain/quantities.py:62-70` (missing identity fields at lines 39-45).

`add()` promises to refuse quantities from different decisions, but compares only the reference period, support category, free-text `decision_clause`, and counting basis. Neither quantity carries a decision/revision identity or school/learner scope. Two independently sourced decisions with a common clause label such as `Clause 1` and matching dates are indistinguishable, even if they belong to different pupils or schools, and are combined into a single entitlement. For example, 60 hours from one decision and 30 hours from another become 5,400 minutes without a rejection. A superseding decision with the same textual label can therefore be counted as an additional right instead of a replacement.

Introduce a validated decision/provision reference containing the necessary subject and decision version identity, and require equality before addition; or move aggregation to a policy whose explicit inputs carry and validate those identities. Preserve the existing unit conversion and period/category/basis rejection. This needs agreement before J05/J06/J15 callers rely on this shared type: a caller cannot recover the missing provenance from an `EntitlementQuantity` alone. This finding concerns safe domain aggregation, not a demonstrated HTTP authorization bypass in an implemented service.

### [P2] Provide an ordinary manual draft request without activating a schedule

Locations: `backend/spesped/domain/recurrence.py:80-85`, `203-212`.

The only manual request operation is `DraftRecurrence.request_manual()`, which requires an explicitly activated `MANUAL` schedule. Even directly constructing the returned `DraftRequest` requires a schedule ID and schedule revision. Thus the ordinary F20 action, “create an email for these chosen dates,” has no shared request contract unless a service creates/activates a schedule or invents schedule identifiers. F20 explicitly makes manual ordering the default and a separate recurring schedule opt-in. Its retry identity also needs to distinguish a retry of one manual command from a later intentional request for the same dates.

Provide a separate validated one-off request/command identity with subject, period, requested time and explicit logical request key; keep schedule/revision/period deduplication for recurring requests. If manual requests are deliberately deferred to J11, document that separation and ensure this schedule-only API is not presented as the ordinary manual request contract. The current values never grant dispatch authority; this finding does not claim that activating a manual schedule sends email.

## Verification

All commands below ran from `/Users/lauritz/Programming/SpesPed` with Python 3.12.

```sh
git diff --exit-code 35c613a765f6dfe43e839b3876278068535cf31f -- backend/spesped/domain backend/tests/test_domain_core.py
git diff --stat 7f3d652..35c613a765f6dfe43e839b3876278068535cf31f -- backend/spesped/domain backend/tests/test_domain_core.py
PYTHONPATH=backend /opt/homebrew/bin/python3.12 -m unittest discover -s backend/tests -p test_domain_core.py -v
```

The equality check returned exit 0: the working-tree J02 files tested match the exact final candidate. The required suite passed **25/25** independently. A separate transient inline unittest run passed **6/6** additional checks: cross-learner/school/protected-case and source-revision rejection; occurrence/cutoff/late-entry and confirmed-evidence selection; mutable manifests/spans/evaluated inputs rejected; content mutation invalidation and JSON type distinctions; reference-period/category/basis/clause mismatch rejection; and monthly skip/anchor/end-boundary behavior with no dispatch grant. No temporary production or test file was added.

The following exact transient command reproduced the midnight and manual API issues and inspected the missing entitlement identity fields:

```sh
PYTHONPATH=backend /opt/homebrew/bin/python3.12 - <<'PY'
from datetime import date, datetime, timezone
from dataclasses import fields
from spesped.domain import *
UTC = timezone.utc
scope = SubjectScope(SchoolId.new(), LearnerId.new())
period = SummaryPeriod(date(2026, 9, 6), date(2026, 9, 6), 'America/Santiago')
try:
    period.to_utc()
except ValueError as error:
    print('Accepted summary period fails resolution:', error)
recurrence = DraftRecurrence(ScheduleId.new(), RevisionId.new(), scope,
    DraftCadence.DAYS, date(2026, 9, 5), 'America/Santiago',
    DraftPeriodSelection(PeriodRule.PREVIOUS_DAYS, 7)).activate()
first = recurrence.next_run(datetime(2026, 9, 4, tzinfo=UTC))
try:
    recurrence.next_run(first)
except ValueError as error:
    print('Accepted daily recurrence fails next run:', error)
manual = DraftRecurrence(ScheduleId.new(), RevisionId.new(), scope,
    DraftCadence.MANUAL, date(2026, 1, 1), 'Europe/Oslo',
    DraftPeriodSelection(PeriodRule.MANUAL))
try:
    manual.request_manual(SummaryPeriod(date(2026, 10, 1), date(2026, 10, 20),
                                      'Europe/Oslo'), datetime(2026, 10, 21, tzinfo=UTC))
except ValueError as error:
    print('One-off manual request fails without schedule activation:', error)
print('Entitlement fields:', ', '.join(field.name for field in fields(EntitlementQuantity)))
PY
```

Observed: both Santiago operations raise `A nonexistent local wall time is not an instant`; the manual operation raises `Manual drafts require an explicitly active manual schedule`; entitlement fields are only `amount, unit, reference_period, category, decision_clause, counting_basis`. An earlier inline probe constructed identical-period/category/basis `Clause 1` quantities of 60 and 30 hours and observed `amount=Decimal('5400')`, `unit=MINUTES` from `add()`.

## Verified behavior and limits

The implementation keeps supported evidence **presence** separate from professional attainment: `evaluate_goal_evidence()` returns relevant confirmed evidence IDs and explicitly requires educator judgement. It does not infer a grade or independent mastery. Source manifests reject mixed subject scopes; knowledge cutoff and occurrence time have separate membership roles. The tested JSON content values preserve scalar/object distinctions, and mutation after approval fails a new content match. Approval binds attachment identities/digests, revision, subject, recipient relationship version, purpose, categories/restrictions and channel. No ordinary mutable list/dict payload is retained behind the reviewed frozen wrappers. Monthly clamping retains its original anchor, skipping and end dates work in the tested cases, and draft requests expose no dispatch authority.

This is a domain-core review, not completion evidence for F01-F40. It does not establish live user/guardian authorization, source-object existence, professional authority, school timezone configuration, instrument suitability, transaction isolation, durable idempotency uniqueness, missed-run handling, owner reassignment, real dispatch, current legal correctness, AI correctness or production/PostgreSQL readiness. These values rely on application services for current rights and authoritative references. No service/database/browser/production integration was exercised here. Type-validation and hash probes cover specified cases rather than exhaustive malformed Python objects or cryptographic collision analysis.

Reviewer is ready to recheck the orchestrator's implementation fixes; no commits, pushes or additional agents were created.

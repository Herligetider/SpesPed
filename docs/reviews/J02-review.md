# J02 independent review

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

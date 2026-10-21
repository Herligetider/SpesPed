# Independent document choices review

Reviewed 21 October 2026. Candidate **955e472598c6cb2a6aa404d944896bf7603026f4**. Result: **changes requested**, bounded to the eight choice inventory/router/test files; this is not whole-feature acceptance.

## Findings

1. **[P2] Use pupil participation in actual-delivery labels.** `backend/spesped/contexts/teaching/document_choices.py:22` formats the selected pupil's choice from `revision.duration_minutes` and the aggregate delivery state. Those are session/group facts, not the pupil's participation. A real native HTTP fixture records a 30-minute two-pupil delivery with pupil A participating for 10 minutes. A's choices endpoint returns `Recorded pupil delivery: delivered (30 minutes)`. The inventory exposes no participation minutes that would let the caller distinguish the figures. This misrepresents the pupil's actual work at source selection. Derive the label from the authorized pupil participation projection (handling multiple support categories without double counting), or explicitly identify any displayed duration as the session duration and include the pupil's participation separately. Reproduced on SQLite and PostgreSQL by `test_actual_label_uses_pupil_participation_minutes`.

2. **[P2] Apply accepted narrowing dates before bounding non-text inventories.** `backend/spesped/contexts/documents/choices.py:218` passes only the upper narrowing bound to future plans and always uses the report's end as the lower bound. Although lines 204–205 parse both narrowing dates, the supplied lower bound is ignored. With a report ending 21 October, two single-pupil future plans on 23 and 25 October, and `source_starts_on=source_ends_on=2026-10-25`, the native HTTP response still includes both plans (`total=2`) on both engines. This also prevents lower-date narrowing from recovering an inventory that exceeds the candidate cap. The same dispatch ignores both narrowing dates for actuals and goals; line 203 explicitly instructs these categories to use source narrowing dates in place of text search. Apply the supported bounds in owner SQL before `bounded`, or explicitly reject unsupported category/filter combinations and provide a usable narrowing mechanism. Reproduced by `test_future_lower_narrowing_applied_before_inventory_cap`; the reduced-cap recovery reproduction is recorded separately.

## Pinned evidence and verification

All source and tests ran from `var/review-document-choices/pin`, extracted with `git archive` at the SHA above. All eight archived files match the author's frozen SHA-256 values in `var/j11-documents/owned-choice-hashes.json`. The manifest file SHA-256 is `c98197800b675fbabd0979ab0c181c7440686f2525687c215d84c6cebd7a9806`, matching `choice-results.json`. No implementation fixes, commits, or shared source edits were made.

Every command used `/Users/lauritz/Programming/SpesPed/backend/.venv/bin/python` (Python 3.12), with the absolute environment:

```text
PYTHONPATH=/Users/lauritz/Programming/SpesPed/var/review-document-choices/pin/backend:/Users/lauritz/Programming/SpesPed/var/review-document-choices/pin/backend/tests
SPESPED_TEST_POSTGRES_URL=<assigned localhost PostgreSQL test URL>
```

From the archive directory:

```text
python -m pytest backend/tests/test_document_choices.py backend/tests/test_documents_authorization.py backend/tests/test_bc10_application_composition.py -q --disable-warnings --maxfail=1
```

Result: **32 passed**, 85.08 seconds, exercising both SQLite and PostgreSQL. Log: `var/review-document-choices/focused.txt`.

Independent adverse scenarios in `var/review-document-choices/review_adverse.py` used the real native owner services and HTTP application, not replacement source ports:

```text
python -m pytest /Users/lauritz/Programming/SpesPed/var/review-document-choices/review_adverse.py -q --disable-warnings
```

Result for the initial four scenarios on both engines: **4 passed, 4 failed**, 16.92 seconds. The failures are the two findings above, each on both engines. Log: `var/review-document-choices/adverse.txt`. An additional `-k recovers_cap` run returned **2 failed, 8 deselected**, 5.09 seconds: both engines returned HTTP 422 `choice_limit` despite a one-day narrowing range containing only one eligible plan (test cap reduced to one candidate). Log: `var/review-document-choices/cap.txt`. Passing independent cases confirmed:

- All nine inventory categories preserve a prior flushed caller write and its outer transaction; caller rollback still restores the persisted original name. Reads did not create teaching follow-up records.
- A case-only `documents.write` grant does not put a person into the pupil owner inventory.
- A contributor assignment for a superseded document revision does not appear in the assignment-only inbox.

The author suite additionally verifies current permission revocation, pupil isolation, source-link recall, exact evidence/observation/result/progress/statement coordinates, human reviewed report coverage, historic goal supersession, actual/future classification, single-pupil future prose, durable suggestion recovery across application restart, review outcomes and model/source recall, and contribution-only access without editor grants. The reviewed implementations resolve through owning services rather than treating metadata selection as authorization to compose or disclose.

PostgreSQL runs used only UUID-named fixture schemas with fixture finalizers. No unrelated schemas or shared database state were cleaned up. Browser/UI and implementation-ledger acceptance remain with the orchestrator. The passing narrow suite does not override the two independent adverse findings or establish F18/F20 completion.

## Repair recheck — b39ecb08e16209d7d99ebbb7747bac90a01750ac

Independent recheck completed 21 October 2026. **Both findings are closed; the bounded document-choice repair is accepted.** This changes the original candidate's review disposition only for the implementation inspected below; it does not establish whole-feature or UI acceptance.

A separate `git archive` extraction at `var/review-document-choices/repair-pin` contains the exact repair revision. All eight archived files match `var/j11-documents/owned-choice-repair-hashes.json`. The manifest SHA-256 is `097a0ed90ad28dfcc3cee7fc891a9b0327f4d313254fb8f4376fe573b81faf42`, matching `choice-repair-results.json`. The repair changes only the documents inventory composition, teaching inventory projection and their focused test file among the eight owned files. Runtime imports of `spesped`, the document choices module and fixture modules were explicitly verified beneath the repair archive, with absolute `PYTHONPATH` entries preventing the editable environment from importing the live checkout.

The actual-delivery inventory now describes only the authorized pupil's category, participation state and minutes. Its typed `participation` field preserves separate category entries, and its label explicitly avoids summing potentially overlapping categories. The original 30-minute group/10-minute pupil reproduction now passes. The date narrowing dispatcher now passes validated category bounds to goals, actuals and future plans before the owner SQL candidate cap. Original one-day future filtering and cap-recovery reproductions both pass. Interval/background/future windows and unsupported date-filter categories reject invalid combinations explicitly, while the response preserves the report's original period.

Using the same Python 3.12 interpreter and assigned localhost PostgreSQL URL, from the repair archive:

```text
PYTHONPATH=/Users/lauritz/Programming/SpesPed/var/review-document-choices/repair-pin/backend:/Users/lauritz/Programming/SpesPed/var/review-document-choices/repair-pin/backend/tests
python -m pytest backend/tests/test_document_choices.py backend/tests/test_documents_authorization.py backend/tests/test_bc10_application_composition.py /Users/lauritz/Programming/SpesPed/var/review-document-choices/review_adverse.py -q --disable-warnings --maxfail=1
```

Independent result: **52 passed on SQLite and actual PostgreSQL**, 125.30 seconds. This includes all ten executions of the original reviewer probes, including both cap reproductions. Log: `var/review-document-choices/repair-focused.txt`.

Additional independent native HTTP cases in `var/review-document-choices/repair_adverse.py` passed on both engines:

- An absent pupil has typed `absent` participation and zero minutes, and its choice label does not substitute the group's 30-minute duration. The aggregate delivery remains correctly identified as partial.
- A one-day future-plan range across the Europe/Oslo autumn DST transition includes both distinct 02:30 instants (UTC offsets +02 and +01), excludes the adjacent-day sessions before the candidate cap, preserves the report period, and returns the correct total across two offset pages.

Result: **4 passed**, 10.50 seconds. Log: `var/review-document-choices/repair-adverse.txt`. This run used the same absolute archive backend/test paths, plus the absolute reviewer evidence directory solely to import its helper.

No new actionable finding was found in the changed choice code. All test processes completed normally and fixture finalizers handled their UUID schemas and loopback model servers; no unrelated database cleanup was performed. The separately reported upstream plan approval digest/offset canonicalization issue is outside this choice repair and is not represented as resolved by these checks. UI/browser, implementation ledger and full F18/F20 acceptance remain with the orchestrator.

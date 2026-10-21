# Independent typed IEP gateway review

Initial reviewed pin: `5a76a69923c55ecd2410e1d8599686960ad5e204`.
Final independently accepted repair pin: `8d82b74908bedecdacac330e71fa430a041c3700`.
Previously accepted teaching gateway: `ac555498c0f8741d77d567075913b2e75a173779`.
Review date: 2026-10-21.

## Verdict

**Accepted within the reviewed gateway scope at `8d82b74`; no open findings.**
The fixed-revision P2 is independently verified as repaired at all three entry
points. The new temporary runtime context also passed independent restoration,
nesting and worker checks. The initial candidate's 206 passing regression cases
and final repair's 79 focused passing cases are recorded below.

This review is limited to the typed IEP gateway and shared validation ports.
The real plans-generation consumer is absent at the reviewed pin; its source,
target-goal, selection, activation, lineage, transaction and UI behavior requires
separate independent acceptance. The prior teaching review is unchanged.

The original finding and candidate results below are preserved as historical
evidence. The final repair recheck is recorded at the end.

## P2 — Enforce revision 1 for immutable plan-basis references

Pinned location: `backend/spesped/contexts/platform/contracts.py:91-93`.
The same missing constraint occurs in the new direct guards at
`backend/spesped/contexts/platform/service.py:75-77` and
`backend/spesped/assembly.py:93-95`.

The new contract in `docs/09-domain-implementation.en.md` accepts exactly one
immutable `plan_basis:UUID:1` reference, but `GenerationRequest.subject_scope`
checks only its kind and count. Constructing an otherwise valid `iep_drafting`
request with `SourceRef(kind='plan_basis', source_id=..., revision=2)` succeeds.
The service and assembly guards likewise permit that coordinate and defer it to
the configured resolver. A generic source reference allowing later revisions
should not widen this new purpose's explicitly fixed immutable-basis contract.

Independent desired-behavior probe:
`var/review-iep-gateway/test_independent_iep_probes.py::test_immutable_plan_basis_request_is_fixed_at_revision_one`.
It fails with `DID NOT RAISE ValidationError` at the reviewed pin. Enforce the
fixed revision in the purpose-specific request and direct resolver guards, with
an adverse regression so a future or custom resolver cannot widen the boundary.
This is a boundary validation mismatch, not a demonstrated disclosure through
the absent real plans consumer.

An additional preserved direct-boundary probe in
`var/review-iep-gateway/test_revision_guard_probes.py` independently reproduces
the same finding for the service and assembly paths on both databases: **4
failed** in 4.54 seconds. The service accepts revision 2 when a fixture resolver
returns that exact reference; assembly reaches its unavailable-consumer 503
instead of rejecting the invalid coordinate with 403. The repair must enforce
the contract before either consumer is invoked.

## Isolation and verification

Read `AGENTS.md`, the new docs/09 IEP contract and all seven changed files.
Archived the exact commit to `var/review-iep-gateway/5a76a69`. Every Python and
pytest invocation used an absolute archive-only `PYTHONPATH`, with the archive's
tests directory when needed, and the existing Python 3.12 virtualenv executable.
An explicit probe checks both platform and plans service module paths are inside
that archive and confirms plans has no `resolve_generation_source` port there.
Uncommitted J05 generation and J06 teaching changes in the shared checkout were
excluded. No production edits, commits, pushes, subagents or external AI calls
were made for the review. PostgreSQL fixtures used unique temporary schemas on
the supplied test instance; no demo or unrelated schema was used.

Primary committed-suite command, run from the archived repository root:

```sh
PYTHONPATH=/Users/lauritz/Programming/SpesPed/var/review-iep-gateway/5a76a69/backend:/Users/lauritz/Programming/SpesPed/var/review-iep-gateway/5a76a69/backend/tests \
SPESPED_TEST_POSTGRES_URL=postgresql+psycopg://spesped_test:synthetic-development-only@127.0.0.1:55432/spesped_test \
/Users/lauritz/Programming/SpesPed/backend/.venv/bin/python -m pytest \
backend/tests/test_iep_gateway.py backend/tests/test_teaching_gateway.py \
backend/tests/test_ai_gateway.py backend/tests/test_intake_structuring.py -q --tb=short
```

Result: **206 passed, 7 expected SQLite skips** in 274.52 seconds. The existing
FastAPI/Starlette TestClient deprecation warning remains.

Independent command, using the same archived environment:

```sh
/Users/lauritz/Programming/SpesPed/backend/.venv/bin/python -m pytest \
/Users/lauritz/Programming/SpesPed/var/review-iep-gateway/test_independent_iep_probes.py -q --tb=short
```

Result: **22 passed, 1 failed** in 22.11 seconds. The sole failure is the fixed
revision finding above. The passing independent probes verify:

- Missing real plans source validation returns `plan_generation_unavailable`
  (503), with no accidental import of the shared in-progress consumer.
- The separate `ai.iep_drafting` grant is required for current-result reads and
  idempotent replay; retaining other AI authorities does not substitute for it.
- Resolved school, learner and purpose must match exactly before any wire call.
- Current source content, cache-warmed release recall and cache-warmed evaluation
  artifact mutation block full reads and replay. Metadata eligibility remains
  separate from source or actor permission.
- The typed schema rejects additional rights, hours, curriculum, participation,
  grade and qualification fields; blank/oversized text, boolean target UUIDs,
  missing source references and blank missing-evidence entries fail validation.
  An arbitrary valid target UUID remains an unconfirmed proposal, explicitly
  requiring later real-consumer membership validation against the immutable basis.
- Metadata reads issue SELECTs, select no generation output, preserve a pending
  policy recall without autoflush or overwriting, and recover after owner rollback.
- Synthetic remote metadata eligibility requires development mode, an explicit
  enablement flag and an exact current operator attestation for `iep_drafting`.
  Production mode, withdrawal, wrong purpose and disabled remote development fail
  closed. These checks seed binding metadata only; no remote generation runs.

Committed suites additionally cover typed wire success, durable replay,
unsupported citations, approval/date fields, empty proposals and tool calls;
schema bounds and duplicate goal keys/targets; and reviewed evidence for the
distinct IEP purpose. Shared suites cover current authorization, source and
processing recalls, pending metadata edits/deletes, local production boundaries,
and absence of silent remote fallback.

## Legacy release stability

Independently ran the digest algorithm from archived accepted `ac55549` and the
IEP candidate using identical fixed provider/model values. All three preexisting
release digests match exactly:

| Template | SHA-256 at both pins |
| --- | --- |
| `bounded-suggestion.v1` | `a0aed6acc8d675173cf94fce8403328729a29ac2cec6cf9fb5dcf31e2533f2ae` |
| `intake-structuring.v1` | `0ab69f0c5adba3599cb4508daa5787c57a978e7b214de48509d1c087142529ed` |
| `teaching-session.v1` | `42866d72e1fb76dcf5774ac4da6bba38184b4d5aa47a12c682f83bc51c318557` |

The new `iep-draft.v1` release digest binds only its distinct instructions and
typed schema alongside the existing shared system prompt and provider binding.
No broader teaching or actual plans-generation acceptance is implied.

## Independent repair recheck — 8d82b74

Repair pin: `8d82b74908bedecdacac330e71fa430a041c3700`, archived separately to
`var/review-iep-gateway/8d82b74` and tested with absolute archive-only Python paths.
The original failing probes remain unchanged. A copy of the main independent
probe file changes only the expected archive path for import isolation.

**Final scoped verdict: accepted, finding closed.** The request model, direct
service resolution and assembly resolution now require exactly revision 1 for
`iep_drafting`. The preserved request failure and four direct service/assembly
failures all pass on the repair. Revision 2 is rejected before invoking the real
or fixture source consumer.

The new runtime context addition was also reviewed. `_resolve` temporarily binds
the explicitly supplied trusted `GatewayRuntime` to
`db.info['ai_gateway_runtime']` only while calling the source resolver, then
restores the exact previous key/value in `finally`. It distinguishes an absent
key from `None`. Independent nested calls with a second runtime restore the outer
runtime before the outer resolver continues, then restore the original caller
context. The independent matrix covers success, `DomainError`, unexpected
`RuntimeError` and invalid returned source coordinates for missing, `None` and
opaque-object prior values. All 12 cases pass without a leaked replacement.

Two additional SQLite/PostgreSQL probes use actual fresh worker sessions with a
synthetic lineage resolver. They verify that creation, execution and completion
source checks see the explicitly supplied current runtime despite a stale outer
context, and that a subsequent policy recall still denies current-result access
while restoring the caller context after the error. This verifies the gateway
handoff mechanism, not the absent real generated-plan/teaching lineage consumer.

Focused repair command, from the archived repository root:

```sh
PYTHONPATH=/Users/lauritz/Programming/SpesPed/var/review-iep-gateway/8d82b74/backend:/Users/lauritz/Programming/SpesPed/var/review-iep-gateway/8d82b74/backend/tests \
SPESPED_TEST_POSTGRES_URL=postgresql+psycopg://spesped_test:synthetic-development-only@127.0.0.1:55432/spesped_test \
/Users/lauritz/Programming/SpesPed/backend/.venv/bin/python -m pytest \
backend/tests/test_iep_gateway.py \
/Users/lauritz/Programming/SpesPed/var/review-iep-gateway/test_iep_repair_probes.py \
/Users/lauritz/Programming/SpesPed/var/review-iep-gateway/test_revision_guard_probes.py \
/Users/lauritz/Programming/SpesPed/var/review-iep-gateway/test_runtime_context_probes.py \
backend/tests/test_teaching_gateway.py::test_current_configuration_rechecks_cached_rows_after_recall \
backend/tests/test_teaching_gateway.py::test_source_and_actor_revocation_still_gate_noncommitting_result \
backend/tests/test_ai_gateway.py::test_idempotent_completed_output_requires_current_reviewed_configuration \
backend/tests/test_ai_gateway.py::test_source_authorization_and_revision_rechecked -q --tb=short
```

Result: **79 passed** in 59.59 seconds, no skips. Only the existing TestClient
deprecation warning remains. These rerun current actor/source authorization,
cached policy/release/evaluation recalls, provider and template changes,
idempotent existing-result visibility, remote attestation withdrawal and pending
metadata transaction preservation alongside the fixed guards and new context.

No additional findings were identified. The preceding candidate's broader 206
passing tests remain applicable to unchanged behavior; they were not repeated
wholesale for this targeted repair. Verification used synthetic localhost wire
and unique PostgreSQL schemas only. The reviewer made no production edits,
commits, pushes or external AI calls and stopped edits after this handoff.

Actual plans and teaching consumer implementations, their real cross-context
generation chain, route registration and UI remain separate review scopes. A
successful gateway fixture chain is not acceptance of those consumers.

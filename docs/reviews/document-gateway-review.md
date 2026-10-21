# Independent document gateway review

Reviewed revision: `9f1ba49ee1e2241eaf6f1247dc21e16f3611ff4c` (parent `25ac24e2d1440c9000ea41e3f0c2ca4c2d3c253f`). Reviewer: `/root/review_j11_gateway`, separate from author `/root/j11_gateway`. Review date: 2026-10-21.

## Disposition and boundary

No actionable finding in the six-file candidate. Accept the shared typed document AI gateway boundary within the limits below. This is not acceptance of native BC10 documents, reports/email application, UI, approval, export or dispatch.

The reviewed boundary adds `report_drafting` and `guardian_email_drafting`, restricted to one learner-scoped `document_basis` at revision 1, and maps both to `document-draft.v1`. The schema requires a nullable bounded subject, 1–40 sections with unique bounded keys, bounded text/references/gaps, unique citations per section, and explicit section or global gaps for uncited sections. Extra structured decision, grade, approval, recipient and dispatch fields are rejected. Output stays unconfirmed and requires human review.

Both purposes independently require matching successful evidence in the reviewed evaluation, even though they share a schema. Authorization, processing policy, configured model/release, immutable source manifests, durable attempts, idempotent replay and current-result recall continue through the existing gateway. The new instructions are bound into the new release digest without changing the four existing template digests. The provider rejects model identity mismatches, tool calls, legacy `function_call`, refusal and truncation; there is no new queue or production remote fallback.

## Isolation and identity

Read root `AGENTS.md`. Created an ignored snapshot with:

```sh
mkdir -p var/review-document-gateway
git archive 9f1ba49ee1e2241eaf6f1247dc21e16f3611ff4c | tar -x -C var/review-document-gateway
```

Every test used `/Users/lauritz/Programming/SpesPed/backend/.venv/bin/python` (Python 3.12.13), from the frozen snapshot backend, with absolute override:

```sh
PYTHONPATH=/Users/lauritz/Programming/SpesPed/var/review-document-gateway/backend:/Users/lauritz/Programming/SpesPed/var/review-document-gateway/backend/tests
```

Import origins for assembly, contracts, providers, router, service and `test_document_gateway` were all verified under that snapshot, overriding the editable environment. Each frozen file's bytes were compared with `git show` for the pinned commit, and SHA-256 matched:

| Candidate file under backend | SHA-256 |
| --- | --- |
| `spesped/assembly.py` | `dc538377e88a42747bf21704c4e596544a586cc1f717371aadbfd2859693a4ba` |
| `spesped/contexts/platform/contracts.py` | `c5def939d82f275cda850e97584460abd80f9e193a5f3eaae5d4858761ff7d99` |
| `spesped/contexts/platform/providers.py` | `706b718956aa9a0e2bbcfbd3626b024d6404dc3c782dfa30c244a268eee23d95` |
| `spesped/contexts/platform/router.py` | `949e23a4cee098a0ce8919eda96b22a0afaffd48246b13df021cb22a485f1870` |
| `spesped/contexts/platform/service.py` | `e3a67bdf7c1e0098d0800d5d1911e5ae97cce920b8bc262645688793d92ecad6` |
| `tests/test_document_gateway.py` | `4f35f54755569418ffe351adf9345923e93b4a056419e623d0c8606b062c9af1` |

Uncommitted native documents, main/environment registration and migrations were excluded. The shared checkout advanced during review; this report applies only to the pinned revision.

## Verification

For database tests, `SPESPED_TEST_POSTGRES_URL` pointed to the provided loopback PostgreSQL test database on port 55432. The existing fixture creates a fresh UUID schema for each PostgreSQL case and drops that exact schema in `finally`; SQLite counterparts use isolated temporary files. All model HTTP data was synthetic and used loopback fixture servers. No real learners, external messages or external model calls were used.

Commands below use the frozen working directory and absolute Python/PYTHONPATH above:

| Command after `python -m pytest` | Outcome |
| --- | --- |
| `tests/test_document_gateway.py -q` | **49 passed**, 30.59 seconds; complete candidate suite, including all eight assembly additions, SQLite and actual PostgreSQL. |
| `../test_review_adverse.py -q` (first eight independent tests) | **26 passed**, 26.12 seconds, SQLite and actual PostgreSQL. |
| `../test_review_adverse.py -q -k actual_frozen` | **4 passed**, 26 deselected, 5.13 seconds; actual absent native owner with both purposes and both databases. |
| `tests/test_ai_gateway.py tests/test_iep_gateway.py tests/test_teaching_gateway.py -q` | **156 passed, 7 skipped**, 167.92 seconds; SQLite-only concurrency skips, with actual PostgreSQL counterparts executed. |

Independent adverse checks are retained only in ignored `var/review-document-gateway/test_review_adverse.py`. They check:

- Direct `GenerationRequest.model_copy` misuse bypassing Pydantic validation: empty/duplicate/wrong-kind/revision-2 sources fail without persisting jobs or invoking the provider. Resolver school/learner/purpose misbindings also fail.
- Background execution rechecks the initiating user's purpose authority; revocation fails before the provider call and stores no output.
- Policy purpose removal while the model call is in progress discards the response as unavailable. Policy omission also blocks document evaluation and generation choices.
- Truncation, refusal, legacy function calls and mismatched template/schema do not produce successful typed output.
- Remote production processing remains rejected even for synthetic sources; development requires explicit enablement and trusted synthetic provenance. These checks do not contact a remote endpoint.
- Subject/text types, blank subject, section count, gap/reference count, unknown references and extra approval fields fail. Citation whitespace normalization preserves the known reference rather than introducing a new one.
- Changing current purpose instructions recalls choices, metadata bindings, result reads and idempotent replay.
- The actual frozen assembly, without an import mock, returns `document_generation_unavailable`/503 before model invocation because the native owner is absent.

Initial adverse-run failures were reviewer assertion corrections, not product defects: ORM policy edits increment the policy version and therefore report `processing_policy_unavailable` before the purpose check; bounded strings intentionally trim citation whitespace. Corrected assertions passed on rerun. The initial log is retained for transparency.

Separately archived the exact parent under the same ignored review directory and ran the identical digest calculation in isolated Python processes for parent and candidate. `bounded-suggestion.v1`, `intake-structuring.v1`, `teaching-session.v1` and `iep-draft.v1` configuration digests all match the parent exactly (`parent-digests.log`). No earlier release is silently invalidated by these new purposes.

## Required remaining work and limits

At `assembly.py:103–113`, only absence of `spesped.contexts.documents` or its `generation` module becomes the explicit 503. Internal import defects, runtime errors and access denials propagate; the assembly additions verify those paths and preserve caller runtime context through nested resolution and failures. Trusted operator attestation binds the exact school, learner, purpose, source reference and content digest.

At `contracts.py:188–210` and `providers.py:228–240`, protocol validation establishes shape and known-reference binding. It cannot establish factual truth inside the basis, citation support for each claim, allowed template membership, selected evidence eligibility or subject support. An independent empty-actuals example with an invented success and unsupported subject remains schema-valid but explicitly unconfirmed and review-required. A global gap can satisfy the uncited-section rule. These are limits of the accepted contract, not evidence of professionally correct draft content.

The native document owner must still implement and verify exact frozen basis retrieval, document/template/evidence selection, period/cutoff semantics, professional selection/application, current permissions and source lineage. Actual report/email application, UI, approval/disclosure binding and dispatch remain required and unproven by protocol fixtures. No claim of complete feature delivery, model factual quality or newly verified legal sources follows from this review.

## Cleanup

All final verification commands exited 0, and all reviewer-started test handles were awaited before handoff. Loopback servers use fixture shutdown/close/join; HTTP worker children are reaped by the adapter. PostgreSQL fixture cleanup drops only its own UUID schema and disposes engines. A final read-only schema query found no remaining `j08_%` schemas, and the reviewer pytest/HTTP worker process check found no remaining processes. No source files, branches, commits, services on ports 8000/5173/18878 or other agents' work were changed. Only this new report and ignored `var/review-document-gateway` artifacts are reviewer-owned. Test logs, independent probes and import/hash evidence remain there for reproducibility. The only test warnings were the existing Starlette/httpx deprecation and `ResourceRights.copy` shadowing warning.

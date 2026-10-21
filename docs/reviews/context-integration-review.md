# Context assembly independent review

Implementation candidate: `c1720fc2a9b0a499517fd91b871a01bfeebd8e61`.
Additional integration-test-only candidate: `43180acb5b9e97d91b5cde05c1d7795dcbb4b109`.
Platform dependency rechecked separately at `69c2572944ebb4a5f8ac2fc7d18cf5e0f24d253d`; see `J08-review.md`.

Verdict: **no actionable finding in the reviewed assembly subset**. This is a software composition review, not a claim that F01–F40, F04/F11/F33 or production operation are complete.

## Scope and revision control

Read repository instructions, F33 and shared implementation contracts. Inspected `backend/spesped/assembly.py`, `config.py`, `main.py`, `migrations/env.py`, the merge migration `b1_integrate_contexts`, `tests/test_context_integration.py`, `.env.example` and backend README. Followed the called evidence access/current-revision/excerpt/original-integrity functions and platform contracts, and inspected the HTTP governance evidence binding scenario.

Shared HEAD advanced to `974833166854f74ce89ada5d6c8730fbc08719d8` during independent verification. The assigned assembly implementation files remain byte-for-byte unchanged relative to `c1720fc`; the integration tests remain unchanged relative to `43180ac`. The separate governance dependency was concurrently fixed by its owner; this review assesses its assembled evidence-reference contract and tested flow, not the intrinsic governance implementation or its separate review verdict. No reviewer implementation edit, commit, push, external AI request or real pupil data occurred.

## Evidence actually verified

- **Confirmed learner evidence to AI:** authenticated HTTP note intake, field review, evidence confirmation, synthetic local model evaluation, artifact inspection, explicit model review, job creation and real local-protocol generation succeed. The model receives only the exact current confirmed evidence plus its active controlled excerpt. Attribution, report/observation distinction, certainty and occurrence/recording time survive serialization. A sibling's source paragraph is absent from the teaching payload. An authorized sibling teacher cannot read the other learner's result.
- **Current source authorization:** wrong learner/school/source identities and raw original source substitution are rejected. Correcting confirmed evidence changes its revision/digest and makes old generated output inaccessible. Governance's adapter freezes the current controlled evidence revision/digest and rejects protected-case evidence explicitly until its owning context exists.
- **Raw image intake boundary:** independent probes uploaded a real synthetic PNG, used explicitly synthetic local scanning/OCR fixtures, reviewed and confirmed a learner link, and verified that the intake resolver returns the exact preserved PNG only for `evidence_extraction` with current learner access, intake authority, an active confirmed same-learner link, current source revision and clean scan. A teacher without intake authority, a different school, teaching purpose, wrong revision, missing confirmed link, revoked link, non-clean scan, missing storage and corrupt original all fail. This is a deliberate post-attribution AI OCR path; it does not implement pre-attribution AI structuring.
- **Trusted synthetic attestations:** the integration suite verifies the exact school/learner/reference/purpose/content-digest binding. A mismatched purpose/digest remains school data; corrected evidence cannot retain an old attestation. No HTTP upload assertion can set synthetic provenance. Production/test settings reject remote-development and source-attestation configuration. Default runtime has no configured AI provider and no external fallback.
- **Provider and fixture settings:** production/local endpoint validation is applied at startup and each gateway operation. Public/link-local/hostname/mapped-address and unconfigured private-address endpoints fail the provider boundary. Credentials are secret fields and omitted from API responses. Evaluation configuration is bounded deployment-owned JSON, not source content; image/audio assets must be bounded and confined to its directory. Independent loading covers teaching, document, embedding, image and audio fixtures; an asset symlink escaping the configured directory is rejected. Existing tests additionally reject `..` traversal and writable-by-others config.
- **Governance through the real HTTP adapter:** the additional integration scenario creates a reviewed rule/profile and triggered obligation. A document-only action cannot satisfy it; recorded performed action plus a corrected/stale source binding also cannot satisfy it. Renewed current evidence and performed action permit reviewed fulfillment. This verifies actual composition, rather than only a mock validator.
- **Shared migrations:** all context models are registered; Alembic exposes a single `b1_integrate_contexts` head. A completely isolated PostgreSQL schema upgraded to head, passed Alembic metadata comparison with no pending operations, downgraded to base, and upgraded again to the same 46 tables (including `alembic_version`). No shared demo schema was touched.

## Commands and results

Commands ran from `/Users/lauritz/Programming/SpesPed` using the synthetic PostgreSQL test DSN documented in `J08-review.md`:

```sh
PYTHONPATH=backend backend/.venv/bin/pytest -q backend/tests/test_context_integration.py
PYTHONPATH=backend backend/.venv/bin/pytest -q var/review-j08/test_recheck_assembly.py
PYTHONPATH=backend backend/.venv/bin/python var/review-j08/probe_shared_migration.py
```

- Expanded integration suite: **10 passed**, 9.93 s, exercising both SQLite and isolated PostgreSQL where applicable. The earlier 8-case revision also passed before the test-only expansion.
- Independent assembly adverse checks: **13 passed**, 15.40 s, covering the image-intake requirements and all-capability fixture loading/confinement described above.
- Shared PostgreSQL migration/metadata probe: **passed**, single merged head, no new upgrade operations, successful head/base/head roundtrip and schema cleanup.
- Existing Starlette/httpx TestClient deprecation is the only test warning.

## Explicit limits

Production scanner/OCR installations, production local model hardware/quality, backup/recovery, complete user interfaces and all downstream context adapters remain separate verification. Fixed protocol responses prove orchestration and authorization boundaries; they do not prove professional AI quality or comprehensive injection resistance. Pre-attribution AI structuring, an owned clarification queue and actual protected-case/dictated-audio adapters are future work. The reviewed assembly exposes those missing capabilities as unavailable rather than treating generic learner evidence as protected-case or raw-audio access.

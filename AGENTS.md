# SpesPed implementation collaboration

The user's goal is to implement **all 40 current features**, including their rules,
exceptions, UI, persistence and meaningful verification. Do not redefine completion
as a prototype, CRUD scaffolding, a checklist or a passing narrow test suite.

## Authoritative specifications

- `docs/features.json` is the complete feature specification; keep F01–F40 stable.
- `docs/04-domain-model.en.md` defines the 16 bounded contexts.
- `docs/09-domain-implementation.en.md` defines shared implementation contracts.
- `docs/10-master-plan.en.md` and `docs/implementation-manifest.json` track delivery.
- Legal sources were researched in September 2026. Do not represent that registry
  as newly verified law or silently activate unreviewed legal interpretations.

## Working rules

- Work only in files assigned by the orchestrator. Shared checkout: other agents'
  changes may be present. Never reset, revert, stash or remove their work.
- Agents do not commit, push, spawn further agents or change shared contracts
  without an explicit assignment. Report necessary cross-module changes instead.
- The orchestrator assigns a different reviewer after **every** implementation
  job. A job is not accepted until findings are fixed and the reviewer verifies it.
- Preserve the existing private/self-hosted product direction. Do not create a
  hosted Sites project or publish pupil-facing infrastructure from a worker task.
- Use Python 3.12, FastAPI, SQLAlchemy and PostgreSQL for the backend, React with
  TypeScript for the web client. SQLite is only a test/development convenience;
  PostgreSQL verification is required before declaring production readiness.
- Dependency additions must be locked. Inspect and coordinate shared lockfile
  changes. No broad framework replacement to make one task easier.
- Use synthetic data for development and demonstrations. No real student data,
  secret values, unrestricted mailbox access or external messages in tests.

## Invariants

- Authentication comes from a validated session, never caller-supplied user/role
  headers. Enforce school, learner, case, purpose and assignment scope at retrieval,
  mutation, generation, export and dispatch. Fail closed on unknown rights.
- Protected cases are not ordinary learner notes. Administrative infrastructure
  access is not automatic permission to read pupil content.
- Plans, actual delivery, observations, evidence interpretations and professional
  judgements are distinct. AI cannot invent facts, decide rights or assign grades.
- Content approval binds to an exact revision. Disclosure approval additionally
  binds recipient, purpose, channel and attachments. Recheck rights at dispatch.
- Parent emails use chosen date intervals. Recurring **drafts** are opt-in and
  cannot send automatically. First communication release is guardian-only.
- Production AI must stay on the configured local processing path, including
  extraction, embeddings and speech where used. Never silently fall back remotely.
- Drafts, missing evidence, unresolved rules, unavailable connectors and unknown
  delivery outcomes must remain visibly distinct from success.
- Persist business changes and required audit/outbox records in a transaction;
  use revision checks and explicit retry/idempotency semantics.

## Verification and handoff

Test actual invariants and adverse paths. Report commands, results, changed files,
public contracts and unresolved limits. No test result or manifest label alone
proves an entire feature complete. Documentation is not an implementation.

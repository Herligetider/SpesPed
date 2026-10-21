# Backend and context integration

Requires Python 3.12 and `uv`. Install the exact locked environment with
`uv sync --project backend --locked`. Production uses PostgreSQL with psycopg;
SQLite is a local convenience. The application never creates tables at startup.

Run from the repository root, supplying settings through a private environment
or `.env` (see the root `.env.example`). Apply migrations before serving:

```sh
uv run --project backend spesped migrate
uv run --project backend uvicorn spesped.main:app --host 127.0.0.1 --port 8000
```

Provision the first school and a school leader with explicit dated authority.
The command prompts for a password without echoing it; `--password-env VARIABLE`
can instead read a private environment variable. A bootstrap account receives
explicit `authority.delegate` and identity/learner authorities. A role label
alone never confers those rights.

```sh
uv run --project backend spesped bootstrap \
  --school-name 'School name' --kind public \
  --email 'leader@school.example' --display-name 'School leader'
```

For an empty development database only, opt into entirely synthetic fixtures.
Set `SPESPED_DEMO_PASSWORD` privately to a password of at least 12 characters;
there is no built-in password and no public demo-login endpoint:

```sh
uv run --project backend spesped demo --confirm-synthetic --password-env SPESPED_DEMO_PASSWORD
```

The six fixture accounts use `example.invalid`: `demo.leader`, `demo.other`,
`demo.teacher`, `demo.assistant`, `demo.technical`, `demo.guardian`. There are two
schools and three synthetic pupils. The teacher can read/update one pupil; the
assistant has only brief/observation actions; the technical user and guardian
cannot read pupils. Production settings reject this fixture command.

HTTP clients send an exact configured `Origin` at login and on every write.
Login/me return the CSRF token; writes add `X-CSRF-Token`. Sessions are opaque,
stored only as SHA-256 token hashes, and cookies are HttpOnly/SameSite=Lax with
path `/api`. Production requires Secure cookies, PostgreSQL, an explicit strong
secret and explicit HTTPS origins. Terminate TLS at the private reverse proxy.
No caller-supplied identity or role headers are accepted. Passwords use Argon2id.
Invalid credentials have a common response and durable bounded retry throttling.
The throttle key is atomically inserted before password checking; PostgreSQL
row locks serialize concurrent checks for the same account, including its first
attempt, so parallel failures cannot lose counts.

School dates are inclusive in that school's IANA timezone. Session timestamps
are UTC instants. Membership alone allows school entry. A current assignment
with an exact action or a scoped dated authority is also required for pupil
access. Case authority remains independent. Assistant assignments are restricted
to `brief.read` and `observation.create`; guardians obtain no direct dossier
access. Guardian relationships retain source, dates, restrictions and unresolved
information rights independently of disclosure permissions.

The initial HTTP endpoints and Python contracts follow `docs/09-domain-implementation.en.md`.
Additional identity commands are:

- `POST /api/v1/schools/{school_id}/memberships`: `user_id`, `role`, `valid_from`, `valid_until`.
- `POST .../assignments`: `user_id`, `learner_id`, `actions`, `purpose`, dates.
- `POST .../authorities`: `user_id`, exact `action`, optional `learner_id`/`case_id`, dates.
- `POST .../guardians`: `guardian_user_id`, `learner_id`, `relationship`, `source_reference`,
  `parental_responsibility`, `information_rights`, `restrictions`, dates.
- `GET .../access/{memberships|assignments|authorities|guardians}`: bounded list envelope.
- `PATCH .../access/{kind}/{id}`: `expected_version`, `state` (`active`/`revoked`), dates.

Each management command needs explicit `membership.manage`, `assignment.manage`,
`authority.manage` or `guardian.manage`. Assignment and guardian management can
be scoped to one pupil; lists, counts and updates enforce that same scope. A
manager can revoke or shorten an existing grant without retaining its content
permission. Creating, reactivating or extending assignments or authorities
additionally requires explicit `authority.delegate` or the actor's own exact
authority, covering the target scope and requested validity period. Both the
actor's current membership and authority must cover the whole requested period.
Explicit delegation can issue the first grant for a case; that delegation alone
never permits reading its content. Ordinary case authorization still requires
an exact case match; downstream case modules must validate case ownership.
Thus technical management permission cannot grant itself pupil rights. To change
actions or relationships, revoke the old record and create a new dated record.
Accounts are provisioned through local commands at this stage; account lifecycle,
identity-provider integration and richer school/profile administration remain
future work. No case-content endpoints or protected-case reader permissions exist.

Successful business changes, audit metadata and identity outbox events commit
atomically. Read/denied-request metadata contains identifiers and outcomes only.
The outbox is durable infrastructure for later consumers; this foundation does
not claim to implement event processing or external delivery. Optimistic version
checks operate at the database UPDATE as well as at the HTTP command boundary.

Verify both SQLite and isolated PostgreSQL schemas with a synthetic test DSN:

```sh
SPESPED_TEST_POSTGRES_URL='postgresql+psycopg://USER:PASSWORD@HOST/TEST_DATABASE' \
  uv run --project backend pytest backend/tests -q
```

PostgreSQL tests create/drop uniquely named schemas. They apply the versioned
migration, exercise real HTTP sessions, scope, delegation, expiry, conflicts,
transaction rollback and persistence. Regression cases also cover initial
case delegation, pupil-scoped revocation/list filtering, delegation membership
expiry and simultaneous first-login failures against real PostgreSQL. Without that environment variable,
PostgreSQL cases are explicitly skipped. This subset does not complete F01,
F02, F27 or F34; production operations, restoration, encryption/key management,
full school administration and downstream case/record/disclosure workflows
remain separate jobs.

## Evidence, AI and governance configuration

The assembled application registers identity, evidence, AI and governance routes.
`b1_integrate_contexts` joins their separate migrations into one head. Apply all
migrations before starting the application. Context review results and remaining
findings are tracked in `docs/reviews/`; registration does not establish complete
features or production readiness.

Evidence originals require `SPESPED_EVIDENCE_STORAGE_ROOT`, a private filesystem
directory outside web/static roots. The local adapter creates private directories
and files. `SPESPED_EVIDENCE_CLAMD_SOCKET` selects the local ClamAV Unix socket.
Without a scanner, file uploads remain quarantined. Text entered as a note does
not require malware scanning, but still requires explicit intake authority and
source review. OCR additionally requires `SPESPED_EVIDENCE_OCR_ENABLED=true`,
Tesseract, Poppler's `pdftoppm`, and the configured language data. The root
`.env.example` lists all paths. Missing OCR remains an explicit clarification
state; after configuring local processing the original can be retried.

Intake requires `evidence.intake` authority. Controlled learner information uses
the exact `evidence.read` / `evidence.write` actions. Source originals are never
returned through the ordinary excerpt or AI teaching path. Uploaded files use a
bounded raw request body, `X-Evidence-Filename`, and JSON `X-Evidence-Metadata`;
pupil prose is not placed in the request URL. Typed fields are reviewed before
confirmation, and corrections retain source versions and revoke old excerpt links.
Goal references also require a scoped goal validator from the planning context;
until that adapter is present, a non-null goal reference fails explicitly.

AI providers are operator-configured JSON, for example this local-only setting:

```dotenv
SPESPED_AI_PROVIDERS=[{"key":"local","endpoint":"http://127.0.0.1:8080/v1","capabilities":["generation","embeddings"],"kind":"local_openai"}]
```

This example selects an endpoint; it neither starts a model nor approves its
quality. Additional private addresses must be explicitly included in
`SPESPED_AI_PRIVATE_NETWORKS`. The boundary also rejects public, link-local,
mapped-address and hostname endpoints. Per-provider `api_key` may be supplied in
the private JSON environment setting when the local service requires it; keys
are not returned through the API. Model policies/releases and evaluations require
`platform.manage`. Generation needs current learner access and the exact
`ai.<purpose>` assignment/authority, with purpose matching the staff assignment.

The evidence resolver reads exact current confirmed revisions and their active
controlled excerpts. The model input preserves report/observation type, certainty,
author, occurrence time and recorded time. Changing a source invalidates access
to an old generated result. Raw source IDs cannot be substituted for evidence IDs.
Original-image AI OCR additionally requires intake authority, a current confirmed
learner link and a clean scan; pre-attribution OCR currently uses the local
Tesseract path. Protected case sources and dictated audio need their later owning
context adapters; the generic evidence path does not expose them.

## Synthetic model evaluation and development

Set `SPESPED_AI_EVALUATION_SUITES` to deployment-owned JSON. A minimal example is:

```json
{
  "version": 1,
  "suites": {
    "teaching-norwegian-v1": [
      {
        "name": "synthetic-supported-reading",
        "purpose": "teaching_suggestion",
        "text": "Syntetisk eksempel: eleven leste tre ord med støtte.",
        "required_substrings": [],
        "forbidden_substrings": []
      }
    ]
  }
}
```

This demonstrates the format, not an adequate production evaluation. School-approved
fixtures need representative tasks, uncertainty, conflicting evidence and adverse
instructions. Text fixtures support teaching, document and embedding purposes.
OCR or transcription fixtures use `file` instead of `text`, with `media_type` such
as `image/png` or `audio/wav`. Assets must remain inside the configuration directory,
be at most 2 MB, and contain synthetic material only. Configuration and assets must
not be writable by other users. Each suite must use purposes compatible with the
release being evaluated, with at most 20 cases. The gateway separately limits the
whole evaluation's serialized input and output evidence to 2 MB each, including
binary encoding overhead. Exact model releases require a passing evaluation and
explicit professional quality review before generation is available. Authorized
operators inspect the persisted case inputs and actual outputs through
`GET /api/v1/schools/{school_id}/ai/evaluations/{evaluation_id}`; the review binds
that evidence to the exact release. The paginated evaluation list contains metadata.

External development APIs are disabled by default. Enabling them requires
development mode, `ai_remote_synthetic_development=true`, and a `remote_openai`
provider at the permitted API endpoint. It additionally requires exact source
attestations from an operator-controlled synthetic fixture manifest. Each entry
binds `fixture_name`, `school_id`, `learner_id`, `reference` (kind/id/revision),
allowed `purposes`, and `content_digest` of the canonical resolved model input.
The JSON envelope is `{"version":1,"entries":[...]}`. A trusted fixture loader
must produce these entries only from known synthetic fixtures. There is no upload
flag or HTTP command that turns school data into synthetic data. Changed content
or revision loses the attestation. Changing these startup files requires an app
restart. Production rejects the remote-development and source-attestation settings.

Governance imports the bundled legal register only as unreviewed candidates.
Configured, reviewed school rules create obligations; document uploads do not
prove that an action was performed. The assembled evidence adapter freezes exact
current learner evidence bindings and checks them again at fulfillment. Protected
case identity and case evidence remain unavailable until their owning context
provides a resolver. No local legal interpretation is automatically activated.

The integration suite `backend/tests/test_context_integration.py` exercises actual
HTTP intake → field review → confirmed excerpt → reviewed local-protocol AI job →
source correction, including sibling separation and result invalidation on both
SQLite and isolated PostgreSQL. Synthetic protocol responses verify orchestration,
not the quality of a real deployed model.

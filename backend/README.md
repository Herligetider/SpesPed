# Backend foundation

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
`authority.manage` or `guardian.manage`. Creating or reactivating assignments or
authorities additionally requires explicit `authority.delegate` or the actor's
own exact authority, covering the target scope and requested validity period.
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
transaction rollback and persistence. Without that environment variable,
PostgreSQL cases are explicitly skipped. This subset does not complete F01,
F02, F27 or F34; production operations, restoration, encryption/key management,
full school administration and downstream case/record/disclosure workflows
remain separate jobs.

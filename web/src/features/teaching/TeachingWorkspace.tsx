import { useRef, useState } from "react";
import type { FormEvent } from "react";
import type {
  WorkspaceProps,
  Basis,
  FollowUp,
  Session,
  SessionField,
} from "./types";
import { fields } from "./types";
import {
  allPages,
  CommandStatus,
  displayDate,
  Field,
  pretty,
  ReadStatus,
  useCommand,
  useRead,
} from "./runtime";
import AssistantInbox from "./Assignments";
import Briefs from "./Briefs";
import CreateSession from "./CreateSession";
import Deliveries from "./Deliveries";
import Observations from "./Observations";
import SessionEditor from "./SessionEditor";
import Suggestions from "./Suggestions";
import "./teaching.css";
const clients = new WeakMap<object, number>();
let nextClient = 1;
function clientKey(client: object) {
  let key = clients.get(client);
  if (!key) {
    key = nextClient++;
    clients.set(client, key);
  }
  return key;
}
export default function TeachingWorkspace(props: WorkspaceProps) {
  return (
    <ScopedWorkspace
      key={`${clientKey(props.client)}:${props.schoolId}:${props.mode}:${props.learnerId ?? ""}:${props.currentUser.id}`}
      {...props}
    />
  );
}
function ScopedWorkspace(props: WorkspaceProps) {
  const schools = useRead(() => props.client.schools(), [props.client]);
  const school = schools.value?.find((s) => s.id === props.schoolId);
  return (
    <div className="teaching-workspace" lang={props.language}>
      <ReadStatus {...schools} formatError={props.formatError} />
      {school &&
        (props.mode === "assistant" ? (
          <AssistantInbox {...props} zone={school.timezone} />
        ) : props.learnerId ? (
          <TeacherWorkspace
            key={props.learnerId}
            {...props}
            learnerId={props.learnerId}
            zone={school.timezone}
          />
        ) : (
          <p>Velg en elev for å planlegge undervisning.</p>
        ))}
    </div>
  );
}
type TeacherProps = WorkspaceProps & {
  learnerId: string;
  zone: string;
  active?: boolean;
};
export function SessionView({ row, zone }: { row: Session; zone: string }) {
  return (
    <article>
      <h3>
        {row.content?.title ?? "Økt trenger ny kontroll"} · revisjon{" "}
        {row.revision}
      </h3>
      <p>
        {displayDate(row.planned_at, zone)} · planlagt {row.duration_minutes}{" "}
        minutter ·{" "}
        {row.approved
          ? "Godkjent eksakt revisjon"
          : row.state === "in_review"
            ? "Faglig gjennomgått"
            : row.state === "review_required"
              ? "Trenger ny kontroll"
              : "Utkast"}
      </p>
      <p>
        Faktisk gjennomføring:{" "}
        {{
          not_recorded: "ikke registrert",
          delivered: "registrert",
          partial: "delvis registrert",
          cancelled: "avlyst",
        }[row.delivery_state] ?? "uavklart"}
        . Plan og godkjenning dokumenterer ikke gjennomføring.
      </p>
      {row.content ? (
        <dl>
          {fields
            .filter((f) => f.key !== "title")
            .map(({ key, label }) => (
              <div key={key}>
                <dt>{label}</dt>
                <dd className="teaching-pre">{pretty(row.content![key])}</dd>
              </div>
            ))}
        </dl>
      ) : (
        <p role="alert">
          Grunnlag, mål eller modellavhengighet har endret seg. Kildeavledet
          innhold er utilgjengelig frem til ny kontroll med gjeldende grunnlag.
          Tidligere tekst hentes ikke fra nettleserutkast.
        </p>
      )}
    </article>
  );
}
function BasisView({ props, row }: { props: TeacherProps; row: Session }) {
  const basis = useRead(
    () =>
      props.client.schoolGet<Basis>(props.schoolId, [
        "teaching",
        "bases",
        row.basis_id,
      ]),
    [props.client, props.schoolId, row.basis_id],
  );
  type Snapshot = {
    theme: string;
    arena: string;
    materials: string[];
    missing_information: string[];
    learners: {
      goals: { goal: { title: string; expected_action: string } }[];
      profile?: { content: string }[];
      evidence?: {
        content: string;
        reporter: string;
        revision: number;
        source: { page: number; revision: number };
      }[];
      observations?: { observation: string; support: string }[];
      source_bindings?: unknown[];
    }[];
  };
  const snapshot = basis.value?.basis as Snapshot | undefined;
  return (
    <details>
      <summary>Kontroller brukt grunnlag</summary>
      <ReadStatus {...basis} formatError={props.formatError} />
      {snapshot ? (
        <>
          <p>
            Tema: {snapshot.theme || "ikke oppgitt"} · Arena: {snapshot.arena}
          </p>
          <p>
            Tilgjengelig materiell:{" "}
            {snapshot.materials.join(", ") || "ikke oppgitt"}
          </p>
          {snapshot.learners.map((learner, i) => (
            <div key={i}>
              <ul>
                {learner.goals.map((g, j) => (
                  <li key={j}>
                    {g.goal.title} · {g.goal.expected_action}
                  </li>
                ))}
              </ul>
              {learner.profile?.map((p, j) => (
                <p key={j}>Bekreftet støtte: {p.content}</p>
              ))}
              {learner.observations?.map((o, j) => (
                <p key={j}>
                  Observasjon: {o.observation} · Støtte: {o.support}
                </p>
              ))}
              {learner.evidence?.map((e, j) => (
                <p key={j}>
                  Valgt kilde: {e.content}
                  <br />
                  {e.reporter} · opplysningsrevisjon {e.revision}, kilde{" "}
                  {e.source.revision}, side {e.source.page}
                </p>
              ))}
              <p>
                {learner.source_bindings?.length ?? 0} eksplisitte
                kildekoblinger. Referansene er bundet til eksakte revisjoner.
              </p>
            </div>
          ))}
          {snapshot.missing_information.length > 0 && (
            <>
              <h4>Manglende eller motstridende grunnlag</h4>
              <ul>
                {snapshot.missing_information.map((item, i) => (
                  <li key={i}>{item}</li>
                ))}
              </ul>
            </>
          )}
        </>
      ) : (
        basis.value && (
          <p role="alert">Grunnlaget trenger ny kontroll og er skjermet.</p>
        )
      )}
    </details>
  );
}
function SessionHistory({ props, row }: { props: TeacherProps; row: Session }) {
  const history = useRead(
    () =>
      allPages<Session>(props.client, props.schoolId, [
        "teaching",
        "sessions",
        row.id,
        "revisions",
      ]),
    [props.client, props.schoolId, row.id, row.revision_id],
  );
  return (
    <details>
      <summary>Lagret revisjonshistorikk</summary>
      <ReadStatus {...history} formatError={props.formatError} />
      {history.value?.map((s) => (
        <div className="teaching-card" key={s.revision_id}>
          <SessionView row={s} zone={props.zone} />
        </div>
      ))}
    </details>
  );
}
function CurrentSession(
  props: TeacherProps & { row: Session; onUpdated: (row: Session) => void },
) {
  const { row, client, schoolId, formatError } = props;
  // The edit buffer belongs to the revision the user opened. A fresh server
  // projection must never become a new buffer merely because its version changed.
  const [editBase, setEditBase] = useState(row);
  const [commandBase, setCommandBase] = useState(row);
  const [published, setPublished] = useState<Session>();
  const [draft, setDraft] = useState(row.content);
  const draftRef = useRef(draft);
  draftRef.current = draft;
  const [reason, setReason] = useState("");
  const [replacements, setReplacements] = useState<SessionField[]>([]);
  const [reviewReason, setReviewReason] = useState("");
  const [conflicted, setConflicted] = useState(false);
  const competing = useRead(
    () =>
      conflicted
        ? client.schoolGet<Session>(schoolId, ["teaching", "sessions", row.id])
        : Promise.resolve(undefined),
    [client, schoolId, row.id, row.version, row.source_status, conflicted],
  );
  const command = useCommand(client, schoolId, formatError, () => {
    setConflicted(true);
    competing.reload();
  });
  const observed =
    row.content === null || !published || row.version >= published.version
      ? row
      : published;
  // A failed conflict read is unknown, not permission to expose the old source.
  const current = conflicted ? competing.value : observed;
  const comparisonRequired =
    !!current &&
    (current.version !== commandBase.version ||
      current.revision_id !== commandBase.revision_id);
  const historicalBuffer =
    !!current && current.revision_id !== editBase.revision_id;
  const bufferSource = useRead(
    () =>
      current?.content && historicalBuffer && draft
        ? allPages<Session>(client, schoolId, [
            "teaching",
            "sessions",
            row.id,
            "revisions",
          ]).then((revisions) =>
            revisions.find(
              (revision) => revision.revision_id === editBase.revision_id,
            ),
          )
        : Promise.resolve(undefined),
    [
      client,
      schoolId,
      row.id,
      current?.version,
      current?.revision_id,
      current?.source_status,
      editBase.revision_id,
      historicalBuffer,
      row,
      props.active,
    ],
  );
  const draftAvailable =
    !!current?.content &&
    current.source_status === "current" &&
    (!historicalBuffer ||
      (!!bufferSource.value?.content &&
        bufferSource.value.source_status === "current"));
  const dirty = JSON.stringify(draft) !== JSON.stringify(current?.content);
  const targetLineage = current?.field_job_ids ?? commandBase.field_job_ids;
  const lineage = Object.fromEntries(
    fields.map(({ key }) => [
      key,
      [
        ...new Set([
          ...(editBase.field_job_ids[key] ?? []),
          ...(targetLineage[key] ?? []),
        ]),
      ],
    ]),
  );
  const independentFields = fields
    .filter(({ key }) =>
      (editBase.field_job_ids[key] ?? []).some(
        (job) => !(targetLineage[key] ?? []).includes(job),
      ),
    )
    .map((field) => field.key);
  const missingReplacements = independentFields.filter(
    (field) => !replacements.includes(field),
  );
  function useCurrent(next: Session) {
    setPublished(next);
    setCommandBase(next);
    setEditBase(next);
    setDraft(next.content);
    setReason("");
    setReviewReason("");
    setReplacements([]);
    setConflicted(false);
  }
  function applied(next: Session, submitted = draft) {
    setPublished(next);
    // A late success cannot discard edits made after that command was started.
    if (draftRef.current === submitted && next.content !== null)
      useCurrent(next);
    props.onUpdated(next);
  }
  function save(event: FormEvent) {
    event.preventDefault();
    if (
      !draft ||
      !draftAvailable ||
      comparisonRequired ||
      conflicted ||
      missingReplacements.length
    )
      return;
    const submitted = draft;
    command.run<Session>(
      ["teaching", "sessions", row.id, "revisions"],
      {
        expected_version: commandBase.version,
        basis_id: commandBase.basis_id,
        owner_id: commandBase.owner_id,
        content: draft,
        reason,
        manual_replacements: replacements,
      },
      (next) => applied(next, submitted),
    );
  }
  function review(kind: "review" | "approve") {
    if (
      !current ||
      !draftAvailable ||
      comparisonRequired ||
      conflicted ||
      dirty
    )
      return;
    const submitted = draft;
    command.run<Session>(
      ["teaching", "sessions", row.id, kind],
      {
        expected_version: current.version,
        revision_id: current.revision_id,
        content_digest: current.content_digest,
        reason: reviewReason,
      },
      (next) => applied(next, submitted),
    );
  }
  return (
    <section>
      {current ? (
        <>
          <SessionView row={current} zone={props.zone} />
          <BasisView
            key={`basis:${current.id}:${current.revision_id}:${current.source_status}`}
            props={props}
            row={current}
          />
          <SessionHistory
            key={`history:${current.id}:${current.revision_id}:${current.source_status}`}
            props={props}
            row={current}
          />
        </>
      ) : (
        <p role="status">
          Gjeldende økt kontrolleres. Tidligere kildeavledet tekst er skjermet
          inntil kontrollen er fullført.
        </p>
      )}
      {draft && (
        <div hidden={!draftAvailable}>
          <details>
            <summary>Rediger økten som ny revisjon</summary>
            <p>
              Eget utkast fra revisjon {editBase.revision}. Lagret gjeldende
              innhold vises over.
            </p>
            <form onSubmit={save}>
              <fieldset disabled={command.busy || command.uncertain}>
                <legend>Manuelle endringer</legend>
                <SessionEditor
                  value={draft}
                  onChange={setDraft}
                  lineage={lineage}
                  replacements={replacements}
                  onReplacements={setReplacements}
                />
                <Field label="Begrunnelse for ny revisjon">
                  <textarea
                    required
                    maxLength={2000}
                    value={reason}
                    onChange={(event) => setReason(event.target.value)}
                  />
                </Field>
                {missingReplacements.length > 0 && (
                  <p role="alert">
                    Tidligere modellavhengighet finnes ikke i gjeldende
                    revisjon. Skriv selvstendig erstatning og marker de berørte
                    feltene før lagring.
                  </p>
                )}
                <button
                  type="submit"
                  disabled={
                    comparisonRequired ||
                    conflicted ||
                    !draftAvailable ||
                    missingReplacements.length > 0
                  }
                >
                  Lagre ny øktrevisjon
                </button>
              </fieldset>
            </form>
          </details>
          <fieldset
            disabled={
              command.busy ||
              command.uncertain ||
              dirty ||
              comparisonRequired ||
              conflicted ||
              !draftAvailable
            }
          >
            <legend>
              Faglig kontroll av lagret revisjon {current?.revision}
            </legend>
            <p>
              Kontrollen gjelder bare det lagrede innholdet vist over.
              Gjennomgang og godkjenning er separate handlinger.
            </p>
            <Field label="Begrunnelse for kontroll og godkjenning">
              <textarea
                maxLength={2000}
                value={reviewReason}
                onChange={(event) => setReviewReason(event.target.value)}
              />
            </Field>
            <button
              type="button"
              disabled={!reviewReason.trim() || current?.state !== "draft"}
              onClick={() => review("review")}
            >
              Bekreft faglig gjennomgang
            </button>
            <button
              type="button"
              disabled={!reviewReason.trim() || current?.state !== "in_review"}
              onClick={() => review("approve")}
            >
              Godkjenn denne revisjonen for gjennomføring
            </button>
          </fieldset>
          {dirty && (
            <p>
              Du har ulagrede endringer. Lagre dem før faglig kontroll eller
              modellvurdering.
            </p>
          )}
          {current && (
            <Suggestions
              {...props}
              session={current}
              draft={draft}
              hasUnsaved={
                dirty || comparisonRequired || conflicted || !draftAvailable
              }
              onSaved={(next) => applied(next, draft)}
              onConflict={() => setConflicted(true)}
            />
          )}
        </div>
      )}
      {draft && !draftAvailable && (
        <button type="button" disabled>
          Lagre ny øktrevisjon
        </button>
      )}
      {historicalBuffer && (
        <div>
          <ReadStatus {...bufferSource} formatError={formatError} />
          {!draftAvailable && (
            <p role="alert">
              Det tidligere utkastets kildegrunnlag er ikke bekreftet
              tilgjengelig. Egen tekst beholdes, men kildeavledet innhold er
              skjermet.
            </p>
          )}
          {!!bufferSource.error && (
            <button type="button" onClick={bufferSource.reload}>
              Kontroller utkastgrunnlaget igjen
            </button>
          )}
        </div>
      )}
      {(comparisonRequired || conflicted) && (
        <section role="alert">
          <h4>
            En annen registrering eller kildeendring konkurrerer med utkastet
          </h4>
          <p>
            Utkastet ditt fra revisjon {editBase.revision} beholdes. Sammenlign
            med gjeldende lagret revisjon før du velger hvordan endringen skal
            innarbeides.
          </p>
          {conflicted && (
            <ReadStatus {...competing} formatError={formatError} />
          )}
          <button
            type="button"
            onClick={() => {
              setConflicted(true);
              competing.reload();
            }}
          >
            Kontroller gjeldende versjon
          </button>
          {current?.content && (
            <>
              <button
                type="button"
                disabled={!draftAvailable || command.busy || command.uncertain}
                onClick={() => {
                  setPublished(current);
                  setCommandBase(current);
                  setConflicted(false);
                }}
              >
                Jeg har sammenlignet og vil lagre eget utkast mot denne
                gjeldende versjonen
              </button>
              <button
                type="button"
                disabled={command.busy || command.uncertain}
                onClick={() => useCurrent(current)}
              >
                Forkast eget utkast og bruk gjeldende lagret revisjon
              </button>
            </>
          )}
        </section>
      )}
      {current?.content === null && (
        <details>
          <summary>
            Velg gjeldende grunnlag og skriv en ny manuell øktrevisjon
          </summary>
          <p>
            Tidligere kildeavledet tekst er skjermet. Velg aktive mål og
            aktuelle kilder, skriv selvstendige praktiske felt og bekreft
            uttrykkelig hvilke avhengigheter som erstattes. Denne flaten gjelder
            én elev; en endret elevgruppe krever en egen økt.
          </p>
          <CreateSession
            {...props}
            revise={current}
            onCreated={(next) => applied(next, draft)}
          />
        </details>
      )}
      <CommandStatus command={command} />
      {current?.content && <Briefs {...props} session={current} />}
    </section>
  );
}

function FollowUpForm({
  props,
  row,
  onSaved,
}: {
  props: TeacherProps;
  row: FollowUp;
  onSaved: () => void;
}) {
  const [resolution, setResolution] = useState("");
  const command = useCommand(props.client, props.schoolId, props.formatError);
  return (
    <article className="teaching-card">
      <h4>
        {{
          basis_changed: "Grunnlag eller økt må kontrolleres",
          guidance_required: "Veiledning trengs",
          delivery_deviation: "Gjennomføringsavvik",
          staffing_unassessed: "Uavklart bemanning",
        }[row.reason_code] ?? "Oppfølgingsbehov"}
      </h4>
      <p>
        Ansvarlig:{" "}
        {row.owner_name ??
          (row.owner_id === props.currentUser.id
            ? props.currentUser.display_name
            : "utpekt ansvarlig pedagog")}
      </p>
      <p>
        {row.action ??
          "Kildegrunnlaget trenger kontroll; tidligere beskrivelse er skjermet."}
      </p>
      {row.state === "resolved" ? (
        <p>Lukket: {row.resolution ?? "Kildegrunnlag trenger kontroll"}</p>
      ) : (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            command.run(
              ["teaching", "follow-ups", row.id, "resolve"],
              { expected_version: row.version, resolution },
              onSaved,
            );
          }}
        >
          <fieldset disabled={command.busy || command.uncertain}>
            <legend>Dokumenter utført oppfølging</legend>
            <Field label="Hva er avklart eller gjort?">
              <textarea
                required
                maxLength={2000}
                value={resolution}
                onChange={(e) => setResolution(e.target.value)}
              />
            </Field>
            <button type="submit">Lukk oppfølgingspunkt</button>
          </fieldset>
          <CommandStatus command={command} />
        </form>
      )}
    </article>
  );
}
function FollowUps(props: TeacherProps) {
  const tasks = useRead(
    () =>
      allPages<FollowUp>(props.client, props.schoolId, [
        "learners",
        props.learnerId,
        "teaching-follow-ups",
      ]),
    [props.client, props.schoolId, props.learnerId, props.active],
  );
  return (
    <section>
      <h3>Ansvarlig oppfølging</h3>
      <ReadStatus {...tasks} formatError={props.formatError} />
      {tasks.value?.length === 0 && (
        <p>Ingen oppfølgingspunkter er registrert.</p>
      )}
      {tasks.value?.map((row) => (
        <FollowUpForm
          key={`${row.id}:${row.version}`}
          props={props}
          row={row}
          onSaved={tasks.reload}
        />
      ))}
    </section>
  );
}
function TeacherWorkspace(props: TeacherProps) {
  const [tab, setTab] = useState("sessions");
  const [opened, setOpened] = useState(["sessions"]);
  const [creating, setCreating] = useState(false);
  const [selected, setSelected] = useState("");
  const [readRevision, setReadRevision] = useState(0);
  const sessions = useRead(
    () =>
      allPages<Session>(props.client, props.schoolId, [
        "learners",
        props.learnerId,
        "teaching-sessions",
      ]),
    [props.client, props.schoolId, props.learnerId],
  );
  const current = useRead(
    () =>
      selected
        ? props.client.schoolGet<Session>(props.schoolId, [
            "teaching",
            "sessions",
            selected,
          ])
        : Promise.resolve(undefined),
    [props.client, props.schoolId, props.learnerId, selected, readRevision],
  );
  const retainedCurrent = useRef<Session | undefined>(undefined);
  if (current.value) retainedCurrent.current = current.value;
  const currentRow =
    retainedCurrent.current?.id === selected
      ? retainedCurrent.current
      : undefined;
  function updated(row: Session) {
    setSelected(row.id);
    setReadRevision((x) => x + 1);
    setCreating(false);
    sessions.reload();
  }
  const tabs = [
    {
      id: "sessions",
      label:
        props.language === "nn" ? "Undervisningsøkter" : "Undervisningsøkter",
    },
    { id: "delivery", label: "Gjennomføring" },
    {
      id: "observations",
      label: props.language === "nn" ? "Observasjonar" : "Observasjoner",
    },
    {
      id: "followups",
      label: props.language === "nn" ? "Oppfølging" : "Oppfølging",
    },
  ];
  return (
    <>
      <h2>Undervisning · {props.learnerName ?? "valgt elev"}</h2>
      <nav className="teaching-tabs" aria-label="Undervisningsarbeid">
        {tabs.map((t) => (
          <button
            type="button"
            key={t.id}
            aria-pressed={tab === t.id}
            onClick={() => {
              if (t.id === "sessions" && tab !== "sessions") {
                current.reload();
                sessions.reload();
              }
              setTab(t.id);
              setOpened((previous) =>
                previous.includes(t.id) ? previous : [...previous, t.id],
              );
            }}
          >
            {t.label}
          </button>
        ))}
      </nav>
      <div hidden={tab !== "sessions"} data-teaching-view="sessions">
        <div className="teaching-actions">
          <button type="button" onClick={() => setCreating(!creating)}>
            {creating ? "Lukk nytt øktutkast" : "Planlegg ny økt"}
          </button>
          <button
            type="button"
            onClick={() => {
              sessions.reload();
              setReadRevision((x) => x + 1);
            }}
          >
            Kontroller lagrede økter på nytt
          </button>
        </div>
        {creating && (
          <CreateSession
            {...props}
            active={tab === "sessions"}
            onCreated={updated}
          />
        )}
        <ReadStatus {...sessions} formatError={props.formatError} />
        {sessions.value?.length === 0 && (
          <p>Ingen lagrede undervisningsøkter.</p>
        )}
        <div className="teaching-list">
          {sessions.value?.map((row) => (
            <button
              type="button"
              key={row.id}
              aria-pressed={selected === row.id}
              onClick={() => {
                setSelected(row.id);
                setReadRevision((x) => x + 1);
              }}
            >
              {row.content?.title ?? "Trenger ny kontroll"} ·{" "}
              {displayDate(row.planned_at, props.zone)} · revisjon{" "}
              {row.revision} · {row.approved ? "godkjent" : "ikke godkjent"}
            </button>
          ))}
        </div>
        <ReadStatus {...current} formatError={props.formatError} />
        {currentRow && (
          <div hidden={current.loading || !!current.error || !current.value}>
            <CurrentSession
              key={currentRow.id}
              {...props}
              row={currentRow}
              active={tab === "sessions"}
              onUpdated={updated}
            />
          </div>
        )}
      </div>
      {opened.includes("delivery") && (
        <div hidden={tab !== "delivery"} data-teaching-view="delivery">
          <Deliveries
            {...props}
            session={current.value}
            active={tab === "delivery"}
            onChanged={() => {
              sessions.reload();
              current.reload();
            }}
          />
        </div>
      )}
      {opened.includes("observations") && (
        <div hidden={tab !== "observations"} data-teaching-view="observations">
          <Observations
            {...props}
            session={current.value}
            active={tab === "observations"}
          />
        </div>
      )}
      {opened.includes("followups") && (
        <div hidden={tab !== "followups"} data-teaching-view="followups">
          <FollowUps {...props} active={tab === "followups"} />
        </div>
      )}
    </>
  );
}

import { useState } from "react";
import type { FormEvent } from "react";
import type {
  WorkspaceProps,
  Assignment,
  Brief,
  BriefContent,
  Person,
  Session,
} from "./types";
import {
  allPages,
  CommandStatus,
  DateField,
  displayDate,
  Field,
  instant,
  lines,
  ReadStatus,
  useCommand,
  useRead,
} from "./runtime";
import { AssignmentPanel, BriefView } from "./Assignments";
type Props = WorkspaceProps & {
  learnerId: string;
  session: Session;
  zone: string;
};
const emptyBrief = (): BriefContent => ({
  simple_goal: "",
  material_location: "",
  steps: ["", "", ""],
  support: "",
  simplification: "",
  help_when: "",
  contact: "",
  training_guidance: "",
});
function NewBrief(props: Props & { onSaved: () => void; replaces?: Brief }) {
  const [content, setContent] = useState<BriefContent>(
    props.replaces?.content ?? emptyBrief(),
  );
  const [template, setTemplate] = useState("practical");
  const [error, setError] = useState("");
  const command = useCommand(props.client, props.schoolId, props.formatError);
  function submit(event: FormEvent) {
    event.preventDefault();
    const cleaned = { ...content, steps: lines(content.steps.join("\n")) };
    if (cleaned.steps.length < 3 || cleaned.steps.length > 5) {
      setError("Kortet må ha tre til fem konkrete hovedsteg.");
      return;
    }
    setError("");
    command.run(
      ["teaching", "briefs"],
      {
        session_revision_id: props.session.revision_id,
        learner_id: props.learnerId,
        template,
        content: cleaned,
        replaces_brief_id: props.replaces?.id ?? null,
      },
      props.onSaved,
    );
  }
  return (
    <form onSubmit={submit}>
      <fieldset disabled={command.busy || command.uncertain}>
        <legend>
          {props.replaces
            ? "Lag nytt kort som erstatter tidligere kort"
            : "Nytt praktisk assistentkort"}
        </legend>
        <p>
          Hold kortet kort nok til å forstå på omtrent fem minutter. Dette må
          prøves med faktiske assistenter, og erstatter ikke nødvendig
          opplæring.
        </p>
        <Field label="Kortmal">
          <select
            value={template}
            onChange={(e) => setTemplate(e.target.value)}
          >
            <option value="practical">Praktiske steg</option>
            <option value="visual_support">Visuell støtte</option>
            <option value="guided_practice">Veiledet øving</option>
          </select>
        </Field>
        {(
          [
            { key: "simple_goal", label: "Mål i enkelt språk", max: 1000 },
            {
              key: "material_location",
              label: "Materiell og hvor det finnes",
              max: 1500,
            },
            {
              key: "steps",
              label: "Tre til fem hovedsteg – ett per linje",
              max: 10000,
            },
            { key: "support", label: "Hvordan avtalt støtte gis", max: 2000 },
            { key: "simplification", label: "Avtalt forenkling", max: 1500 },
            {
              key: "help_when",
              label: "Når skal assistenten hente hjelp?",
              max: 1500,
            },
            { key: "contact", label: "Kontaktperson og kontaktvei", max: 500 },
            {
              key: "training_guidance",
              label: "Nødvendig opplæring og veiledning",
              max: 1500,
            },
          ] as const
        ).map((field) => (
          <Field key={field.key} label={field.label}>
            <textarea
              required
              maxLength={field.max}
              value={
                field.key === "steps"
                  ? content.steps.join("\n")
                  : content[field.key]
              }
              onChange={(e) =>
                setContent({
                  ...content,
                  [field.key]:
                    field.key === "steps"
                      ? e.target.value.split("\n")
                      : e.target.value,
                })
              }
            />
          </Field>
        ))}
        <button type="submit">Lagre kort til kontroll</button>
      </fieldset>
      {error && <p role="alert">{error}</p>}
      <CommandStatus command={command} />
    </form>
  );
}
function ManageBrief(props: Props & { brief: Brief; onChanged: () => void }) {
  const { brief, client, schoolId, learnerId, zone, formatError } = props;
  const [reviewReason, setReviewReason] = useState("");
  const [assistant, setAssistant] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [role, setRole] = useState("");
  const [error, setError] = useState("");
  const [selected, setSelected] = useState("");
  const [replacing, setReplacing] = useState(false);
  const staff = useRead(
    () =>
      allPages<Person>(
        client,
        schoolId,
        ["learners", learnerId, "teaching-staff"],
        new URLSearchParams({ purpose: "assistant" }),
      ),
    [client, schoolId, learnerId],
  );
  const assignments = useRead(
    () =>
      allPages<Assignment>(client, schoolId, [
        "teaching",
        "briefs",
        brief.id,
        "assignments",
      ]),
    [client, schoolId, brief.id, brief.version],
  );
  const command = useCommand(client, schoolId, formatError, props.onChanged);
  function review(event: FormEvent) {
    event.preventDefault();
    command.run<Brief>(
      ["teaching", "briefs", brief.id, "review"],
      {
        expected_version: brief.version,
        content_digest: brief.content_digest,
        reason: reviewReason,
      },
      props.onChanged,
    );
  }
  function assign(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      const from = instant(start, zone),
        until = instant(end, zone);
      if (from >= until)
        throw new Error("Tildelingen trenger en slutt etter starten.");
      command.run(
        ["teaching", "briefs", brief.id, "assignments"],
        {
          expected_version: brief.version,
          assistant_id: assistant,
          valid_from: from,
          valid_until: until,
          role,
        },
        () => {
          assignments.reload();
          setSelected("");
        },
      );
    } catch (err) {
      setError(formatError(err));
    }
  }
  return (
    <article className="teaching-card">
      <h4>
        Assistentkort ·{" "}
        {brief.state === "review_required"
          ? "trenger ny kontroll"
          : brief.state === "approved"
            ? "kontrollert"
            : "utkast"}
      </h4>
      {brief.content ? (
        <BriefView content={brief.content} />
      ) : (
        <p role="alert">
          Kildeavledet kort er utilgjengelig etter endret grunnlag. Lag et nytt
          kort fra gjeldende godkjent økt.
        </p>
      )}
      {brief.content && brief.state !== "approved" && (
        <form onSubmit={review}>
          <fieldset disabled={command.busy || command.uncertain}>
            <legend>Kontroll av nøyaktig lagret kort</legend>
            <Field label="Begrunnelse for kortkontroll">
              <textarea
                required
                maxLength={2000}
                value={reviewReason}
                onChange={(e) => setReviewReason(e.target.value)}
              />
            </Field>
            <button type="submit">Bekreft kontrollert kort</button>
          </fieldset>
        </form>
      )}
      {brief.content && brief.state === "approved" && (
        <form onSubmit={assign}>
          <fieldset disabled={command.busy || command.uncertain}>
            <legend>Datert tildeling</legend>
            <ReadStatus {...staff} formatError={formatError} />
            <Field label="Assistent">
              <select
                required
                value={assistant}
                onChange={(e) => setAssistant(e.target.value)}
              >
                <option value="">Velg assistent</option>
                {staff.value?.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.display_name}
                  </option>
                ))}
              </select>
            </Field>
            <DateField
              label="Tilgang fra"
              zone={zone}
              value={start}
              onChange={setStart}
            />
            <DateField
              label="Tilgang til"
              zone={zone}
              value={end}
              onChange={setEnd}
            />
            <Field label="Avgrenset oppdrag og rolle">
              <textarea
                required
                maxLength={500}
                value={role}
                onChange={(e) => setRole(e.target.value)}
              />
            </Field>
            <button type="submit">Tildel kontrollert kort</button>
          </fieldset>
        </form>
      )}
      {props.session.approved && (
        <button type="button" onClick={() => setReplacing(!replacing)}>
          Erstatt med nytt kontrollert kort
        </button>
      )}
      {replacing && (
        <NewBrief
          {...props}
          replaces={brief}
          onSaved={() => {
            setReplacing(false);
            props.onChanged();
          }}
        />
      )}
      <ReadStatus {...assignments} formatError={formatError} />
      {assignments.value?.map((a) => (
        <div className="teaching-card" key={a.id}>
          <p>
            {a.assistant_name ?? "Tildelt assistent"} ·{" "}
            {displayDate(a.valid_from, zone)} –{" "}
            {displayDate(a.valid_until, zone)} ·{" "}
            {a.state === "active" ? "Aktiv tildeling" : "Tilbakekalt tildeling"}
          </p>
          <button type="button" onClick={() => setSelected(a.id)}>
            Åpne spørsmål, innspill og vurdering
          </button>
          {a.state === "active" && (
            <button
              type="button"
              disabled={command.busy || command.uncertain}
              onClick={() =>
                command.run(
                  ["teaching", "brief-assignments", a.id, "revoke"],
                  { expected_version: a.version },
                  () => {
                    setSelected("");
                    assignments.reload();
                  },
                )
              }
            >
              Trekk tilbake tildeling
            </button>
          )}
        </div>
      ))}
      {selected && (
        <AssignmentPanel key={selected} {...props} assignmentId={selected} />
      )}
      <CommandStatus command={command} />
      {error && <p role="alert">{error}</p>}
    </article>
  );
}
export default function Briefs(props: Props) {
  const briefs = useRead(
    () =>
      allPages<Brief>(props.client, props.schoolId, [
        "teaching",
        "sessions",
        props.session.id,
        "briefs",
      ]),
    [props.client, props.schoolId, props.session.id, props.session.revision_id],
  );
  const [creating, setCreating] = useState(false);
  return (
    <section>
      <h3>Assistentkort og veiledning</h3>
      {props.session.approved ? (
        <button type="button" onClick={() => setCreating(!creating)}>
          Lag assistentkort fra godkjent revisjon
        </button>
      ) : (
        <p>Godkjenn eksakt øktrevisjon før et nytt kort opprettes.</p>
      )}
      {creating && props.session.approved && (
        <NewBrief
          {...props}
          onSaved={() => {
            setCreating(false);
            briefs.reload();
          }}
        />
      )}
      <ReadStatus {...briefs} formatError={props.formatError} />
      {briefs.value?.map((b) => (
        <ManageBrief
          key={`${b.id}:${b.version}:${b.state}`}
          {...props}
          brief={b}
          onChanged={briefs.reload}
        />
      ))}
    </section>
  );
}

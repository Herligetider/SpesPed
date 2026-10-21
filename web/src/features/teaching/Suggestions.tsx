import { useRef, useState } from "react";
import type {
  WorkspaceProps,
  Diff,
  Job,
  Session,
  SessionContent,
  SessionField,
} from "./types";
import { fields } from "./types";
import {
  allPages,
  CommandStatus,
  Field,
  pretty,
  ReadStatus,
  useCommand,
  useRead,
} from "./runtime";
import SessionEditor from "./SessionEditor";
type Option = {
  policy_id: string;
  release_id: string;
  label: string;
  model_version: string;
  reviewed_at: string;
};
export default function Suggestions(
  props: WorkspaceProps & {
    learnerId: string;
    session: Session;
    draft: SessionContent;
    onSaved: (row: Session) => void;
    onConflict: () => void;
    hasUnsaved: boolean;
  },
) {
  const { client, schoolId, learnerId, session, formatError } = props;
  const options = useRead(
    () =>
      allPages<Option>(
        client,
        schoolId,
        ["ai", "choices"],
        new URLSearchParams({
          purpose: "session_planning",
          learner_id: learnerId,
        }),
      ),
    [client, schoolId, learnerId],
  );
  const [selected, setSelected] = useState("");
  const [job, setJob] = useState<Job>();
  const [chosen, setChosen] = useState<SessionField[]>([]);
  const [edited, setEdited] = useState<SessionContent>();
  const [reason, setReason] = useState("");
  const [stale, setStale] = useState(false);
  const [jobReload, setJobReload] = useState(0);
  const jobRef = useRef(job);
  jobRef.current = job;
  const currentJob = useRead(
    () =>
      job
        ? client.schoolGet<Job>(schoolId, ["ai", "jobs", job.id])
        : Promise.resolve(undefined),
    [client, schoolId, job?.id, jobReload],
  );
  const diff = useRead(
    () =>
      job && currentJob.value?.state === "succeeded"
        ? client.schoolGet<Diff>(schoolId, [
            "teaching",
            "sessions",
            session.id,
            "suggestions",
            job.id,
            "diff",
          ])
        : Promise.resolve(undefined),
    [
      client,
      schoolId,
      session.id,
      session.revision_id,
      job?.id,
      currentJob.value?.state,
    ],
  );
  const command = useCommand(client, schoolId, formatError, () => {
    setStale(true);
    props.onConflict();
    setJobReload((x) => x + 1);
  });
  const selectedOption = options.value?.find((_, i) => String(i) === selected);
  function request() {
    if (!selectedOption) return;
    command.run<Job>(
      ["teaching", "sessions", session.id, "suggestions"],
      {
        policy_id: selectedOption.policy_id,
        release_id: selectedOption.release_id,
      },
      (row) => {
        setJob(row);
        setChosen([]);
        setEdited(undefined);
        setStale(false);
      },
    );
  }
  function run() {
    const current = currentJob.value ?? job;
    if (current)
      command.run<Job>(
        ["ai", "jobs", current.id, "run"],
        { expected_version: current.version },
        (row) => {
          if (jobRef.current?.id === row.id) {
            setJob(row);
            setJobReload((x) => x + 1);
          }
        },
        false,
      );
  }
  function review(outcome: "accepted" | "edited" | "rejected") {
    if (!job || !diff.value) return;
    command.run<Session>(
      ["teaching", "sessions", session.id, "suggestions", "review"],
      {
        expected_version: diff.value.expected_version,
        job_id: job.id,
        outcome,
        selected_fields: outcome === "rejected" ? [] : chosen,
        ...(outcome === "edited" ? { content: edited } : {}),
        reason,
      },
      (row) => {
        setJob(undefined);
        setChosen([]);
        setEdited(undefined);
        props.onSaved(row);
      },
    );
  }
  return (
    <section>
      <h4>Modellforslag med faglig kontroll</h4>
      <p>
        Et nytt forslag beholder lagret plan og egne redigeringer. Valgte felt
        erstattes først etter din uttrykkelige vurdering. Forslaget dokumenterer
        ingen tidligere mestring.
      </p>
      <p className="teaching-muted">Ubehandlede modellforslag kan foreløpig bare åpnes i denne aktive arbeidsflaten. Fullfør vurderingen før du lukker den eller bytter økt. Lagrede øktrevisjoner og egne lagrede endringer beholdes.</p>
      <ReadStatus {...options} formatError={formatError} />
      <Field label="Gjennomgått lokal modell og behandlingsoppsett">
        <select value={selected} onChange={(e) => setSelected(e.target.value)}>
          <option value="">Velg et godkjent oppsett</option>
          {options.value?.map((option, index) => (
            <option
              value={index}
              key={`${option.policy_id}:${option.release_id}`}
            >
              {option.label} · {option.model_version}
            </option>
          ))}
        </select>
      </Field>
      {options.value?.length === 0 && (
        <p>
          Ingen godkjente modellvalg er tilgjengelige. Du kan fortsette med
          manuell planlegging.
        </p>
      )}
      <button
        type="button"
        disabled={
          !selectedOption ||
          command.busy ||
          command.uncertain ||
          props.hasUnsaved
        }
        onClick={request}
      >
        {job ? "Bestill nytt forslag" : "Bestill forslag"}
      </button>
      {props.hasUnsaved && (
        <p>
          Lagre egne endringer som ny revisjon før modellforslaget vurderes.
          Utkastet beholdes.
        </p>
      )}
      {job && (
        <>
          <ReadStatus {...currentJob} formatError={formatError} />
          <p>
            Modelljobb:{" "}
            {{
              queued: "Venter på kjøring",
              running: "Behandler",
              succeeded: "Forslag klart til kontroll",
              failed: "Mislyktes",
              cancelled: "Avbrutt",
              expired: "Utløpt",
            }[currentJob.value?.state ?? job.state] ?? "Uavklart"}
            {currentJob.value?.error_code
              ? " · Manuell planlegging er tilgjengelig."
              : ""}
          </p>
          {["queued", "failed"].includes(
            currentJob.value?.state ?? job.state,
          ) && (
            <button
              type="button"
              disabled={command.busy || command.uncertain}
              onClick={run}
            >
              Kjør lokal modelljobb
            </button>
          )}
          <button type="button" onClick={() => setJobReload((x) => x + 1)}>
            Kontroller jobbstatus
          </button>
          <ReadStatus {...diff} formatError={formatError} />
          {diff.value && (
            <>
              <p>
                Ubekreftet forslag. Gjeldende lagrede revisjon{" "}
                {session.revision} vises til venstre, foreslått innhold til
                høyre.
              </p>
              <div className="teaching-diff">
                {diff.value.changes.map((change) => (
                  <div className="teaching-card" key={change.field}>
                    <label className="teaching-check">
                      <input
                        type="checkbox"
                        checked={chosen.includes(change.field)}
                        onChange={(e) =>
                          setChosen(
                            e.target.checked
                              ? [...chosen, change.field]
                              : chosen.filter((f) => f !== change.field),
                          )
                        }
                      />
                      <strong>
                        {fields.find((f) => f.key === change.field)?.label}{" "}
                        {change.changed ? "· endret" : "· lik tekst"}
                      </strong>
                    </label>
                    <div className="teaching-columns">
                      <div>
                        <h5>Lagret</h5>
                        <p className="teaching-pre">{pretty(change.before)}</p>
                      </div>
                      <div>
                        <h5>Forslag</h5>
                        <p className="teaching-pre">
                          {pretty(change.proposed)}
                        </p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
              {diff.value.missing_evidence.length > 0 && (
                <div>
                  <h5>Manglende grunnlag</h5>
                  <ul>
                    {diff.value.missing_evidence.map((item, i) => (
                      <li key={i}>{item}</li>
                    ))}
                  </ul>
                </div>
              )}
              <button
                type="button"
                onClick={() =>
                  setEdited({
                    ...props.draft,
                    ...Object.fromEntries(
                      diff.value!.changes.map((change) => [
                        change.field,
                        change.proposed,
                      ]),
                    ),
                  } as SessionContent)
                }
              >
                Rediger forslag før valg av felt
              </button>
              {edited && <SessionEditor value={edited} onChange={setEdited} />}
              <Field label="Kort faglig begrunnelse (valgfritt for forslag)">
                <textarea
                  maxLength={2000}
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                />
              </Field>
              <button
                type="button"
                disabled={
                  !chosen.length ||
                  props.hasUnsaved ||
                  stale ||
                  command.busy ||
                  command.uncertain
                }
                onClick={() => review(edited ? "edited" : "accepted")}
              >
                Bruk valgte felt i ny øktrevisjon
              </button>
              <button
                type="button"
                disabled={
                  props.hasUnsaved || stale || command.busy || command.uncertain
                }
                onClick={() => review("rejected")}
              >
                Forkast forslaget
              </button>
            </>
          )}
        </>
      )}
      {stale && (
        <p role="alert">
          Grunnlaget eller versjonen er endret. Kontroller konkurrerende versjon
          før videre vurdering.
        </p>
      )}
      <CommandStatus command={command} />
    </section>
  );
}

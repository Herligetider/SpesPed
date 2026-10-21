import { useRef, useState } from "react";
import type {
  WorkspaceProps,
  Diff,
  Session,
  SessionContent,
  SessionField,
} from "./types";
import { fields } from "./types";
import { allPages, Field, pretty, ReadStatus, useRead } from "./runtime";
import SessionEditor from "./SessionEditor";
import {
  SavedProposals,
  SelectedProposal,
  RecoveryStatus,
} from "../suggestions/SavedProposals";
import {
  proposalScopeKey,
  useProposalRecovery,
} from "../suggestions/useProposalRecovery";
import type { ProposalRecovery } from "../suggestions/useProposalRecovery";
type Option = {
  policy_id: string;
  release_id: string;
  label: string;
  model_version: string;
  reviewed_at: string;
};
type Props = WorkspaceProps & {
  learnerId: string;
  session: Session;
  draft: SessionContent;
  onSaved: (row: Session) => void;
  onConflict: () => void;
  hasUnsaved: boolean;
};
function config(props: Props) {
  return {
    client: props.client,
    schoolId: props.schoolId,
    learnerId: props.learnerId,
    userId: props.currentUser.id,
    ownerId: props.session.id,
    revisionId: props.session.revision_id,
    basisId: props.session.basis_id,
    kind: "teaching" as const,
    formatError: props.formatError,
  };
}
export default function Suggestions(props: Props) {
  return <ScopedSuggestions key={proposalScopeKey(config(props))} {...props} />;
}
function ScopedSuggestions(props: Props) {
  const { client, schoolId, learnerId, session, formatError } = props;
  const latest = useRef(props);
  latest.current = props;
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
  const recovery = useProposalRecovery<Diff>({
    ...config(props),
    onConflict: props.onConflict,
    onReconciled: (owner) => {
      const row = owner as Session;
      if (latest.current.hasUnsaved || row.source_status !== "current")
        latest.current.onConflict();
      else latest.current.onSaved(row);
    },
  });
  const selectedOption = options.value?.find((_, i) => String(i) === selected);
  return (
    <section>
      <h4>Modellforslag med faglig kontroll</h4>
      <p>
        Et nytt forslag beholder lagret plan og egne redigeringer. Valgte felt
        erstattes først etter din uttrykkelige vurdering. Forslaget dokumenterer
        ingen tidligere mestring.
      </p>
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
          recovery.busy ||
          Boolean(recovery.uncertain) ||
          props.hasUnsaved
        }
        onClick={() => {
          if (selectedOption)
            recovery.command({
              kind: "create",
              path: ["teaching", "sessions", session.id, "suggestions"],
              body: {
                request_key: crypto.randomUUID(),
                policy_id: selectedOption.policy_id,
                release_id: selectedOption.release_id,
              },
              onSuccess: (value) =>
                recovery.select((value as { id: string }).id),
            });
        }}
      >
        Bestill forslag
      </button>
      {props.hasUnsaved && (
        <p>
          Lagre eller avklar egne endringer før modellforslaget vurderes.
          Utkastet beholdes når du henter eller åpner lagrede forslag.
        </p>
      )}
      <SavedProposals recovery={recovery} />
      <SelectedProposal recovery={recovery} />
      {recovery.selectedId && (
        <TeachingProposalReview
          key={recovery.selectedId}
          {...props}
          recovery={recovery}
        />
      )}
      <RecoveryStatus recovery={recovery} />
    </section>
  );
}
function TeachingProposalReview(
  props: Props & { recovery: ProposalRecovery<Diff> },
) {
  const r = props.recovery;
  const latest = useRef(props);
  latest.current = props;
  const fresh = r.verified.value?.diff;
  const retained = useRef<Diff | null>(null);
  if (fresh) retained.current = fresh;
  const [chosen, setChosen] = useState<SessionField[]>([]),
    [edited, setEdited] = useState<SessionContent>(),
    [reason, setReason] = useState("");
  const d = retained.current;
  if (!d) return null;
  function review(outcome: "accepted" | "edited" | "rejected") {
    if (!fresh || props.hasUnsaved) return;
    r.command({
      kind: "review",
      jobId: r.selectedId,
      outcome,
      path: ["teaching", "sessions", props.session.id, "suggestions", "review"],
      diff: fresh,
      body: {
        request_key: crypto.randomUUID(),
        expected_version: fresh.expected_version,
        job_id: r.selectedId,
        outcome,
        selected_fields: outcome === "rejected" ? [] : chosen,
        ...(outcome === "edited" ? { content: edited } : {}),
        reason,
      },
      onSuccess: (owner) => {
        if (latest.current.hasUnsaved) latest.current.onConflict();
        else latest.current.onSaved(owner as Session);
      },
    });
  }
  return (
    <div hidden={!fresh}>
      <fieldset disabled={r.busy || Boolean(r.uncertain) || props.hasUnsaved}>
        <legend>Faglig vurdering av valgt lagret forslag</legend>
        <p>
          Ubekreftet forslag. Gjeldende lagrede revisjon{" "}
          {props.session.revision} vises til venstre, foreslått innhold til
          høyre.
        </p>
        <div className="teaching-diff">
          {d.changes.map((change) => (
            <div className="teaching-card" key={change.field}>
              <label className="teaching-check">
                <input
                  type="checkbox"
                  checked={chosen.includes(change.field)}
                  onChange={(e) =>
                    setChosen(
                      e.target.checked
                        ? [...chosen, change.field]
                        : chosen.filter((field) => field !== change.field),
                    )
                  }
                />
                <strong>
                  {fields.find((field) => field.key === change.field)?.label}{" "}
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
                  <p className="teaching-pre">{pretty(change.proposed)}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
        {d.missing_evidence.length > 0 && (
          <div>
            <h5>Manglende grunnlag</h5>
            <ul>
              {d.missing_evidence.map((item, i) => (
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
                d.changes.map((change) => [change.field, change.proposed]),
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
          disabled={!chosen.length}
          onClick={() => review(edited ? "edited" : "accepted")}
        >
          Bruk valgte felt i ny øktrevisjon
        </button>
        <button type="button" onClick={() => review("rejected")}>
          Forkast forslaget
        </button>
      </fieldset>
    </div>
  );
}

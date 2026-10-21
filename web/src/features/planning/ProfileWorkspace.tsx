import { useState } from "react";
import type { Binding, Context, Statement } from "./types";
import {
  Field,
  ListBlock,
  SourcePicker,
  SourceView,
  State,
  key,
  label,
  localInstant,
  useCommand,
  when,
} from "./shared";
export default function ProfileWorkspace({ ctx }: { ctx: Context }) {
  const [history, setHistory] = useState(false),
    [category, setCategory] = useState("strength"),
    [content, setContent] = useState(""),
    [source, setSource] = useState<Binding | null>(null),
    [observed, setObserved] = useState(""),
    [replaces, setReplaces] = useState<Statement | null>(null),
    [validation, setValidation] = useState("");
  const cmd = useCommand(ctx);
  const base = ["learners", ctx.learnerId, "support-profile"];
  return (
    <section aria-labelledby="planning-profile-title">
      <h3 id="planning-profile-title">Pedagogisk støtteprofil</h3>
      <p>
        Opplysninger foreslås med kilde og dato. Ansvarlig person bekrefter hva
        som gjelder.
      </p>
      <label>
        <input
          type="checkbox"
          checked={history}
          onChange={(e) => setHistory(e.target.checked)}
        />{" "}
        Vis også erstattede og avviste opplysninger
      </label>
      <ListBlock<Statement>
        key={String(history)}
        ctx={ctx}
        path={base}
        query={{ history: String(history) }}
      >
        {(s) => (
          <article className="planning-card">
            <h4>{label(s.category)}</h4>
            <State value={s.state} />
            <State value={s.source_status} />
            {s.source_status === "current" ? (
              <>
                <p>{s.content}</p>
                <p>
                  Opplyst {when(s.observed_at)} · sist vurdert{" "}
                  {when(s.reviewed_at)}
                </p>
                <SourceView ctx={ctx} value={s.source} />
                {s.review_reason && <p>Vurdering: {s.review_reason}</p>}
                <button
                  type="button"
                  onClick={() => {
                    setReplaces(s);
                    setCategory(s.category);
                    setContent(s.content || "");
                    setSource(null);
                  }}
                >
                  Foreslå retting av denne opplysningen
                </button>
                <StatementReview ctx={ctx} statement={s} />
              </>
            ) : (
              <p>Innholdet vises etter ny vurdering av kildegrunnlaget.</p>
            )}
            <details>
              <summary>Vurderingshistorikk</summary>
              <ListBlock<{
                id: string;
                outcome: string;
                reason: string | null;
                reviewed_at: string;
                source_status: string;
              }>
                ctx={ctx}
                path={[...base, "statements", s.id, "history"]}
              >
                {(r) => (
                  <p>
                    <State value={r.outcome} /> {when(r.reviewed_at)} ·{" "}
                    {r.reason || "Grunnlaget må vurderes på nytt"}
                  </p>
                )}
              </ListBlock>
            </details>
          </article>
        )}
      </ListBlock>
      <details open={replaces ? true : undefined}>
        <summary>
          {replaces ? "Foreslå retting" : "Legg til en kildebelagt opplysning"}
        </summary>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (!source) return;
            try {
              cmd.submit(
                [...base, "statements"],
                {
                  request_key: key(),
                  category,
                  content,
                  source,
                  observed_at: localInstant(observed),
                  replaces_id: replaces?.id || null,
                },
                () => {
                  setContent("");
                  setReplaces(null);
                },
              );
            } catch (e) {
              setValidation(ctx.formatError(e));
            }
          }}
        >
          <fieldset disabled={cmd.busy || cmd.pending}>
            <legend>
              {replaces
                ? "Retting erstatter først etter bekreftelse"
                : "Ny opplysning"}
            </legend>
            {replaces && <p>Retter: {replaces.content}</p>}
            <label>
              Kategori
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value)}
              >
                {[
                  "strength",
                  "interest",
                  "language",
                  "communication",
                  "support_strategy",
                ].map((v) => (
                  <option key={v} value={v}>
                    {label(v)}
                  </option>
                ))}
              </select>
            </label>
            <Field
              title="Opplysning"
              type="textarea"
              value={content}
              onChange={setContent}
            />
            <Field
              title="Opplysningen gjelder fra (lokal dato og tid)"
              type="datetime-local"
              value={observed}
              onChange={setObserved}
            />
            <SourcePicker ctx={ctx} value={source} onChange={setSource} />
            <button disabled={!source} type="submit">
              Lagre forslag til profil
            </button>
            {replaces && (
              <button type="button" onClick={() => setReplaces(null)}>
                Avslutt retting
              </button>
            )}
          </fieldset>
          {validation && <p role="alert">{validation}</p>}
          {cmd.status}
        </form>
      </details>
    </section>
  );
}
function StatementReview({
  ctx,
  statement: s,
}: {
  ctx: Context;
  statement: Statement;
}) {
  const [reason, setReason] = useState(""),
    [outcome, setOutcome] = useState("confirmed");
  const cmd = useCommand(ctx);
  return (
    <details>
      <summary>Vurder opplysningen</summary>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          cmd.submit(
            [
              "learners",
              ctx.learnerId,
              "support-profile",
              "statements",
              s.id,
              "review",
            ],
            {
              request_key: key(),
              expected_version: s.version,
              outcome,
              reason,
            },
          );
        }}
      >
        <fieldset disabled={cmd.busy || cmd.pending}>
          <legend>Vurder vist opplysning og kilde</legend>
          <label>
            Konklusjon
            <select
              value={outcome}
              onChange={(e) => setOutcome(e.target.value)}
            >
              <option value="confirmed">Bekreft</option>
              <option value="disputed">Marker som bestridt</option>
              <option value="rejected">Avvis</option>
            </select>
          </label>
          <Field
            title="Begrunnelse for vurderingen"
            type="textarea"
            value={reason}
            onChange={setReason}
          />
          <button type="submit">Lagre vurdering</button>
        </fieldset>
        {cmd.status}
      </form>
    </details>
  );
}

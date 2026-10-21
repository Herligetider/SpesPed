import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { ApiClient, ApiError } from './api';
import type { IntakeSource } from './types';
import { Field, localInstant, localValue } from './features/planning/shared';

type Props = {
  client: ApiClient; schoolId: string; source: IntakeSource; disabled: boolean;
  sourceAvailable?: boolean;
  formatError: (error: unknown) => string;
  onBusy: (busy: boolean) => void;
  onRefresh: () => Promise<IntakeSource | undefined>;
};
type Draft = { sender: string; documentType: string; originalAt: string };
type Attempt = { kind: 'inspect'; base: IntakeSource } | {
  kind: 'replace'; base: IntakeSource; file: File; metadata: Record<string, unknown>; draft: Draft;
};
const initial = (source: IntakeSource): Draft => ({ sender: source.sender, documentType: source.document_type, originalAt: source.original_at ? localValue(source.original_at) : '' });
const same = (left: Draft, right: Draft) => JSON.stringify(left) === JSON.stringify(right);
const uncertainError = (error: unknown) => !(error instanceof ApiError) || error.status === 0 || error.status >= 500;

/** Scoped to one authenticated workspace and source by the parent's key. */
export default function SourceMaintenance({ client, schoolId, source, disabled, sourceAvailable = true, formatError, onBusy, onRefresh }: Props) {
  const alive = useRef(true), fileInput = useRef<HTMLInputElement>(null);
  const [base, setBase] = useState(source), [draft, setDraft] = useState<Draft>(() => initial(source));
  const [file, setFile] = useState<File | null>(null), [attempt, setAttempt] = useState<Attempt | null>(null);
  const [busy, setBusy] = useState(false), [unknown, setUnknown] = useState(false);
  const [message, setMessage] = useState(''), [failure, setFailure] = useState('');
  const [observed, setObserved] = useState<IntakeSource | null>(null), [needsRefresh, setNeedsRefresh] = useState(false);
  const latest = useRef({ file, draft }); latest.current = { file, draft };
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  const changed = base.version !== source.version || base.current_revision !== source.current_revision;
  const locked = busy || disabled;
  function working(value: boolean) { setBusy(value); onBusy(value); }

  async function run(command: Attempt) {
    working(true); setFailure(''); setMessage(''); setObserved(null);
    try {
      const saved = command.kind === 'replace'
        ? await client.reviseIntake(schoolId, command.base.id, command.base.version, command.file, command.metadata)
        : await client.schoolCommand<IntakeSource>(schoolId, ['intake', command.base.id, 'inspect'], { expected_version: command.base.version });
      if (!alive.current) return;
      setUnknown(false); setAttempt(null);
      if (command.kind === 'replace' && latest.current.file === command.file && same(latest.current.draft, command.draft)) {
        setFile(null); if (fileInput.current) fileInput.current.value = '';
      }
      setMessage(command.kind === 'replace'
        ? `Revisjon ${saved.revision} er lagret. Kontroller den nye kilden og uttrekket før opplysninger brukes videre.`
        : saved.extraction_state === 'ready'
          ? 'Dokumentbehandlingen er fullført. Uttrekket er klart for kontroll.'
          : 'Forsøket er registrert, men dokumentet er fortsatt ikke klart for kontroll. Se skann- og uttrekksstatus.');
      const current = await onRefresh();
      if (!alive.current) return;
      setNeedsRefresh(!current);
      if (current) setBase(current);
    } catch (error) {
      if (!alive.current) return;
      setFailure(formatError(error));
      if (uncertainError(error)) { setUnknown(true); setAttempt(command); }
      else if (unknown || (command.kind === 'inspect' && error instanceof ApiError && error.status === 409)) {
        // A version conflict may follow a committed inspection whose reply was
        // lost. Read registered state before offering a new operation.
        setUnknown(true); setAttempt(command);
      } else { setAttempt(null); setNeedsRefresh(error instanceof ApiError && error.status === 409); }
    } finally { if (alive.current) working(false); }
  }

  async function replace(event: FormEvent) {
    event.preventDefault();
    if (locked || !sourceAvailable || unknown || changed || needsRefresh || !file) return;
    try {
      const metadata = {
        request_key: crypto.randomUUID(), external_scope: base.external_scope, external_id: base.external_id,
        sender: draft.sender, document_type: draft.documentType,
        received_at: new Date().toISOString(), original_at: draft.originalAt ? localInstant(draft.originalAt) : null,
      };
      const command: Attempt = { kind: 'replace', base, file, metadata, draft: { ...draft } };
      setAttempt(command); await run(command);
    } catch (error) { setFailure(formatError(error)); }
  }

  async function refresh() {
    working(true); setFailure(''); setObserved(null);
    try {
      const current = await onRefresh();
      if (!alive.current) return;
      setNeedsRefresh(!current);
      if (!current) setFailure('Gjeldende kildestatus kunne ikke bekreftes. Prøv å laste status på nytt.');
      else if (unknown) setObserved(current);
      else setMessage('Gjeldende kilde er lastet. Sammenlign revisjonene før du bruker et beholdt utkast.');
    } catch (error) { if (alive.current) { setFailure(formatError(error)); setNeedsRefresh(true); } }
    finally { if (alive.current) working(false); }
  }

  return <section className="followup-panel" aria-label="Oppdater originalkilden">
    <h3>Oppdater originalkilden</h3>
    <p>En ny fil lagres som en ny revisjon. Tidligere originaler og registrerte elevopplysninger beholdes. Opplysninger som bygger på en eldre kilde må kontrolleres på nytt.</p>
    {message && <p role="status">{message}</p>}
    {failure && <p role="alert">{failure}</p>}
    {unknown && attempt && <div className="error-panel" role="alert">
      <p>Utfallet er ukjent. Innsendingen er beholdt med samme innhold og revisjonsgrunnlag.</p>
      <button type="button" disabled={locked || !sourceAvailable} onClick={() => void run(attempt)}>Prøv den samme kildehandlingen igjen</button>
      <button type="button" disabled={locked} onClick={() => void refresh()}>Avklar mot gjeldende kildestatus</button>
      {observed && <div>
        <p>Registrert nå: revisjon {observed.current_revision}, versjon {observed.version}, uttrekk {observed.extraction_state === 'ready' ? 'klart' : 'ikke klart'}. Dette alene bekrefter ikke utfallet av den opprinnelige innsendingen.</p>
        {(observed.version !== attempt.base.version || observed.current_revision !== attempt.base.current_revision) && <button type="button" disabled={locked} onClick={() => {
          setUnknown(false); setAttempt(null); setBase(observed); setObserved(null);
          setMessage('Avklaringen er avsluttet med den registrerte statusen. Ingen ny innsending er utført. Kontroller kilden før du sender inn på nytt.');
        }}>Bruk registrert status og avslutt avklaringen</button>}
      </div>}
    </div>}
    {!unknown && (changed || needsRefresh || !sourceAvailable) && <div className="error-panel">
      <p>Utkastet bygger på revisjon {base.current_revision}, versjon {base.version}. Gjeldende kilde er revisjon {source.current_revision}, versjon {source.version}. Fil og felter er beholdt.</p>
      <button type="button" disabled={locked} onClick={() => void refresh()}>Last gjeldende kildestatus</button>
      {changed && !needsRefresh && sourceAvailable && <button type="button" disabled={locked} onClick={() => { setBase(source); setMessage('Beholdte felter vil brukes på den valgte gjeldende revisjonen.'); }}>Behold feltene mine og bruk gjeldende revisjon</button>}
    </div>}
    <details>
      <summary>Last opp ny revisjon</summary>
      <form onSubmit={replace}>
        <fieldset disabled={locked || !sourceAvailable || unknown}>
          <label>Ny kildefil<input ref={fileInput} type="file" required onChange={event => setFile(event.target.files?.[0] ?? null)}/></label>
          <label>Avsender for ny revisjon<input required maxLength={320} value={draft.sender} onChange={event => setDraft(value => ({ ...value, sender: event.target.value }))}/></label>
          <label>Dokumenttype for ny revisjon<input required maxLength={80} value={draft.documentType} onChange={event => setDraft(value => ({ ...value, documentType: event.target.value }))}/></label>
          <Field title="Opprinnelig dokumenttidspunkt for ny revisjon" type="datetime-local" required={false} value={draft.originalAt} onChange={originalAt => setDraft(value => ({ ...value, originalAt }))}/>
          <button className="primary-button" disabled={changed || needsRefresh || !file}>Lagre ny kilderevisjon</button>
        </fieldset>
      </form>
    </details>
    {source.extraction_state !== 'ready' && <div>
      <p>Når skann eller tekstuttak er tilgjengelig igjen, kan den bevarte originalen behandles på nytt.</p>
      <button type="button" className="secondary-button" disabled={locked || !sourceAvailable || unknown || changed || needsRefresh} onClick={() => void run({ kind: 'inspect', base })}>Prøv dokumentbehandlingen på nytt</button>
    </div>}
  </section>;
}

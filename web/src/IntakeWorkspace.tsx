import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { ApiClient, ApiError } from './api';
import type { Clarification, ExtractionProposal, IntakeSource, Learner, ListResponse } from './types';
type Load<T> = {
    state: 'loading';
} | {
    state: 'error';
    error: unknown;
} | {
    state: 'ready';
    value: T;
};
type Props = {
    client: ApiClient;
    schoolId: string;
    formatError: (e: unknown) => string;
};
type Page = {
    page: number;
    text: string;
    source_revision: number;
};
type Span = {
    start: number;
    end: number;
};
type Candidate = Pick<ExtractionProposal, 'id' | 'page' | 'source_revision' | 'span_start' | 'span_end' | 'field_name'>;
type Attribution = {
    learner_id: string;
    reporter: string;
    topic: string;
    occurred_at: string;
    excerpt_start: number;
    excerpt_end: number;
    certainty: 'confirmed' | 'uncertain' | 'disputed';
    claim_type: 'report' | 'observation' | 'professional_judgement';
};
const fieldLabels: Record<string, string> = { content: 'Innhold', learner: 'Elev', document_date: 'Dokumentdato', goal: 'Mål', measure: 'Tiltak', follow_up: 'Oppfølging', hours: 'Timer', document_type: 'Dokumenttype', mentioned_learner: 'Omtalt elev' };
const reasonLabels: Record<string, string> = { unresolved_attribution: 'Uavklart elevtilordning', ambiguous_field: 'Tvetydig felt', unsupported_field: 'Felt uten støtte i kilden', missing_source_span: 'Mangler kildeutdrag', disagreement: 'Uenighet', invalid_structuring_output: 'Ugyldig modelluttrekk', missing_information: 'Manglende opplysninger' };
const stateLabels: Record<string, string> = { received: 'Mottatt', processing: 'Under behandling', quarantined: 'I karantene', needs_review: 'Må kontrolleres', needs_clarification: 'Må avklares', awaiting_confirmation: 'Venter på bekreftelse', done: 'Behandlet', clean: 'Godkjent', not_required_note: 'Ikke nødvendig for notat', ready: 'Klar', pending: 'Venter', failed: 'Feilet', not_started: 'Ikke startet', unsupported: 'Ikke støttet' };
const label = (v: string) => stateLabels[v] ?? v;
const makeKey = () => globalThis.crypto.randomUUID();
const characters = (text: string) => Array.from(text);
const excerpt = (text: string, span: Span) => characters(text).slice(span.start, span.end).join('');
export const selectionSpan = (text: string, start: number, end: number): Span => ({ start: characters(text.slice(0, start)).length, end: characters(text.slice(0, end)).length });
export function localInstant(value: string): string {
    const date = new Date(value), parts = value.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/);
    if (!parts || !Number.isFinite(date.getTime()) || [date.getFullYear(), date.getMonth() + 1, date.getDate(), date.getHours(), date.getMinutes()].some((n, i) => n !== Number(parts[i + 1])))
        throw new ApiError('Velg et gyldig lokalt hendelsestidspunkt.', 422, 'occurrence_time');
    return date.toISOString();
}
async function allItems<T>(load: (offset: number) => Promise<ListResponse<T>>): Promise<ListResponse<T>> {
    const items: T[] = [];
    for (;;) {
        const result = await load(items.length);
        items.push(...result.items);
        if (items.length >= result.total || !result.items.length)
            return { items, total: result.total };
    }
}
const clientKeys = new WeakMap<ApiClient, string>();
export default function IntakeWorkspace(props: Props) { if (!clientKeys.has(props.client))
    clientKeys.set(props.client, makeKey()); return <Workspace key={`${clientKeys.get(props.client)}:${props.schoolId}`} {...props}/>; }
function Workspace({ client, schoolId, formatError }: Props) {
    const alive = useRef(true), navigation = useRef(0), pageGeneration = useRef(0), inboxGeneration = useRef(0), originalRef = useRef('');
    const [inbox, setInbox] = useState<Load<ListResponse<IntakeSource>>>({ state: 'loading' }), [selected, setSelected] = useState<IntakeSource | null>(null);
    const [proposals, setProposals] = useState<Load<ListResponse<ExtractionProposal>> | null>(null), [tasks, setTasks] = useState<Clarification[]>([]);
    const [page, setPage] = useState<Page | null>(null), [pageNumber, setPageNumber] = useState(1), [pageError, setPageError] = useState('');
    const [originalUrl, setOriginalUrl] = useState(''), [originalError, setOriginalError] = useState('');
    const [learners, setLearners] = useState<Load<Learner[]>>({ state: 'loading' }), [assignees, setAssignees] = useState<Load<{
        id: string;
        display_name: string;
    }[]>>({ state: 'loading' });
    const [notice, setNotice] = useState(''), [conflict, setConflict] = useState(false), [busy, setBusy] = useState(false), [gatewayError, setGatewayError] = useState('');
    const [manual, setManual] = useState({ field_name: 'content', value: '', page: 1, start: 0, end: 0 }), [editor, setEditor] = useState<Record<string, string>>({});
    const [clarification, setClarification] = useState({ assignee_id: '', reason: 'missing_information', detail: '' }), [highlight, setHighlight] = useState<Span | null>(null), [retained, setRetained] = useState('');
    const noteAttempt = useRef<{
        signature: string;
        body: Record<string, unknown>;
    } | null>(null), fileAttempt = useRef<{
        signature: string;
        file: File;
        metadata: Record<string, unknown>;
    } | null>(null);
    const [attributions, setAttributions] = useState<Record<string, Attribution>>({}), [recoveryDraft, setRecoveryDraft] = useState({ candidate: '', value: '' });
    const noteForm = useRef<HTMLFormElement>(null);
    const [uncertain, setUncertain] = useState<'note' | 'file' | null>(null);
    const active = (generation: number) => alive.current && navigation.current === generation;
    function revokeOriginal() { if (originalRef.current)
        URL.revokeObjectURL(originalRef.current); originalRef.current = ''; setOriginalUrl(''); }
    function clearSource() { revokeOriginal(); setOriginalError(''); setPage(null); setPageError(''); setPageNumber(1); setProposals(null); setTasks([]); setGatewayError(''); setManual({ field_name: 'content', value: '', page: 1, start: 0, end: 0 }); setEditor({}); setClarification({ assignee_id: '', reason: 'missing_information', detail: '' }); setHighlight(null); setRetained(''); setAttributions({}); setRecoveryDraft({ candidate: '', value: '' }); setBusy(false); }
    async function reloadInbox(offset = 0) { const generation = ++inboxGeneration.current; if (!offset)
        setInbox({ state: 'loading' }); try {
        const value = await client.intake(schoolId, offset);
        if (!alive.current || generation !== inboxGeneration.current)
            return;
        setInbox(previous => ({ state: 'ready', value: { ...value, items: offset && previous.state === 'ready' ? [...previous.value.items, ...value.items] : value.items } }));
    }
    catch (error) {
        if (alive.current && generation === inboxGeneration.current)
            setInbox({ state: 'error', error });
    } }
    useEffect(() => {
        alive.current = true;
        void reloadInbox();
        allItems(offset => client.learners(schoolId, offset, 100)).then(r => { if (alive.current)
            setLearners({ state: 'ready', value: r.items }); }).catch(error => { if (alive.current)
            setLearners({ state: 'error', error }); });
        allItems(offset => client.intakeAssignees(schoolId, offset)).then(r => { if (alive.current)
            setAssignees({ state: 'ready', value: r.items }); }).catch(error => { if (alive.current)
            setAssignees({ state: 'error', error }); });
        return () => { alive.current = false; navigation.current++; pageGeneration.current++; if (originalRef.current)
            URL.revokeObjectURL(originalRef.current); };
    }, [client, schoolId]);
    async function loadPage(source: IntakeSource, number: number, generation = navigation.current, span?: Span, preserve = false) {
        const request = ++pageGeneration.current;
        setPage(null);
        setPageError('');
        setPageNumber(number);
        setHighlight(null);
        try {
            const data = await client.intakePage(schoolId, source.id, source.current_revision, number);
            if (!active(generation) || request !== pageGeneration.current)
                return;
            setPage(data);
            setHighlight(span ?? null);
            if (!span)
                setManual(v => preserve && v.page === number ? v : { ...v, value: v.page === number ? v.value : '', page: number, start: 0, end: characters(data.text).length });
        }
        catch (error) {
            if (active(generation) && request === pageGeneration.current)
                setPageError(formatError(error));
        }
    }
    async function openSource(source: IntakeSource, refresh = false) {
        const generation = ++navigation.current;
        pageGeneration.current++;
        if (!refresh) {
            clearSource();
            setNotice('');
            setConflict(false);
        }
        else {
            revokeOriginal();
            setPage(null);
            setPageError('');
            setProposals({ state: 'loading' });
            setTasks([]);
            setGatewayError('');
            setBusy(false);
        }
        setSelected(source);
        setProposals({ state: 'loading' });
        setBusy(true);
        try {
            const current = await client.intakeSource(schoolId, source.id);
            if (!active(generation))
                return;
            if (refresh && current.current_revision !== source.current_revision) {
                setRetained(`Revisjon ${source.current_revision}\nManuelt felt (${fieldLabels[manual.field_name]}, side ${manual.page}): ${manual.value}\nRettelser: ${Object.values(editor).join('; ')}\nAvklaring: ${clarification.detail}\nBekreftelsesutkast: ${Object.values(attributions).map(a => `${a.reporter}; ${a.occurred_at || 'ukjent hendelsestid'}; ${a.topic}`).join(' / ')}\nManuell gjenoppretting: ${recoveryDraft.value}\nLes den nye kilden og velg et nytt utdrag før du bruker en beholdt verdi.`);
                setManual({ field_name: 'content', value: '', page: 1, start: 0, end: 0 });
                setEditor({});
                setAttributions({});
                setRecoveryDraft({ candidate: '', value: '' });
                setClarification({ assignee_id: '', reason: 'missing_information', detail: '' });
            }
            setSelected(current);
            void client.intakeOriginal(schoolId, current.id, current.current_revision).then(blob => { if (!active(generation))
                return; const url = URL.createObjectURL(blob); originalRef.current = url; setOriginalUrl(url); setOriginalError(''); }).catch(error => { if (active(generation))
                setOriginalError(formatError(error)); });
            if (current.page_count)
                void loadPage(current, refresh ? Math.min(pageNumber, current.page_count) : 1, generation, undefined, refresh);
            void allItems(offset => client.intakeClarifications(schoolId, current.id, offset)).then(r => { if (active(generation))
                setTasks(r.items); }).catch(error => { if (active(generation))
                setNotice(formatError(error)); });
            try {
                const value = await allItems(offset => client.intakeProposals(schoolId, current.id, current.current_revision, undefined, offset));
                if (active(generation))
                    setProposals({ state: 'ready', value });
            }
            catch (error) {
                if (!active(generation))
                    return;
                if (error instanceof ApiError && (error.status === 503 || /gateway|recall/.test(error.code))) {
                    setGatewayError(formatError(error));
                    try {
                        const value = await allItems(offset => client.intakeProposals(schoolId, current.id, current.current_revision, 'manual', offset));
                        if (active(generation))
                            setProposals({ state: 'ready', value });
                    }
                    catch (manualError) {
                        if (active(generation))
                            setProposals({ state: 'error', error: manualError });
                    }
                }
                else
                    setProposals({ state: 'error', error });
            }
        }
        catch (error) {
            if (active(generation))
                setProposals({ state: 'error', error });
        }
        finally {
            if (active(generation))
                setBusy(false);
        }
    }
    async function perform(action: () => Promise<unknown>, message: string): Promise<boolean> {
        const generation = navigation.current;
        setBusy(true);
        setNotice('');
        try {
            await action();
            if (!active(generation))
                return false;
            setNotice(message);
            setConflict(false);
            void reloadInbox();
            if (selected) {
                await openSource(selected, true);
                return active(generation + 1);
            }
            return active(generation);
        }
        catch (error) {
            if (!active(generation))
                return false;
            setNotice(error instanceof ApiError && error.status === 0 ? 'Lagringsutfallet er ukjent. Serveren kan ha lagret innholdet. Prøv samme innsending igjen for å avklare utfallet.' : formatError(error));
            setConflict(error instanceof ApiError && error.status === 409);
            return false;
        }
        finally {
            if (active(generation))
                setBusy(false);
        }
    }
    function metadata(sender: string, document_type: string, original_at: string) { return { request_key: makeKey(), external_scope: 'manual', external_id: makeKey(), sender, document_type, received_at: new Date().toISOString(), original_at: original_at ? localInstant(original_at) : null }; }
    async function submitNote(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        const form = event.currentTarget, data = new FormData(form), input = { sender: String(data.get('sender') || 'Ansatt'), document_type: String(data.get('doctype') || 'notat'), original_at: String(data.get('original_at') || ''), text: String(data.get('note') || '') };
        if (!input.text.trim())
            return;
        const signature = JSON.stringify(input);
        if (noteAttempt.current && noteAttempt.current.signature !== signature) {
            setNotice('Notatet er endret etter et uavklart lagringsforsøk. Prøv den opprinnelige innsendingen igjen først.');
            setUncertain('note');
            return;
        }
        try {
            noteAttempt.current ??= { signature, body: { ...metadata(input.sender, input.document_type, input.original_at), text: input.text } };
        }
        catch (error) {
            setNotice(formatError(error));
            return;
        }
        const generation = navigation.current, attempt = noteAttempt.current;
        if (await perform(() => client.createIntakeNote(schoolId, attempt.body).catch(error => { if (error instanceof ApiError && error.status >= 400 && error.status < 500 && noteAttempt.current === attempt)
            noteAttempt.current = null; throw error; }), 'Notatet er lagret i innboksen.')) {
            noteAttempt.current = null;
            setUncertain(null);
            form.reset();
        }
        else if (active(generation))
            setUncertain(noteAttempt.current ? 'note' : null);
    }
    async function retryNote() { const attempt = noteAttempt.current; if (!attempt)
        return; if (await perform(() => client.createIntakeNote(schoolId, attempt.body).catch(error => { if (error instanceof ApiError && error.status >= 400 && error.status < 500 && noteAttempt.current === attempt)
        noteAttempt.current = null; throw error; }), 'Den opprinnelige innsendingen er bekreftet lagret. Du kan nå skrive et nytt notat.')) {
        noteAttempt.current = null;
        setUncertain(null);
        const form = noteForm.current;
        if (form) {
            const data = new FormData(form);
            if (JSON.stringify({ sender: String(data.get('sender') || 'Ansatt'), document_type: String(data.get('doctype') || 'notat'), original_at: String(data.get('original_at') || ''), text: String(data.get('note') || '') }) === attempt.signature)
                form.reset();
        }
    } }
    async function submitFile(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        const form = event.currentTarget, data = new FormData(form), file = data.get('file');
        if (!(file instanceof File) || !file.size)
            return;
        const input = { sender: String(data.get('sender') || 'Ukjent avsender'), document_type: String(data.get('doctype') || 'importert dokument'), original_at: String(data.get('original_at') || ''), external_id: String(data.get('external_id') || '').trim() }, signature = JSON.stringify({ ...input, name: file.name, size: file.size, lastModified: file.lastModified });
        if (fileAttempt.current && fileAttempt.current.signature !== signature) {
            setNotice('Prøv den opprinnelige filinnsendingen igjen før du oppretter en ny import.');
            setUncertain('file');
            return;
        }
        try {
            fileAttempt.current ??= { signature, file, metadata: { ...metadata(input.sender, input.document_type, input.original_at), ...(input.external_id ? { external_id: input.external_id } : {}) } };
        }
        catch (error) {
            setNotice(formatError(error));
            return;
        }
        const generation = navigation.current, attempt = fileAttempt.current;
        if (await perform(() => client.uploadIntake(schoolId, attempt.file, attempt.metadata).catch(error => { if (error instanceof ApiError && error.status >= 400 && error.status < 500 && fileAttempt.current === attempt)
            fileAttempt.current = null; throw error; }), 'Kilden er lagret. Filkontroll og uttrekk vises i statusen.')) {
            fileAttempt.current = null;
            setUncertain(null);
            form.reset();
        }
        else if (active(generation))
            setUncertain(fileAttempt.current ? 'file' : null);
    }
    async function retryFile() { const attempt = fileAttempt.current; if (!attempt)
        return; if (await perform(() => client.uploadIntake(schoolId, attempt.file, attempt.metadata).catch(error => { if (error instanceof ApiError && error.status >= 400 && error.status < 500 && fileAttempt.current === attempt)
        fileAttempt.current = null; throw error; }), 'Den opprinnelige filinnsendingen er bekreftet lagret.')) {
        fileAttempt.current = null;
        setUncertain(null);
    } }
    async function review(field: ExtractionProposal, outcome: 'accepted' | 'edited' | 'rejected') {
        const value = editor[field.id] ?? field.proposed_value;
        const success = await perform(() => client.reviewProposal(schoolId, field.id, { expected_version: field.version, outcome, ...(outcome === 'edited' ? { value } : {}), reason: outcome === 'accepted' ? 'Kontrollert mot vist kilde' : outcome === 'rejected' ? 'Ikke støttet av vist kilde' : 'Manuelt korrigert mot vist kilde' }), outcome === 'rejected' ? 'Feltet er forkastet.' : 'Feltet er lagret som gjennomgått.');
        if (success)
            setEditor(values => { const next = { ...values }; delete next[field.id]; return next; });
    }
    async function manualProposal(event: FormEvent) { event.preventDefault(); if (!selected || !page || manual.page !== page.page)
        return; await perform(() => client.proposeField(schoolId, selected.id, { expected_version: selected.version, page: manual.page, span_start: manual.start, span_end: manual.end, field_name: manual.field_name, proposed_value: manual.value }), 'Manuelt kildefelt er lagret som forslag.'); }
    async function createTask(event: FormEvent) { event.preventDefault(); if (selected)
        await perform(() => client.createClarification(schoolId, selected.id, { expected_version: selected.version, ...clarification }), 'Avklaringsoppgaven er tildelt.'); }
    async function changeTask(task: Clarification) { if (!selected)
        return; const explanation = window.prompt(task.state === 'open' ? 'Beskriv hva som ble avklart:' : 'Hvorfor må oppgaven åpnes igjen?'); if (!explanation?.trim())
        return; await perform(() => task.state === 'open' ? client.resolveClarification(schoolId, selected.id, task.id, { expected_version: task.version, resolution: explanation }) : client.reopenClarification(schoolId, selected.id, task.id, { expected_version: task.version, reason: explanation }), task.state === 'open' ? 'Avklaringen er løst og lagret.' : 'Avklaringsoppgaven er åpnet igjen.'); }
    async function downloadOriginal() { if (!selected)
        return; const source = selected, generation = navigation.current; try {
        const blob = await client.intakeOriginal(schoolId, source.id, source.current_revision);
        if (!active(generation))
            return;
        const url = URL.createObjectURL(blob), link = document.createElement('a');
        link.href = url;
        link.download = source.filename;
        link.click();
        URL.revokeObjectURL(url);
    }
    catch (error) {
        if (active(generation))
            setNotice(formatError(error));
    } }
    const alerts = <>{notice && <p className="notice" role="status">{notice}
        </p>}{conflict && <div className="error-panel" role="alert">
        <p>Versjonskonflikt: endringen ble ikke lagret. Utkastet ditt er beholdt. Last inn gjeldende kilde, sammenlign verdiene og velg selv om endringen skal brukes på nytt.</p>
        <button type="button" className="secondary-button" onClick={() => selected && void openSource(selected, true)}>Last inn gjeldende kilde og behold utkast</button>
        </div>}{retained && <label>Beholdt utkast fra tidligere kilderevisjon<textarea readOnly value={retained}/>
        </label>}
    </>;
    if (selected)
        return <section className="intake-workspace" aria-labelledby="intake-title">
    <button className="back-link" type="button" onClick={() => { navigation.current++; pageGeneration.current++; clearSource(); setSelected(null); setNotice(''); setConflict(false); void reloadInbox(); }}>← Tilbake til innboksen</button>
    <div className="list-heading">
        <div>
        <p className="eyebrow">Kildekontroll · revisjon {selected.current_revision}
        </p>
        <h2 id="intake-title">{selected.filename}
        </h2>
        <p>{selected.sender} · {selected.document_type} · mottatt {new Date(selected.received_at).toLocaleString('nb-NO')}
        </p>{selected.original_at && <p>Opprinnelig dokumentdato: {new Date(selected.original_at).toLocaleString('nb-NO')}
            </p>}
        </div>
        <button className="secondary-button" type="button" onClick={downloadOriginal}>Last ned original</button>
        </div>
    <div className="intake-status" aria-label="Kildestatus">
        <span>Status: <strong>{label(selected.state)}
        </strong>
        </span>
        <span>Skann: <strong>{label(selected.scan_state)}
        </strong>
        </span>
        <span>Uttrekk: <strong>{label(selected.extraction_state)}
        </strong>
        </span>{selected.issue && <span role="alert">{selected.issue}
            </span>}
        </div>{alerts}
    <div className="source-review-grid">
        <section className="source-card" aria-label="Originalkilde">
        <div className="list-heading">
        <h3>Original og tekstuttak</h3>{selected.page_count > 1 && <label>Side <select aria-label="Kildeside" value={pageNumber} onChange={e => void loadPage(selected, Number(e.target.value))}>{Array.from({ length: selected.page_count }, (_, i) => <option key={i + 1}>{i + 1}
                </option>)}
            </select>
            </label>}
        </div>
      {originalUrl && (['application/pdf', 'text/plain'].includes(selected.media_type) || selected.media_type.startsWith('image/')) ? <iframe className="original-preview" title={`Originalkilde ${selected.filename}`} sandbox="" src={originalUrl}/> : <p className="muted">{originalError || 'Originalen lastes, eller filtypen krever nedlasting.'}
            </p>}
      {pageError && <p role="alert">{pageError}
            </p>}{page ? <>
            <p className="source-page-label">Uttrekk · side {page.page} · kildeversjon {page.source_revision}
            </p>
            <p>Marker tekst i kilden for å velge et manuelt kildeutdrag.</p>
            <TextSelection title="Kildetekst – marker et utdrag" text={page.text} onSelect={span => setManual(v => ({ ...v, page: page.page, ...span }))}/>{highlight && <div className="source-highlight">
                <strong>Valgt kildeutsnitt</strong>
                <blockquote>{excerpt(page.text, highlight)}
                </blockquote>
                </div>}
            </> : <p className="muted">Kildeteksten lastes eller er utilgjengelig. Kontroller uttrekksstatusen.</p>}
    </section>
        <section className="proposal-card" aria-label="Felt til gjennomgang">
        <h3>Foreslåtte felt og kildebevis</h3>
      {gatewayError && <div className="error-panel" role="alert">
            <p>Modellforslaget er utilgjengelig eller tilbakekalt. Kildens gjeldende tekst og manuell kontroll er fortsatt tilgjengelig.</p>
            <p>{gatewayError}
            </p>
            </div>}{proposals?.state === 'loading' && <p role="status">Laster kontrollerbare felt …</p>}{proposals?.state === 'error' && <p role="alert">{formatError(proposals.error)}
            </p>}{proposals?.state === 'ready' && !proposals.value.items.length && <p>Ingen tilgjengelige uttrekksforslag. Du kan fortsette manuelt fra kilden.</p>}
      {proposals?.state === 'ready' && proposals.value.items.map(field => <ProposalCard key={`${selected.id}:${selected.current_revision}:${field.id}`} {...{ client, schoolId, field, selected, learners, busy, formatError, perform }} draft={attributions[field.id]} setDraft={value => setAttributions(v => { const next = { ...v }; if (value)
                next[field.id] = value;
            else
                delete next[field.id]; return next; })} editor={editor[field.id]} setEditor={value => setEditor(v => ({ ...v, [field.id]: value }))} onReview={outcome => review(field, outcome)} showSpan={() => void loadPage(selected, field.page, navigation.current, { start: field.span_start, end: field.span_end })} onClarify={value => setClarification(v => ({ ...v, reason: 'disagreement', detail: `Beholdt retting av ${fieldLabels[field.field_name]}: ${value}. Gjeldende verdi: ${field.reviewed_value ?? field.proposed_value}` }))}/>)}
      {gatewayError && <ManualRecovery key={`${selected.id}:${selected.current_revision}`} {...{ client, schoolId, source: selected, formatError, perform, busy }} draft={recoveryDraft} setDraft={setRecoveryDraft} onShow={c => void loadPage(selected, c.page, navigation.current, { start: c.span_start, end: c.span_end })}/>}
      <form className="manual-field-form" onSubmit={manualProposal}>
        <h4>Registrer et felt manuelt</h4>
        <p className="muted">Marker nødvendig tekst i kilden. Kontroller utdraget før du lagrer feltet.</p>
        <label>Felttype<select aria-label="Felttype" value={manual.field_name} onChange={e => setManual(v => ({ ...v, field_name: e.target.value, value: '' }))}>{Object.entries(fieldLabels).map(([value, name]) => <option key={value} value={value}>{name}
            </option>)}
        </select>
        </label>
        <p>Side {manual.page} · {manual.end - manual.start} tegn valgt</p>
        <blockquote aria-label="Manuelt kildeutdrag">{page && manual.page === page.page ? excerpt(page.text, manual) : ''}
        </blockquote>
      {manual.field_name === 'learner' ? <label>Feltverdi<select aria-label="Feltverdi" required value={manual.value} onChange={e => setManual(v => ({ ...v, value: e.target.value }))}>
            <option value="">Velg autorisert elev</option>{learners.state === 'ready' && learners.value.map(l => <option key={l.id} value={l.id}>{l.display_name}
                </option>)}
            </select>
            </label> : <label>Feltverdi<input required type={manual.field_name === 'document_date' ? 'date' : manual.field_name === 'hours' ? 'number' : 'text'} step={manual.field_name === 'hours' ? 'any' : undefined} min={manual.field_name === 'hours' ? 0 : undefined} maxLength={20000} value={manual.value} onChange={e => setManual(v => ({ ...v, value: e.target.value }))}/>
            </label>}
        <button className="primary-button" disabled={busy || !page || manual.page !== page.page || manual.end <= manual.start}>Lagre manuelt forslag</button>
        </form>
    </section>
        </div>
    <section className="followup-panel">
        <h3>Avklaringer og oppfølging</h3>{tasks.length ? <ul className="task-list">{tasks.map(task => <li key={task.id}>
                <strong>{task.state === 'open' ? 'Åpen' : 'Løst'} · {reasonLabels[task.reason] ?? task.reason}
                </strong>
                <span>{task.detail}
                </span>
                <small>Ansvarlig: {assignees.state === 'ready' ? assignees.value.find(a => a.id === task.assignee_id)?.display_name ?? 'Tidligere ansvarlig' : 'Laster ansvarlig'} · revisjon {task.source_revision}
                </small>{task.resolution && <p>{task.resolution}
                    </p>}
                <button type="button" className="secondary-button" disabled={busy} onClick={() => void changeTask(task)}>{task.state === 'open' ? 'Registrer avklaring som løst' : 'Åpne oppgaven igjen'}
                </button>
                </li>)}
            </ul> : <p>Ingen registrerte avklaringsoppgaver.</p>}
    <form onSubmit={createTask}>
        <h4>Tildel en avklaring</h4>{assignees.state === 'error' && <p role="alert">Ansvarlige kunne ikke lastes: {formatError(assignees.error)}
            </p>}
        <div className="form-grid">
        <label>Ansvarlig<select aria-label="Ansvarlig" required value={clarification.assignee_id} onChange={e => setClarification(v => ({ ...v, assignee_id: e.target.value }))}>
        <option value="">Velg ansvarlig</option>{assignees.state === 'ready' && assignees.value.map(a => <option key={a.id} value={a.id}>{a.display_name}
            </option>)}
        </select>
        </label>
        <label>Årsak<select aria-label="Årsak" value={clarification.reason} onChange={e => setClarification(v => ({ ...v, reason: e.target.value }))}>{Object.entries(reasonLabels).map(([value, name]) => <option key={value} value={value}>{name}
            </option>)}
        </select>
        </label>
        </div>
        <label>Hva må avklares?<textarea required maxLength={2000} value={clarification.detail} onChange={e => setClarification(v => ({ ...v, detail: e.target.value }))}/>
        </label>
        <button className="secondary-button" disabled={busy || !clarification.assignee_id}>Opprett avklaringsoppgave</button>
        </form>
        </section>
  </section>;
    return <section className="intake-workspace" aria-labelledby="intake-title">
    <div className="list-heading">
    <div>
    <p className="eyebrow">Dokumentinntak og kildekontroll</p>
    <h2 id="intake-title">Dokumentinnboks</h2>
    <p>Importer kilder og kontroller hvert uttrekk før opplysningene brukes videre.</p>
    </div>
    </div>{alerts}
    {uncertain && <div className="error-panel" role="alert">
        <p>Innsendingen er beholdt til utfallet er avklart. Nytt forsøk bruker samme innhold og identitet.</p>
        <button className="secondary-button" disabled={busy} onClick={() => void (uncertain === 'note' ? retryNote() : retryFile())}>Prøv opprinnelig innsending igjen</button>
        </div>}
    <div className="intake-forms">
    <form ref={noteForm} onSubmit={submitNote}>
    <h3>Nytt notat</h3>
    <label>Avsender<input name="sender" defaultValue="Ansatt" required maxLength={320}/>
    </label>
    <label>Type dokument<input name="doctype" defaultValue="notat" required maxLength={80}/>
    </label>
    <label>Opprinnelig dokumentdato (valgfri)<input name="original_at" type="datetime-local"/>
    </label>
    <label>Notat<textarea name="note" required maxLength={100000}/>
    </label>
    <button className="primary-button" disabled={busy}>Lagre notat</button>
    </form>
    <form onSubmit={submitFile}>
    <h3>Importer fil eller lagret e-post</h3>
    <p className="muted">Velg en lokal PDF, Word-fil, skann eller .eml.</p>
    <label>Avsender<input name="sender" defaultValue="Ukjent avsender" required maxLength={320}/>
    </label>
    <label>Type dokument<input name="doctype" defaultValue="importert dokument" required maxLength={80}/>
    </label>
    <label>Opprinnelig dokumentdato (valgfri)<input name="original_at" type="datetime-local"/>
    </label>
    <details>
    <summary>Kjent kildeidentitet (valgfritt)</summary>
    <label>Kilde-ID for dublettkontroll<input name="external_id" maxLength={320} placeholder="For eksempel Message-ID fra e-post"/>
    </label>
    <p>Bruk samme kjente identitet ved ny import av samme e-post. Vanlige forsøk på nytt håndteres automatisk.</p>
    </details>
    <label>Fil<input name="file" type="file" required accept=".pdf,.docx,.txt,.eml,.png,.jpg,.jpeg"/>
    </label>
    <button className="primary-button" disabled={busy}>Importer til innboksen</button>
    </form>
    </div>
    <div className="list-heading inbox-heading">
    <div>
    <h3>Mottatte kilder</h3>
    <p>{inbox.state === 'ready' ? `${inbox.value.items.length} av ${inbox.value.total} registrerte kilder` : ''}
    </p>
    </div>
    <button type="button" className="secondary-button" onClick={() => void reloadInbox()}>Oppdater</button>
    </div>{inbox.state === 'loading' && <p role="status">Laster innboksen …</p>}{inbox.state === 'error' && <div className="error-panel" role="alert">
        <p>{formatError(inbox.error)}
        </p>
        <button className="secondary-button" onClick={() => void reloadInbox()}>Prøv igjen</button>
        </div>}{inbox.state === 'ready' && <>
        <ul className="inbox-list">{inbox.value.items.map(source => <li key={source.id}>
            <button type="button" onClick={() => void openSource(source)}>
            <strong>{source.filename}
            </strong>
            <span>{source.sender} · {source.document_type}
            </span>
            <span className="source-pill">{label(source.state)}
            </span>
            <small>Revisjon {source.current_revision} · skann {label(source.scan_state)} · uttrekk {label(source.extraction_state)}
            </small>
            </button>
            </li>)}
        </ul>{inbox.value.items.length < inbox.value.total && <button className="secondary-button" onClick={() => void reloadInbox(inbox.value.items.length)}>Vis flere kilder</button>}{!inbox.value.items.length && <p>Innboksen er tom. Legg inn et notat eller importer en godkjent kilde.</p>}
        </>}
  </section>;
}
function TextSelection({ title, text, onSelect }: {
    title: string;
    text: string;
    onSelect: (span: Span) => void;
}) {
    return <label>{title}
    <textarea className="source-text" readOnly value={text} onSelect={e => { const element = e.currentTarget; if (element.selectionStart !== element.selectionEnd)
        onSelect(selectionSpan(text, element.selectionStart, element.selectionEnd)); }}/>
    </label>;
}
function ProposalCard({ client, schoolId, field, selected, learners, busy, formatError, perform, draft, setDraft, editor, setEditor, onReview, showSpan, onClarify }: {
    client: ApiClient;
    schoolId: string;
    field: ExtractionProposal;
    selected: IntakeSource;
    learners: Load<Learner[]>;
    busy: boolean;
    formatError: (e: unknown) => string;
    perform: (action: () => Promise<unknown>, message: string) => Promise<boolean>;
    draft: Attribution | undefined;
    setDraft: (value: Attribution | undefined) => void;
    editor: string | undefined;
    setEditor: (value: string) => void;
    onReview: (outcome: 'accepted' | 'edited' | 'rejected') => Promise<void>;
    showSpan: () => void;
    onClarify: (value: string) => void;
}) {
    const a: Attribution = draft ?? { learner_id: '', reporter: selected.sender, topic: 'kildeopplysning', occurred_at: '', excerpt_start: field.span_start, excerpt_end: field.span_end, certainty: 'uncertain', claim_type: 'report' };
    const setA = (update: (value: Attribution) => Attribution) => setDraft(update(a));
    const [sourcePage, setSourcePage] = useState<Load<Page>>({ state: 'loading' }), [error, setError] = useState('');
    useEffect(() => { let current = true; client.intakePage(schoolId, selected.id, field.source_revision, field.page).then(value => { if (current)
        setSourcePage({ state: 'ready', value }); }).catch(error => { if (current)
        setSourcePage({ state: 'error', error }); }); return () => { current = false; }; }, [client, schoolId, selected.id, field.source_revision, field.page]);
    const value = field.reviewed_value ?? field.proposed_value, validSpan = a.excerpt_start <= field.span_start && a.excerpt_end >= field.span_end && sourcePage.state === 'ready' && a.excerpt_end <= characters(sourcePage.value.text).length;
    async function confirm(event: FormEvent) { event.preventDefault(); try {
        const occurred_at = localInstant(a.occurred_at);
        setError('');
        if (await perform(() => client.reviewEvidence(schoolId, field.id, { expected_version: field.version, learner_id: a.learner_id, claim_type: a.claim_type, reporter: a.reporter, source_type: 'imported_document', certainty: a.certainty, occurred_at, topic: a.topic, excerpt_page: field.page, excerpt_start: a.excerpt_start, excerpt_end: a.excerpt_end }), 'Opplysningen er knyttet til valgt elev med kontrollert kildeutdrag.'))
            setDraft(undefined);
    }
    catch (error) {
        setError(formatError(error));
    } }
    return <article className="proposal-item">
    <div className="proposal-meta">
    <strong>{fieldLabels[field.field_name] ?? field.field_name}
    </strong>
    <span>{field.state === 'confirmed' ? 'Bekreftet' : field.outcome === 'pending' ? 'Må kontrolleres' : field.outcome === 'rejected' ? 'Forkastet' : field.outcome === 'edited' ? 'Rettet' : 'Godtatt'} · side {field.page}
    </span>
    <button className="text-button" onClick={showSpan}>Vis kildeutsnitt</button>
    </div>
    <p className="proposal-value">{value}
    </p>{field.reviewed_value !== null && field.reviewed_value !== field.proposed_value && <details>
        <summary>Opprinnelig forslag</summary>
        <p>{field.proposed_value}
        </p>
        </details>}{sourcePage.state === 'ready' && <blockquote aria-label="Feltets kildeutsnitt">{excerpt(sourcePage.value.text, { start: field.span_start, end: field.span_end })}
        </blockquote>}{sourcePage.state === 'error' && <p role="alert">{formatError(sourcePage.error)}
        </p>}{field.review_reason && <p className="muted">Kontrollgrunn: {field.review_reason}
        </p>}
    {field.outcome === 'pending' && <>
        <label>Rett verdi<input value={editor ?? field.proposed_value} onChange={e => setEditor(e.target.value)}/>
        </label>
        <div className="button-row">
        <button className="primary-button" disabled={busy} onClick={() => void onReview('accepted')}>Godta</button>
        <button className="secondary-button" disabled={busy} onClick={() => void onReview('edited')}>Lagre retting</button>
        <button className="secondary-button" disabled={busy} onClick={() => void onReview('rejected')}>Forkast</button>
        </div>
        </>}
    {field.outcome !== 'pending' && editor !== undefined && editor !== value && <div className="error-panel">
        <label>Din beholdte retting<textarea value={editor} onChange={e => setEditor(e.target.value)}/>
        </label>
        <p>En annen gjennomgang er allerede lagret. Sammenlign med gjeldende verdi over. Behold rettingen i en avklaring dersom du er uenig.</p>
        <button className="secondary-button" onClick={() => onClarify(editor)}>Bruk rettingen i en avklaring</button>
        </div>}
    {field.state === 'confirmed' && draft && <div className="error-panel">
        <p>Bekreftelsesutkastet ditt er beholdt etter en konkurrerende lagring.</p>
        <p>Valgt elev: {learners.state === 'ready' ? learners.value.find(l => l.id === a.learner_id)?.display_name ?? 'Tidligere valgt elev' : 'Tidligere valgt elev'} · hendelse: {a.occurred_at || 'Ikke avklart'} · tema: {a.topic} · rapportør: {a.reporter}
        </p>
        <button className="secondary-button" onClick={() => onClarify(`Beholdt elevtilordning: ${a.occurred_at}, ${a.topic}, ${a.reporter}`)}>Bruk bekreftelsesutkastet i en avklaring</button>
        </div>}
    {['accepted', 'edited'].includes(field.outcome) && field.state !== 'confirmed' && <form className="attribution-form" onSubmit={confirm}>
        <h4>Bekreft elevtilordning og utdrag</h4>
        <p>Kontrollert verdi: <strong>{value}
        </strong>
        </p>
        <p>Marker bare nødvendig tekst i utdraget. Utdraget må omfatte feltets kildeutsnitt.</p>{sourcePage.state === 'ready' && <>
            <TextSelection title="Kildetekst for elevutdrag" text={sourcePage.value.text} onSelect={span => setA(v => ({ ...v, excerpt_start: span.start, excerpt_end: span.end }))}/>
            <blockquote aria-label="Utdrag som knyttes til eleven">{excerpt(sourcePage.value.text, { start: a.excerpt_start, end: a.excerpt_end })}
            </blockquote>
            </>}{!validSpan && <p role="alert">Velg et utdrag som omfatter hele feltets kildeutsnitt.</p>}
    <div className="form-grid">
        <label>Elev<select aria-label="Elev" required value={a.learner_id} onChange={e => setA(v => ({ ...v, learner_id: e.target.value }))}>
        <option value="">Velg autorisert elev</option>{learners.state === 'ready' && learners.value.map(l => <option key={l.id} value={l.id}>{l.display_name} · trinn {l.grade}
            </option>)}
        </select>
        </label>
        <label>Opplysningstype<select aria-label="Opplysningstype" value={a.claim_type} onChange={e => setA(v => ({ ...v, claim_type: e.target.value as Attribution['claim_type'] }))}>
        <option value="report">Rapportert opplysning</option>
        <option value="observation">Observasjon</option>
        <option value="professional_judgement">Faglig vurdering</option>
        </select>
        </label>
        <label>Avsender / rapportør<input required value={a.reporter} onChange={e => setA(v => ({ ...v, reporter: e.target.value }))}/>
        </label>
        <label>Hendelsestidspunkt<input type="datetime-local" required value={a.occurred_at} onChange={e => setA(v => ({ ...v, occurred_at: e.target.value }))}/>
        </label>
        <label>Tema<input required maxLength={100} value={a.topic} onChange={e => setA(v => ({ ...v, topic: e.target.value }))}/>
        </label>
        <label>Avklaring<select aria-label="Avklaring" value={a.certainty} onChange={e => setA(v => ({ ...v, certainty: e.target.value as Attribution['certainty'] }))}>
        <option value="uncertain">Usikker</option>
        <option value="confirmed">Bekreftet</option>
        <option value="disputed">Bestridt</option>
        </select>
        </label>
        </div>
        <p className="muted">Hendelsestidspunkt oppgis i din lokale tidssone ({Intl.DateTimeFormat().resolvedOptions().timeZone}). Bekreftelse krever et kjent tidspunkt.</p>{learners.state === 'error' && <p role="alert">{formatError(learners.error)}
            </p>}{error && <p role="alert">{error}
            </p>}
        <button className="primary-button" disabled={busy || !validSpan || learners.state !== 'ready' || !learners.value.length}>Bekreft avgrenset elevopplysning</button>
        </form>}
  </article>;
}
function ManualRecovery({ client, schoolId, source, formatError, perform, onShow, busy, draft, setDraft }: {
    client: ApiClient;
    schoolId: string;
    source: IntakeSource;
    formatError: (e: unknown) => string;
    perform: (action: () => Promise<unknown>, message: string) => Promise<boolean>;
    onShow: (candidate: Candidate) => void;
    busy: boolean;
    draft: {
        candidate: string;
        value: string;
    };
    setDraft: (value: {
        candidate: string;
        value: string;
    }) => void;
}) {
    const [candidates, setCandidates] = useState<Load<Candidate[]>>({ state: 'loading' });
    const { candidate, value } = draft;
    const setCandidate = (candidate: string) => setDraft({ ...draft, candidate });
    const setValue = (value: string) => setDraft({ ...draft, value });
    useEffect(() => { let current = true; allItems(offset => client.recoveryCandidates(schoolId, source.id, offset)).then(r => { if (current)
        setCandidates({ state: 'ready', value: r.items }); }).catch(error => { if (current)
        setCandidates({ state: 'error', error }); }); return () => { current = false; }; }, [client, schoolId, source.id, source.current_revision]);
    const choices = candidates.state === 'ready' ? candidates.value : [], chosen = choices.find(c => c.id === candidate);
    return <form className="recovery-panel" onSubmit={async (e) => { e.preventDefault(); if (chosen)
        await perform(() => client.recoverManualField(schoolId, source.id, { expected_version: source.version, source_revision: source.current_revision, recovery_of_proposal_id: chosen.id, page: chosen.page, span_start: chosen.span_start, span_end: chosen.span_end, field_name: chosen.field_name, proposed_value: value }), 'Manuelt felt er lagret og kan vurderes uavhengig.'); }}>
    <h4>Manuell gjenoppretting av modellfelt</h4>
    <p>Velg en kildeplassering og les originalen. Modellens tilbakekalte tekst vises ikke.</p>{candidates.state === 'loading' && <p role="status">Henter kildeplasseringer …</p>}{candidates.state === 'error' && <p role="alert">{formatError(candidates.error)}
        </p>}{candidates.state === 'ready' && !choices.length && <p>Ingen modellplasseringer på gjeldende revisjon.</p>}{choices.length > 0 && <>
        <label>Kildeplassering<select aria-label="Kildeplassering" required value={candidate} onChange={e => { setCandidate(e.target.value); const c = choices.find(c => c.id === e.target.value); if (c)
            onShow(c); }}>
        <option value="">Velg plassering</option>{choices.map((c, i) => <option key={c.id} value={c.id}>{fieldLabels[c.field_name]} · side {c.page} · plassering {i + 1}
            </option>)}
        </select>
        </label>
        <label>Verdi kontrollert mot kildeteksten<input required maxLength={20000} value={value} onChange={e => setValue(e.target.value)}/>
        </label>
        <button className="secondary-button" disabled={busy || !candidate}>Lagre uavhengig manuelt felt</button>
        </>}
    </form>;
}

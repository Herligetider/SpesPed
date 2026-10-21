import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import IntakeWorkspace, { localInstant, selectionSpan } from './IntakeWorkspace';
import { ApiClient, ApiError } from './api';
import type { ExtractionProposal, IntakeSource } from './types';
const source: IntakeSource = { id: 'source-1', version: 3, state: 'needs_clarification', current_revision: 2, revision: 2, sender: 'Synthetic sender', document_type: 'notat', received_at: '2026-10-21T08:00:00Z', original_at: null, filename: 'synthetic.txt', media_type: 'text/plain', digest: 'a'.repeat(64), byte_size: 32, scan_state: 'not_required_note', extraction_state: 'ready', issue: null, page_count: 1, review_progress: { pending: 0 }, pagination: 'source_pages' };
const field: ExtractionProposal = { id: 'field-1', version: 1, state: 'pending', source_id: source.id, source_revision: 2, page: 1, span_start: 0, span_end: 18, field_name: 'content', proposed_value: 'Synthetic 😀 source', reviewed_value: null, outcome: 'pending', review_reason: null, generation_job_id: null, unit: null, recovery_of_proposal_id: null };
const ok = (items: unknown[] = []) => ({ items, total: items.length });
const failure = (status: number, code = 'conflict') => new ApiError('Synthetic safe error', status, code);
const formatError = (e: unknown) => e instanceof Error ? e.message : 'error';
function deferred<T>() { let resolve!: (v: T) => void; const promise = new Promise<T>(r => { resolve = r; }); return { promise, resolve }; }
function fixture(overrides: Record<string, unknown> = {}) {
    return { intake: vi.fn().mockResolvedValue(ok([source])), intakeSource: vi.fn().mockImplementation(async (_s, id) => ({ ...source, id, filename: id === 'source-2' ? 'second.txt' : source.filename })), intakeOriginal: vi.fn().mockResolvedValue(new Blob(['Synthetic'])), intakePage: vi.fn().mockResolvedValue({ page: 1, text: 'Synthetic 😀 source', source_revision: 2 }), intakeProposals: vi.fn().mockResolvedValue(ok([field])), intakeClarifications: vi.fn().mockResolvedValue(ok()), intakeAssignees: vi.fn().mockResolvedValue(ok([{ id: 'staff-1', display_name: 'Synthetic Staff' }])), learners: vi.fn().mockResolvedValue(ok([{ id: 'learner-1', display_name: 'Synthetic Pupil', grade: 4, version: 1, group_name: null }])), reviewProposal: vi.fn().mockResolvedValue({}), proposeField: vi.fn().mockResolvedValue({}), createIntakeNote: vi.fn().mockResolvedValue(source), reviewEvidence: vi.fn().mockResolvedValue({}), recoveryCandidates: vi.fn().mockResolvedValue(ok()), ...overrides } as unknown as ApiClient;
}
async function open(user: ReturnType<typeof userEvent.setup>) { await user.click(await screen.findByRole('button', { name: /synthetic.txt/i })); await screen.findByLabelText('Kildetekst – marker et utdrag'); await waitFor(() => expect(screen.getByRole('button', { name: 'Lagre manuelt forslag' })).toBeEnabled()); }
beforeEach(() => { URL.createObjectURL = vi.fn().mockReturnValue('blob:synthetic'); URL.revokeObjectURL = vi.fn(); });
describe('document intake scope, exact review and recovery', () => {
    it('shows restricted inbox errors', async () => {
        const client = fixture({ intake: vi.fn().mockRejectedValue(failure(403)) });
        render(<IntakeWorkspace {...{ client, formatError }} schoolId="school-1"/>);
        expect(await screen.findByRole('alert')).toHaveTextContent('Synthetic safe error');
        expect(client.intake).toHaveBeenCalledWith('school-1', 0);
    });
    it('resets all source content and drafts immediately on school change and revokes the blob', async () => {
        const user = userEvent.setup(), client = fixture();
        const view = render(<IntakeWorkspace {...{ client, formatError }} schoolId="school-1"/>);
        await open(user);
        await user.type(screen.getByLabelText('Feltverdi'), 'A private draft');
        view.rerender(<IntakeWorkspace {...{ client, formatError }} schoolId="school-2"/>);
        expect(screen.queryByLabelText('Feltverdi')).not.toBeInTheDocument();
        expect(screen.queryByLabelText('Kildetekst – marker et utdrag')).not.toBeInTheDocument();
        expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:synthetic');
        await open(user);
        expect(screen.getByLabelText('Feltverdi')).toHaveValue('');
    });
    it('ignores old source completions after returning and opening another source', async () => {
        const user = userEvent.setup(), old = deferred<IntakeSource>(), second = { ...source, id: 'source-2', filename: 'second.txt' };
        const client = fixture({ intake: vi.fn().mockResolvedValue(ok([source, second])), intakeSource: vi.fn().mockImplementation((_s, id) => id === source.id ? old.promise : Promise.resolve(second)), intakeProposals: vi.fn().mockResolvedValue(ok()) });
        render(<IntakeWorkspace {...{ client, formatError }} schoolId="school-1"/>);
        await user.click(await screen.findByRole('button', { name: /synthetic.txt/ }));
        await user.click(screen.getByRole('button', { name: /Tilbake til innboksen/ }));
        await user.click(await screen.findByRole('button', { name: /second.txt/ }));
        await screen.findByLabelText('Kildetekst – marker et utdrag');
        await act(async () => old.resolve(source));
        expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('second.txt');
    });
    it('prevents an old page result from replacing a newer page and clears page-local interpretation', async () => {
        const user = userEvent.setup(), old = deferred<{
            page: number;
            text: string;
            source_revision: number;
        }>();
        let delayed = false;
        const client = fixture({ intake: vi.fn().mockResolvedValue(ok([{ ...source, page_count: 2 }])), intakeSource: vi.fn().mockResolvedValue({ ...source, page_count: 2 }), intakeProposals: vi.fn().mockResolvedValue(ok()), intakePage: vi.fn().mockImplementation((_s, _id, _r, n) => n === 1 && delayed ? old.promise : Promise.resolve({ page: n, text: `Synthetic page ${n}`, source_revision: 2 })) });
        render(<IntakeWorkspace {...{ client, formatError }} schoolId="school-1"/>);
        await open(user);
        await user.type(screen.getByLabelText('Feltverdi'), 'Page one draft');
        await user.selectOptions(screen.getByLabelText('Kildeside'), '2');
        await waitFor(() => expect(screen.getByLabelText('Kildetekst – marker et utdrag')).toHaveValue('Synthetic page 2'));
        expect(screen.getByLabelText('Feltverdi')).toHaveValue('');
        delayed = true;
        await user.selectOptions(screen.getByLabelText('Kildeside'), '1');
        await user.selectOptions(screen.getByLabelText('Kildeside'), '2');
        await act(async () => old.resolve({ page: 1, text: 'STALE PAGE', source_revision: 2 }));
        expect(screen.getByLabelText('Kildetekst – marker et utdrag')).toHaveValue('Synthetic page 2');
    });
    it('shows the reviewed value and exact excerpt before confirmation, with no invented occurrence time', async () => {
        const user = userEvent.setup(), client = fixture({ intakeProposals: vi.fn().mockResolvedValue(ok([{ ...field, outcome: 'edited', state: 'reviewed', reviewed_value: '30' }])) });
        render(<IntakeWorkspace {...{ client, formatError }} schoolId="school-1"/>);
        await open(user);
        expect(document.querySelector('.proposal-value')).toHaveTextContent('30');
        await user.selectOptions(screen.getByLabelText('Elev'), 'learner-1');
        expect(screen.getByLabelText('Hendelsestidspunkt')).toHaveValue('');
        expect(screen.getByLabelText('Utdrag som knyttes til eleven')).toHaveTextContent('Synthetic 😀 source');
        fireEvent.change(screen.getByLabelText('Hendelsestidspunkt'), { target: { value: '2026-09-15T10:00' } });
        await user.click(screen.getByRole('button', { name: 'Bekreft avgrenset elevopplysning' }));
        expect(client.reviewEvidence).toHaveBeenCalledWith('school-1', 'field-1', expect.objectContaining({ expected_version: 1, occurred_at: new Date('2026-09-15T10:00').toISOString(), excerpt_start: 0, excerpt_end: 18 }));
    });
    it('loads independent manual recovery proposals while recalled model prose remains hidden', async () => {
        const user = userEvent.setup();
        let recovered = false;
        const client = fixture({ intakeProposals: vi.fn().mockImplementation((_s, _id, _r, origin) => origin === 'manual' ? Promise.resolve(ok(recovered ? [{ ...field, id: 'manual-1', proposed_value: 'Human interpretation' }] : [])) : Promise.reject(failure(503, 'model_recalled'))), recoveryCandidates: vi.fn().mockResolvedValue(ok([{ ...field, id: 'model-1' }])), recoverManualField: vi.fn().mockImplementation(async () => { recovered = true; return {}; }) });
        render(<IntakeWorkspace {...{ client, formatError }} schoolId="school-1"/>);
        await open(user);
        await screen.findByText(/Modellforslaget er utilgjengelig/);
        const form = (await screen.findByRole('heading', { name: 'Manuell gjenoppretting av modellfelt' })).closest('form')!;
        await user.selectOptions(within(form).getByLabelText('Kildeplassering'), 'model-1');
        await user.type(within(form).getByLabelText('Verdi kontrollert mot kildeteksten'), 'Human interpretation');
        await user.click(within(form).getByRole('button', { name: 'Lagre uavhengig manuelt felt' }));
        expect(await screen.findByLabelText('Rett verdi')).toHaveValue('Human interpretation');
        expect(client.intakeProposals).toHaveBeenCalledWith('school-1', source.id, 2, 'manual', 0);
    });
    it('retains a conflicting edit and the conflict message across an explicit refresh', async () => {
        const user = userEvent.setup();
        let reviewed = false;
        const client = fixture({ reviewProposal: vi.fn().mockImplementation(async () => { reviewed = true; throw failure(409); }), intakeProposals: vi.fn().mockImplementation(async () => ok([{ ...field, ...(reviewed ? { outcome: 'accepted', state: 'reviewed', reviewed_value: field.proposed_value, version: 2 } : {}) }])) });
        render(<IntakeWorkspace {...{ client, formatError }} schoolId="school-1"/>);
        await open(user);
        await user.clear(screen.getByLabelText('Rett verdi'));
        await user.type(screen.getByLabelText('Rett verdi'), 'UNSAVED HUMAN EDIT');
        await user.click(screen.getByRole('button', { name: 'Lagre retting' }));
        await screen.findByText(/Versjonskonflikt:/);
        await user.click(screen.getByRole('button', { name: 'Last inn gjeldende kilde og behold utkast' }));
        expect(await screen.findByLabelText('Din beholdte retting')).toHaveValue('UNSAVED HUMAN EDIT');
        expect(screen.getByText(/Versjonskonflikt:/)).toBeInTheDocument();
        await user.click(screen.getByRole('button', { name: 'Bruk rettingen i en avklaring' }));
        expect((screen.getByLabelText('Hva må avklares?') as HTMLTextAreaElement).value).toContain('UNSAVED HUMAN EDIT');
    });
    it('keeps the exact logical note command after a lost committed response', async () => {
        const user = userEvent.setup(), create = vi.fn().mockRejectedValueOnce(failure(0, 'NETWORK_ERROR')).mockResolvedValue(source), client = fixture({ createIntakeNote: create });
        render(<IntakeWorkspace {...{ client, formatError }} schoolId="school-1"/>);
        await user.type(await screen.findByLabelText('Notat'), 'Synthetic uncertain note');
        await user.click(screen.getByRole('button', { name: 'Lagre notat' }));
        await screen.findByText(/Lagringsutfallet er ukjent/);
        await user.click(screen.getByRole('button', { name: 'Lagre notat' }));
        await waitFor(() => expect(create).toHaveBeenCalledTimes(2));
        expect(create.mock.calls[0]).toEqual(create.mock.calls[1]);
    });
    it('allows correcting a definite note validation rejection using a new command', async () => {
        const user = userEvent.setup(), create = vi.fn().mockRejectedValueOnce(failure(422)).mockResolvedValue(source), client = fixture({ createIntakeNote: create });
        render(<IntakeWorkspace {...{ client, formatError }} schoolId="school-1"/>);
        await user.type(await screen.findByLabelText('Notat'), 'First note');
        await user.click(screen.getByRole('button', { name: 'Lagre notat' }));
        await screen.findByText('Synthetic safe error');
        await user.type(screen.getByLabelText('Notat'), ' corrected');
        await user.click(screen.getByRole('button', { name: 'Lagre notat' }));
        await waitFor(() => expect(create).toHaveBeenCalledTimes(2));
        expect(create.mock.calls[0][1].request_key).not.toBe(create.mock.calls[1][1].request_key);
    });
    it('clears the unchanged file selection after an explicit successful retry', async () => {
        const user = userEvent.setup(), upload = vi.fn().mockRejectedValueOnce(failure(0, 'NETWORK_ERROR')).mockResolvedValue(source);
        const client = fixture({ uploadIntake: upload });
        render(<IntakeWorkspace {...{ client, formatError }} schoolId="school-1"/>);
        const input = await screen.findByLabelText('Fil') as HTMLInputElement;
        await user.upload(input, new File(['Synthetic upload'], 'synthetic.txt', { type: 'text/plain' }));
        expect(input.files).toHaveLength(1);
        // jsdom's native file validity does not recognize user-event's FileList.
        // Real Chromium covers native validation; this probe targets retry state.
        fireEvent.submit(input.form!);
        expect(upload).toHaveBeenCalledTimes(1);
        await user.click(await screen.findByRole('button', { name: 'Prøv opprinnelig innsending igjen' }));
        await waitFor(() => expect(input.files).toHaveLength(0));
        expect(upload.mock.calls[0]).toEqual(upload.mock.calls[1]);
        await user.click(screen.getByRole('button', { name: 'Importer til innboksen' }));
        expect(upload).toHaveBeenCalledTimes(2);
    });
    it('preserves a new note draft typed during the original save', async () => {
        const user = userEvent.setup(), pending = deferred<IntakeSource>(), client = fixture({ createIntakeNote: vi.fn().mockReturnValue(pending.promise) });
        render(<IntakeWorkspace {...{ client, formatError }} schoolId="school-1"/>);
        const input = await screen.findByLabelText('Notat');
        await user.type(input, 'Submitted note');
        await user.click(screen.getByRole('button', { name: 'Lagre notat' }));
        await user.clear(input); await user.type(input, 'New unsaved note');
        await act(async () => pending.resolve(source));
        expect(input).toHaveValue('New unsaved note');
    });
    it.each([false, true])('preserves a replacement file during a pending save (retry=%s)', async retry => {
        const user = userEvent.setup(), pending = deferred<IntakeSource>();
        const upload = retry ? vi.fn().mockRejectedValueOnce(failure(0, 'NETWORK_ERROR')).mockReturnValue(pending.promise) : vi.fn().mockReturnValue(pending.promise);
        const client = fixture({ uploadIntake: upload });
        render(<IntakeWorkspace {...{ client, formatError }} schoolId="school-1"/>);
        const input = await screen.findByLabelText('Fil') as HTMLInputElement;
        const oldFile = new File(['old'], 'same.txt', { type: 'text/plain', lastModified: 1 });
        const newFile = new File(['new'], 'same.txt', { type: 'text/plain', lastModified: 1 });
        await user.upload(input, oldFile);
        fireEvent.submit(input.form!);
        expect(upload).toHaveBeenCalledTimes(1);
        if (retry) await user.click(await screen.findByRole('button', { name: 'Prøv opprinnelig innsending igjen' }));
        await user.upload(input, newFile);
        await act(async () => pending.resolve(source));
        expect(input.files?.[0]).toBe(newFile);
    });
    it('preserves a newer review edit after the submitted edit succeeds', async () => {
        const user = userEvent.setup(), pending = deferred<unknown>(); let reviewed = false;
        const client = fixture({ reviewProposal: vi.fn().mockImplementation(() => { reviewed = true; return pending.promise; }), intakeProposals: vi.fn().mockImplementation(async () => ok([{ ...field, ...(reviewed ? { outcome: 'edited', state: 'reviewed', reviewed_value: 'Submitted review', version: 2 } : {}) }])) });
        render(<IntakeWorkspace {...{ client, formatError }} schoolId="school-1"/>); await open(user);
        const input = screen.getByLabelText('Rett verdi');
        await user.clear(input); await user.type(input, 'Submitted review');
        await user.click(screen.getByRole('button', { name: 'Lagre retting' }));
        await user.clear(input); await user.type(input, 'New unsaved review');
        await act(async () => pending.resolve({}));
        expect(await screen.findByLabelText('Din beholdte retting')).toHaveValue('New unsaved review');
    });
    it('keeps attribution controls fixed while their exact confirmation is pending', async () => {
        const user = userEvent.setup(), pending = deferred<unknown>();
        const client = fixture({ intakeProposals: vi.fn().mockResolvedValue(ok([{ ...field, outcome: 'accepted', state: 'reviewed' }])), reviewEvidence: vi.fn().mockReturnValue(pending.promise) });
        render(<IntakeWorkspace {...{ client, formatError }} schoolId="school-1"/>); await open(user);
        await user.selectOptions(screen.getByLabelText('Elev'), 'learner-1');
        fireEvent.change(screen.getByLabelText('Hendelsestidspunkt'), { target: { value: '2026-09-15T10:00' } });
        await user.click(screen.getByRole('button', { name: 'Bekreft avgrenset elevopplysning' }));
        expect(screen.getByLabelText('Tema')).toBeDisabled();
        expect(screen.getByLabelText('Elev')).toBeDisabled();
        await act(async () => pending.resolve({}));
    });
    it('uses Unicode code points for default and selected manual excerpts', async () => {
        const user = userEvent.setup(), client = fixture();
        render(<IntakeWorkspace {...{ client, formatError }} schoolId="school-1"/>);
        await open(user);
        await user.selectOptions(screen.getByLabelText('Felttype'), 'measure');
        await user.type(screen.getByLabelText('Feltverdi'), 'Synthetic measure');
        await user.click(screen.getByRole('button', { name: 'Lagre manuelt forslag' }));
        expect(client.proposeField).toHaveBeenCalledWith('school-1', source.id, expect.objectContaining({ span_start: 0, span_end: 18 }));
        const text = await screen.findByLabelText('Kildetekst – marker et utdrag') as HTMLTextAreaElement;
        text.setSelectionRange(10, 12);
        fireEvent.select(text);
        expect(screen.getByLabelText('Manuelt kildeutdrag')).toHaveTextContent('😀');
        expect(selectionSpan('A😀B', 1, 3)).toEqual({ start: 1, end: 2 });
    });
    it('loads all authorized learner and assignee pages and offers older inbox sources', async () => {
        const user = userEvent.setup(), client = fixture({ intake: vi.fn().mockImplementation(async (_s, offset) => offset ? ok([{ ...source, id: 'source-old', filename: 'old.txt' }]) : { items: [source], total: 2 }), intakeAssignees: vi.fn().mockImplementation(async (_s, offset) => offset ? { items: [{ id: 'last-staff', display_name: 'Last Staff' }], total: 2 } : { items: [{ id: 'first-staff', display_name: 'First Staff' }], total: 2 }), learners: vi.fn().mockImplementation(async (_s, offset) => offset ? { items: [{ id: 'last-learner', display_name: 'Last Pupil', grade: 4 }], total: 2 } : { items: [{ id: 'first-learner', display_name: 'First Pupil', grade: 4 }], total: 2 }) });
        render(<IntakeWorkspace {...{ client, formatError }} schoolId="school-1"/>);
        await user.click(await screen.findByRole('button', { name: 'Vis flere kilder' }));
        expect(await screen.findByRole('button', { name: /old.txt/ })).toBeInTheDocument();
        await open(user);
        expect(screen.getByRole('option', { name: 'Last Staff' })).toBeInTheDocument();
        expect(client.learners).toHaveBeenCalledWith('school-1', 1, 100);
    });
    it('rejects nonexistent local times and converts known local times without slicing UTC', () => { expect(() => localInstant('not-a-time')).toThrow('gyldig'); expect(localInstant('2026-09-15T10:00')).toBe(new Date('2026-09-15T10:00').toISOString()); });
});

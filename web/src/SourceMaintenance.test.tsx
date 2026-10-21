import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { useState } from 'react';
import SourceMaintenance from './SourceMaintenance';
import { ApiClient, ApiError } from './api';
import type { IntakeSource } from './types';

const original: IntakeSource = {
  id: 'original', version: 3, current_revision: 1, revision: 1, state: 'needs_review',
  external_scope: 'manual', external_id: 'stable-original', sender: 'Synthetic sender',
  document_type: 'Synthetic plan', received_at: '2026-10-21T08:00:00Z', original_at: '2026-10-20T08:00:00.000123Z',
  filename: 'original.txt', media_type: 'text/plain', digest: 'a'.repeat(64), byte_size: 20,
  scan_state: 'clean', extraction_state: 'ready', issue: null, page_count: 1, review_progress: {}, pagination: 'source_pages',
};
const revised = { ...original, version: 4, current_revision: 2, revision: 2, filename: 'revised.txt' };
const failure = (status = 0) => new ApiError('Synthetic safe failure', status, 'synthetic_failure');
function deferred<T>() { let resolve!: (value: T) => void; let reject!: (error: unknown) => void; const promise = new Promise<T>((r, j) => { resolve = r; reject = j; }); return { promise, resolve, reject }; }
function fixture(source = original) {
  let current = source;
  const client = { reviseIntake: vi.fn().mockImplementation(async () => current = revised), schoolCommand: vi.fn() } as unknown as ApiClient;
  const read = vi.fn(async () => current);
  function Harness() {
    const [row, setRow] = useState(source), [busy, setBusy] = useState(false);
    return <SourceMaintenance client={client} schoolId="school" source={row} disabled={busy} onBusy={setBusy} formatError={e => e instanceof Error ? e.message : 'Failed'} onRefresh={async () => { const value = await read(); if (value) setRow(value); return value; }}/>;
  }
  return { client, read, Harness, current: (value: IntakeSource) => { current = value; } };
}
async function choose(file = new File(['Synthetic revised source'], 'revised.txt', { type: 'text/plain' })) {
  const user = userEvent.setup();
  await user.click(screen.getByText('Last opp ny revisjon'));
  const input = screen.getByLabelText('Ny kildefil') as HTMLInputElement;
  await user.upload(input, file);
  return { user, input, file };
}
function submit(input: HTMLInputElement) { fireEvent.submit(input.form!); }

describe('source replacement and reprocessing', () => {
  it('keeps exact source identity and imported timestamp, then clears only the saved file', async () => {
    const { client, Harness } = fixture(); render(<Harness/>);
    const { input, file } = await choose(new File(['Synthetic new'], 'vurdering Æ😀.txt', { type: 'text/plain' }));
    submit(input);
    await screen.findByText(/Revisjon 2 er lagret/);
    expect(client.reviseIntake).toHaveBeenCalledWith('school', original.id, 3, file, expect.objectContaining({
      external_scope: original.external_scope, external_id: original.external_id,
      original_at: original.original_at, sender: original.sender,
    }));
    await waitFor(() => expect(input.files).toHaveLength(0));
    expect(screen.getByRole('button', { name: 'Lagre ny kilderevisjon' })).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Prøv dokumentbehandlingen på nytt' })).not.toBeInTheDocument();
  });

  it('retries a lost committed replacement reply with the identical frozen command', async () => {
    const { client, Harness } = fixture();
    vi.mocked(client.reviseIntake).mockRejectedValueOnce(failure()).mockResolvedValue(revised);
    render(<Harness/>); const { input, user } = await choose(); submit(input);
    await screen.findByText(/Utfallet er ukjent/);
    expect(input).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Prøv den samme kildehandlingen igjen' }));
    await screen.findByText(/Revisjon 2 er lagret/);
    expect(vi.mocked(client.reviseIntake).mock.calls[0]).toEqual(vi.mocked(client.reviseIntake).mock.calls[1]);
    expect(screen.queryByText(/Utfallet er ukjent/)).not.toBeInTheDocument();
  });

  it('does not clear a newer selected file or typed field when an earlier request finishes', async () => {
    const pending = deferred<IntakeSource>(), { client, Harness } = fixture();
    vi.mocked(client.reviseIntake).mockReturnValue(pending.promise);
    render(<Harness/>); const { input } = await choose(); submit(input);
    const newer = new File(['Synthetic newer'], 'newer.txt', { type: 'text/plain' });
    fireEvent.change(input, { target: { files: [newer] } });
    fireEvent.change(screen.getByLabelText('Avsender for ny revisjon'), { target: { value: 'Synthetic newer author' } });
    await act(async () => pending.resolve(revised));
    expect(input.files?.[0]).toBe(newer);
    expect(screen.getByLabelText('Avsender for ny revisjon')).toHaveValue('Synthetic newer author');
  });

  it('requires explicit comparison before using a conflicting replacement on a newer source', async () => {
    const f = fixture(); vi.mocked(f.client.reviseIntake).mockRejectedValueOnce(failure(409)).mockResolvedValue({ ...revised, version: 5, revision: 3, current_revision: 3 });
    render(<f.Harness/>); const { user, input } = await choose(); submit(input);
    await screen.findByText('Synthetic safe failure');
    f.current(revised);
    await user.click(screen.getByRole('button', { name: 'Last gjeldende kildestatus' }));
    expect(screen.getByRole('button', { name: 'Lagre ny kilderevisjon' })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Behold feltene mine og bruk gjeldende revisjon' }));
    submit(input); await screen.findByText(/Revisjon 3 er lagret/);
    const calls = vi.mocked(f.client.reviseIntake).mock.calls;
    expect(calls[0][2]).toBe(3); expect(calls[1][2]).toBe(4);
    expect(calls[0][3]).toBe(calls[1][3]);
    expect(calls[0][4].request_key).not.toBe(calls[1][4].request_key);
  });

  it('reconciles changed inspection status explicitly without claiming the original request succeeded', async () => {
    const source = { ...original, extraction_state: 'unavailable', page_count: 0, state: 'quarantined' };
    const f = fixture(source); vi.mocked(f.client.schoolCommand).mockRejectedValue(failure());
    render(<f.Harness/>); const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Prøv dokumentbehandlingen på nytt' }));
    await screen.findByText(/Utfallet er ukjent/);
    f.current({ ...source, version: 4, extraction_state: 'ready', state: 'needs_review' });
    await user.click(screen.getByRole('button', { name: 'Avklar mot gjeldende kildestatus' }));
    expect(screen.getByText(/Dette alene bekrefter ikke utfallet/)).toBeInTheDocument();
    expect(screen.getByText(/Utfallet er ukjent/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Bruk registrert status og avslutt avklaringen' }));
    expect(screen.queryByText(/Utfallet er ukjent/)).not.toBeInTheDocument();
    expect(f.client.schoolCommand).toHaveBeenCalledTimes(1);
    expect(f.client.schoolCommand).toHaveBeenCalledWith('school', ['intake', source.id, 'inspect'], { expected_version: 3 });
  });

  it('keeps unchanged inspection state uncertain and retries the original expected version', async () => {
    const source = { ...original, extraction_state: 'unavailable' }, f = fixture(source);
    vi.mocked(f.client.schoolCommand).mockRejectedValue(failure());
    render(<f.Harness/>); const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Prøv dokumentbehandlingen på nytt' }));
    await user.click(await screen.findByRole('button', { name: 'Avklar mot gjeldende kildestatus' }));
    expect(screen.queryByRole('button', { name: 'Bruk registrert status og avslutt avklaringen' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Prøv den samme kildehandlingen igjen' }));
    expect(vi.mocked(f.client.schoolCommand).mock.calls[0]).toEqual(vi.mocked(f.client.schoolCommand).mock.calls[1]);
  });

  it('reports a recorded inspection that still lacks extraction without asserting it is ready', async () => {
    const source = { ...original, extraction_state: 'unavailable' }, f = fixture(source);
    vi.mocked(f.client.schoolCommand).mockResolvedValue({ ...source, version: 4 });
    f.current({ ...source, version: 4 }); render(<f.Harness/>);
    await userEvent.setup().click(screen.getByRole('button', { name: 'Prøv dokumentbehandlingen på nytt' }));
    await screen.findByText(/dokumentet er fortsatt ikke klart/);
    expect(screen.queryByText(/Uttrekket er klart for kontroll/)).not.toBeInTheDocument();
  });

  it('keeps a recorded success separate from a failed fresh-status read', async () => {
    const f = fixture(); f.read.mockResolvedValue(undefined as unknown as IntakeSource);
    render(<f.Harness/>); const { input } = await choose(); submit(input);
    await screen.findByText(/Revisjon 2 er lagret/);
    expect(await screen.findByRole('button', { name: 'Last gjeldende kildestatus' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Lagre ny kilderevisjon' })).toBeDisabled();
  });

  it('ignores a late successful mutation after leaving this source scope', async () => {
    const pending = deferred<IntakeSource>(), f = fixture(); vi.mocked(f.client.reviseIntake).mockReturnValue(pending.promise);
    const view = render(<f.Harness/>); const { input } = await choose(); submit(input);
    view.unmount(); await act(async () => pending.resolve(revised));
    expect(f.read).not.toHaveBeenCalled();
  });
});

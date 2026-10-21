import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { ApiClient } from './api';

const session = { user: { id: 'u1', email: 'pedagog@skole.no', display_name: 'Kari Lærer' }, csrf_token: 'csrf', schools: [{ id: 's1', name: 'Solvang skole', kind: 'primary', timezone: 'Europe/Oslo', role: 'teacher' }] };

describe('workspace access flow', () => {
  it('supports keyboard sign in, authorized learner navigation, and sign out', async () => {
    const user = userEvent.setup();
    const client = {
      setSessionExpiredHandler: vi.fn(),
      me: vi.fn().mockRejectedValue(Object.assign(new Error('unauthorized'), { status: 401 })),
      login: vi.fn().mockResolvedValue(session),
      learners: vi.fn().mockResolvedValue({ total: 1, items: [{ id: 'l1', display_name: 'Ola Elev', grade: 4, group_name: '4A', version: 1 }] }),
      learner: vi.fn().mockResolvedValue({ id: 'l1', display_name: 'Ola Elev', grade: 4, group_name: '4A', version: 1, strengths: 'Nysgjerrig' }),
      logout: vi.fn().mockResolvedValue(undefined),
    } as unknown as ApiClient;
    render(<App client={client} />);
    await user.type(await screen.findByLabelText('E-postadresse'), 'pedagog@skole.no');
    await user.type(screen.getByLabelText('Passord'), 'not-a-real-secret');
    await user.click(screen.getByRole('button', { name: 'Logg inn' }));
    expect(await screen.findByRole('combobox', { name: 'Skoler' })).toHaveValue('s1');
    expect(await screen.findByRole('button', { name: /Ola Elev/ })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /Ola Elev/ }));
    expect(await screen.findByText('Nysgjerrig')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Logg ut' }));
    expect(await screen.findByLabelText('Passord')).toBeInTheDocument();
  });

  it('shows a clear server error and allows retrying the learner list', async () => {
    const user = userEvent.setup();
    const client = {
      setSessionExpiredHandler: vi.fn(), me: vi.fn().mockResolvedValue(session),
      learners: vi.fn().mockRejectedValueOnce(new Error('Tilkoblingen ble avbrutt.')).mockResolvedValue({ total: 0, items: [] }),
    } as unknown as ApiClient;
    render(<App client={client} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Tilkoblingen ble avbrutt.');
    await user.click(screen.getByRole('button', { name: 'Prøv igjen' }));
    expect(await screen.findByText('Ingen elever er tilgjengelige i denne skoleoversikten.')).toBeInTheDocument();
  });
});

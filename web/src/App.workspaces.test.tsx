import {act, render, screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {describe, expect, it, vi} from 'vitest';
import type {ApiClient} from './api';
import type {Session} from './types';
import App from './App';

// Isolate the shell's scope/lifetime behavior from each workspace's own suite.
vi.mock('./features/planning/PlanningWorkspace', () => ({default: ({learnerName}: {learnerName: string}) =>
  <label>Plan for {learnerName}<input aria-label="Ulagret planutkast" defaultValue="" /></label>}));
vi.mock('./features/teaching/TeachingWorkspace', () => ({default: ({mode, schoolId, learnerName}: {mode: string; schoolId: string; learnerName?: string}) =>
  <p>{mode === 'assistant' ? `Oppdrag ved ${schoolId}` : `Undervisning for ${learnerName}`}</p>}));
vi.mock('./features/guardian/GuardianPortal', () => ({default: ({schoolId}: {schoolId: string}) =>
  <p>Foresattbrev ved {schoolId}</p>}));

const pupil = {id: 'p1', display_name: 'Test Elev', grade: 4, group_name: 'A', version: 1};
function makeClient(role = 'teacher', schoolId = 's1') {
  const session: Session = {user: {id: 'u1', display_name: 'Test Ansatt', email: 'synthetic@example.invalid'},
    csrf_token: 'synthetic', schools: [{id: schoolId, name: schoolId, kind: 'public', timezone: 'Europe/Oslo', role}]};
  return {setSessionExpiredHandler: vi.fn(), me: vi.fn().mockResolvedValue(session),
    learners: vi.fn().mockResolvedValue({items: [pupil], total: 1}),
    learner: vi.fn().mockResolvedValue({...pupil, strengths: 'Original profile prose'})} as unknown as ApiClient;
}

describe('workspace composition', () => {
  it('opens the guardian portal without staff navigation or pupil list requests', async () => {
    const client = makeClient('guardian');
    render(<App client={client} />);
    expect(await screen.findByText('Foresattbrev ved s1')).toBeVisible();
    expect(screen.queryByRole('button', {name: 'Dokumentinnboks'})).not.toBeInTheDocument();
    expect(screen.queryByRole('button', {name: 'Mine assistentoppdrag'})).not.toBeInTheDocument();
    expect(client.learners).not.toHaveBeenCalled();
    expect(client.learner).not.toHaveBeenCalled();
  });
  it('opens the school assistant inbox without fetching a pupil dossier or list', async () => {
    const client = makeClient('assistant');
    render(<App client={client} />);
    expect(await screen.findByText('Oppdrag ved s1')).toBeVisible();
    expect(client.learners).not.toHaveBeenCalled();
    expect(client.learner).not.toHaveBeenCalled();
  });

  it('preserves a visited planning draft while switching between pupil workspaces', async () => {
    const user = userEvent.setup();
    render(<App client={makeClient()} />);
    await user.click(await screen.findByRole('button', {name: /Test Elev/}));
    await user.click(screen.getByRole('button', {name: 'Grunnlag og planer'}));
    await user.type(screen.getByLabelText('Ulagret planutkast'), 'Human draft');
    await user.click(screen.getByRole('button', {name: 'Undervisning'}));
    expect(screen.getByText('Undervisning for Test Elev')).toBeVisible();
    expect(screen.getByLabelText('Ulagret planutkast')).not.toBeVisible();
    await user.click(screen.getByRole('button', {name: 'Grunnlag og planer'}));
    expect(screen.getByLabelText('Ulagret planutkast')).toHaveValue('Human draft');
  });

  it('drops prior identity content immediately when replacing the API client', async () => {
    const user = userEvent.setup();
    const first = makeClient();
    const second = makeClient('assistant', 's2');
    let finish!: (value: Session) => void;
    const pending = new Promise<Session>(resolve => {finish = resolve;});
    vi.mocked(second.me).mockReturnValue(pending);
    const view = render(<App client={first} />);
    await user.click(await screen.findByRole('button', {name: /Test Elev/}));
    expect(await screen.findByText('Original profile prose')).toBeVisible();
    view.rerender(<App client={second} />);
    expect(screen.queryByText('Original profile prose')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', {name: 'Grunnlag og planer'})).not.toBeInTheDocument();
    await act(async () => finish({user: {id: 'u2', display_name: 'New staff', email: 'new@example.invalid'}, csrf_token: 'synthetic',
      schools: [{id: 's2', name: 's2', kind: 'public', timezone: 'Europe/Oslo', role: 'assistant'}]}));
    expect(await screen.findByText('Oppdrag ved s2')).toBeVisible();
    expect(screen.queryByText('Original profile prose')).not.toBeInTheDocument();
  });
});

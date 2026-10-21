import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { act } from 'react';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { ApiClient, ApiError } from './api';
import type { Learner, Session } from './types';
import './styles.css';

const school = (id: string, name: string) => ({ id, name, kind: 'primary', timezone: 'Europe/Oslo', role: 'teacher' });
const session = (userId = 'u1', schools = [school('s1', 'Solvang skole')]): Session => ({
  user: { id: userId, email: `${userId}@skole.no`, display_name: userId === 'u1' ? 'Kari Lærer' : 'Ola Lærer' },
  csrf_token: `csrf-${userId}`,
  schools,
});
const learner = (id: string, name: string): Learner => ({ id, display_name: name, grade: 4, group_name: '4A', version: 1 });
const profile = (record: Learner) => ({ ...record, strengths: `Styrke ${record.display_name}` });

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

async function pressTabUntil(user: ReturnType<typeof userEvent.setup>, element: Element) {
  for (let index = 0; index < 12; index += 1) {
    await user.tab();
    if (document.activeElement === element) return;
  }
  throw new Error('Could not reach the target using the keyboard tab order.');
}

function luminance(color: string): number {
  const channels = color.match(/[\d.]+/g)?.slice(0, 3).map(Number) ?? [];
  const linear = channels.map((channel) => {
    const value = channel / 255;
    return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];
}

function contrast(foreground: string, background: string): number {
  const values = [luminance(foreground), luminance(background)].sort((a, b) => b - a);
  return (values[0] + 0.05) / (values[1] + 0.05);
}

function composite(foreground: string, background: string, alpha: number): string {
  const fg = foreground.match(/[\d.]+/g)!.slice(0, 3).map(Number);
  const bg = background.match(/[\d.]+/g)!.slice(0, 3).map(Number);
  return `rgb(${fg.map((channel, index) => Math.round(channel * alpha + bg[index] * (1 - alpha))).join(', ')})`;
}

describe('workspace access flow', () => {
  it('uses keyboard tab order and Enter for sign in, learner profile, back, and logout', async () => {
    const user = userEvent.setup();
    const record = learner('l1', 'Ola Elev');
    const client = {
      setSessionExpiredHandler: vi.fn(),
      me: vi.fn().mockRejectedValue(new ApiError('Sign in to continue.', 401, 'authentication_required')),
      login: vi.fn().mockResolvedValue(session()),
      learners: vi.fn().mockResolvedValue({ total: 1, items: [record] }),
      learner: vi.fn().mockResolvedValue(profile(record)),
      logout: vi.fn().mockResolvedValue(undefined),
    } as unknown as ApiClient;
    render(<App client={client} />);
    const email = await screen.findByLabelText('E-postadresse');
    expect(email).toHaveFocus();
    await user.keyboard('pedagog@skole.no');
    await user.keyboard('{Tab}');
    const password = screen.getByLabelText('Passord');
    expect(password).toHaveFocus();
    await user.keyboard('not-a-real-secret');
    await user.keyboard('{Tab}{Enter}');

    expect(await screen.findByRole('combobox', { name: 'Skoler' })).toHaveValue('s1');
    const learnerButton = await screen.findByRole('button', { name: /Ola Elev/ });
    await pressTabUntil(user, learnerButton);
    await user.keyboard('{Enter}');
    expect(await screen.findByText('Styrke Ola Elev')).toBeInTheDocument();

    const back = screen.getByRole('button', { name: 'Tilbake til elevlisten' });
    await pressTabUntil(user, back);
    await user.keyboard('{Enter}');
    const logout = screen.getByRole('button', { name: 'Logg ut' });
    await pressTabUntil(user, logout);
    await user.keyboard('{Enter}');
    expect(await screen.findByLabelText('Passord')).toBeInTheDocument();
  });

  it('ignores late profile success and error responses after switching pupil, school, or user', async () => {
    const user = userEvent.setup();
    const firstSchool = school('s1', 'Solvang skole');
    const secondSchool = school('s2', 'Fjell skole');
    const firstSession = session('u1', [firstSchool, secondSchool]);
    const secondSession = session('u2', [secondSchool]);
    const alpha = learner('l1', 'Alpha elev');
    const beta = learner('l2', 'Beta elev');
    const alphaSuccess = deferred<ReturnType<typeof profile>>();
    const alphaError = deferred<ReturnType<typeof profile>>();
    const betaProfile = deferred<ReturnType<typeof profile>>();
    let alphaRequests = 0;
    const loginQueue = [secondSession];
    const client = {
      setSessionExpiredHandler: vi.fn(),
      me: vi.fn().mockResolvedValue(firstSession),
      login: vi.fn().mockImplementation(() => Promise.resolve(loginQueue.shift()!)),
      logout: vi.fn().mockResolvedValue(undefined),
      learners: vi.fn().mockImplementation((schoolId: string) => Promise.resolve({ total: 1, items: [schoolId === 's1' ? alpha : beta] })),
      learner: vi.fn().mockImplementation((_schoolId: string, learnerId: string) => {
        if (learnerId !== alpha.id) return betaProfile.promise;
        alphaRequests += 1;
        return alphaRequests === 1 ? alphaSuccess.promise : alphaError.promise;
      }),
    } as unknown as ApiClient;
    render(<App client={client} />);

    await user.selectOptions(await screen.findByRole('combobox', { name: 'Skoler' }), 's1');
    await user.click(await screen.findByRole('button', { name: /Alpha elev/ }));
    await user.click(screen.getByRole('button', { name: 'Tilbake til elevlisten' }));
    await user.click(await screen.findByRole('button', { name: /Alpha elev/ }));
    await user.selectOptions(screen.getByRole('combobox', { name: 'Skoler' }), 's2');
    await user.click(await screen.findByRole('button', { name: /Beta elev/ }));
    await act(async () => { betaProfile.resolve(profile(beta)); });
    expect(await screen.findByText('Styrke Beta elev')).toBeInTheDocument();
    await act(async () => { alphaSuccess.resolve(profile(alpha)); });
    await act(async () => { alphaError.reject(new ApiError('You do not have access to this operation.', 403, 'access_denied')); });
    expect(screen.getByText('Styrke Beta elev')).toBeInTheDocument();
    expect(screen.queryByText('Styrke Alpha elev')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Logg ut' }));
    await user.type(await screen.findByLabelText('E-postadresse'), 'u2@skole.no');
    await user.type(screen.getByLabelText('Passord'), 'safe-test-only');
    await user.click(screen.getByRole('button', { name: 'Logg inn' }));
    expect(await screen.findByRole('combobox', { name: 'Skoler' })).toHaveValue('s2');
    expect(await screen.findByRole('button', { name: /Beta elev/ })).toBeInTheDocument();
    expect(screen.queryByText('Styrke Alpha elev')).not.toBeInTheDocument();
  });

  it('ignores an old school retry after selecting another school', async () => {
    const user = userEvent.setup();
    const first = school('s1', 'Solvang skole');
    const second = school('s2', 'Fjell skole');
    const retry = deferred<{ total: number; items: Learner[] }>();
    let firstSchoolCalls = 0;
    const client = {
      setSessionExpiredHandler: vi.fn(), me: vi.fn().mockResolvedValue(session('u1', [first, second])),
      learners: vi.fn().mockImplementation((schoolId: string) => {
        if (schoolId === 's1') {
          firstSchoolCalls += 1;
          if (firstSchoolCalls === 1) return Promise.reject(new ApiError('Service unavailable.', 503, 'HTTP_503'));
          return retry.promise;
        }
        return Promise.resolve({ total: 1, items: [learner('new', 'Fjell elev')] });
      }),
    } as unknown as ApiClient;
    render(<App client={client} />);

    await user.selectOptions(await screen.findByRole('combobox', { name: 'Skoler' }), 's1');
    expect(await screen.findByRole('alert')).toHaveTextContent('Noe gikk galt.');
    await user.click(screen.getByRole('button', { name: 'Prøv igjen' }));
    await user.selectOptions(screen.getByRole('combobox', { name: 'Skoler' }), 's2');
    expect(await screen.findByRole('button', { name: /Fjell elev/ })).toBeInTheDocument();
    await act(async () => { retry.resolve({ total: 1, items: [learner('old', 'Gammal elev')] }); });
    expect(screen.getByRole('button', { name: /Fjell elev/ })).toBeInTheDocument();
    expect(screen.queryByText('Gammal elev')).not.toBeInTheDocument();
  });

  it('ignores a learner retry that resolves after another user signs in', async () => {
    const user = userEvent.setup();
    const oldRetry = deferred<{ total: number; items: Learner[] }>();
    let calls = 0;
    const client = {
      setSessionExpiredHandler: vi.fn(),
      me: vi.fn().mockResolvedValue(session('u1')),
      login: vi.fn().mockResolvedValue(session('u2')),
      logout: vi.fn().mockResolvedValue(undefined),
      learners: vi.fn().mockImplementation(() => {
        calls += 1;
        if (calls === 1) return Promise.reject(new ApiError('Unavailable.', 503, 'HTTP_503'));
        if (calls === 2) return oldRetry.promise;
        return Promise.resolve({ total: 1, items: [learner('new', 'Ny bruker sin elev')] });
      }),
    } as unknown as ApiClient;
    render(<App client={client} />);
    await screen.findByRole('alert');
    await user.click(screen.getByRole('button', { name: 'Prøv igjen' }));
    await user.click(screen.getByRole('button', { name: 'Logg ut' }));
    await user.type(await screen.findByLabelText('E-postadresse'), 'u2@skole.no');
    await user.type(screen.getByLabelText('Passord'), 'safe-test-only');
    await user.click(screen.getByRole('button', { name: 'Logg inn' }));
    expect(await screen.findByRole('button', { name: /Ny bruker sin elev/ })).toBeInTheDocument();
    await act(async () => { oldRetry.resolve({ total: 1, items: [learner('old', 'Forrige bruker sin elev')] }); });
    expect(screen.getByRole('button', { name: /Ny bruker sin elev/ })).toBeInTheDocument();
    expect(screen.queryByText('Forrige bruker sin elev')).not.toBeInTheDocument();
  });

  it('does not restore a prior user profile after logout and a different user login', async () => {
    const user = userEvent.setup();
    const oldRecord = learner('old', 'Tidlegare elev');
    const newRecord = learner('new', 'Ny elev');
    const oldProfile = deferred<ReturnType<typeof profile>>();
    let learnerLoad = 0;
    const client = {
      setSessionExpiredHandler: vi.fn(),
      me: vi.fn().mockResolvedValue(session('u1')),
      logout: vi.fn().mockResolvedValue(undefined),
      login: vi.fn().mockResolvedValue(session('u2')),
      learners: vi.fn().mockImplementation(() => Promise.resolve({ total: 1, items: [++learnerLoad === 1 ? oldRecord : newRecord] })),
      learner: vi.fn().mockImplementation((_schoolId: string, learnerId: string) => learnerId === oldRecord.id ? oldProfile.promise : Promise.resolve(profile(newRecord))),
    } as unknown as ApiClient;
    render(<App client={client} />);
    await user.click(await screen.findByRole('button', { name: /Tidlegare elev/ }));
    await user.click(screen.getByRole('button', { name: 'Logg ut' }));
    await user.type(await screen.findByLabelText('E-postadresse'), 'u2@skole.no');
    await user.type(screen.getByLabelText('Passord'), 'safe-test-only');
    await user.click(screen.getByRole('button', { name: 'Logg inn' }));
    expect(await screen.findByRole('button', { name: /Ny elev/ })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /Ny elev/ }));
    expect(await screen.findByText('Styrke Ny elev')).toBeInTheDocument();
    await act(async () => { oldProfile.resolve(profile(oldRecord)); });
    expect(screen.getByText('Styrke Ny elev')).toBeInTheDocument();
    expect(screen.queryByText('Styrke Tidlegare elev')).not.toBeInTheDocument();
  });

  it('shows all learners through the backend offset/limit pages and retains the total', async () => {
    const user = userEvent.setup();
    const records = Array.from({ length: 50 }, (_, index) => learner(`l${index + 1}`, `Elev ${index + 1}`));
    const last = learner('l51', 'Elev 51');
    const client = {
      setSessionExpiredHandler: vi.fn(), me: vi.fn().mockResolvedValue(session()),
      learners: vi.fn().mockImplementation((_schoolId: string, offset = 0, limit = 50) => Promise.resolve({
        total: 51,
        items: offset === 0 ? records.slice(0, limit) : [last],
      })),
    } as unknown as ApiClient;
    render(<App client={client} />);
    expect(await screen.findByText('Viser 1–50 av 51')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Elev 51/ })).not.toBeInTheDocument();
    const next = screen.getByRole('button', { name: 'Neste' });
    next.focus();
    await user.keyboard('{Enter}');
    expect(await screen.findByRole('button', { name: /Elev 51/ })).toBeInTheDocument();
    expect(screen.getByText('Viser 51–51 av 51')).toBeInTheDocument();
    expect(client.learners).toHaveBeenLastCalledWith('s1', 50, 50);
  });

  it('does not describe unsupported pedagogical fields as confirmed empty', async () => {
    const user = userEvent.setup();
    const record = learner('l1', 'Ola Elev');
    const client = {
      setSessionExpiredHandler: vi.fn(), me: vi.fn().mockResolvedValue(session()),
      learners: vi.fn().mockResolvedValue({ total: 1, items: [record] }),
      learner: vi.fn().mockResolvedValue(record),
    } as unknown as ApiClient;
    render(<App client={client} />);
    await user.click(await screen.findByRole('button', { name: /Ola Elev/ }));
    expect(await screen.findByText('Pedagogiske profilopplysninger utover grunnopplysningene vises ikke her ennå.')).toBeInTheDocument();
  });

  it('uses Nynorsk for code-mapped backend errors and network failures', async () => {
    const user = userEvent.setup();
    const client = {
      setSessionExpiredHandler: vi.fn(),
      me: vi.fn().mockRejectedValue(new ApiError('Sign in to continue.', 401, 'authentication_required')),
      login: vi.fn()
        .mockRejectedValueOnce(new ApiError('Could not connect.', 0, 'NETWORK_ERROR'))
        .mockRejectedValueOnce(new ApiError('The email or password is incorrect.', 401, 'invalid_credentials')),
    } as unknown as ApiClient;
    render(<App client={client} />);
    await user.selectOptions(await screen.findByRole('combobox', { name: 'Språk' }), 'nn');
    await user.type(screen.getByLabelText('E-postadresse'), 'u1@skole.no');
    await user.type(screen.getByLabelText('Passord'), 'safe-test-only');
    await user.click(screen.getByRole('button', { name: 'Logg inn' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Fekk ikkje kontakt med SpesPed.');
    await user.click(screen.getByRole('button', { name: 'Logg inn' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('E-postadressa eller passordet er feil.');
    expect(document.documentElement).toHaveAttribute('lang', 'nn');
  });

  it('keeps school selection visible at a narrow viewport and renders readable muted text', async () => {
    window.innerWidth = 390;
    const user = userEvent.setup();
    const client = {
      setSessionExpiredHandler: vi.fn(), me: vi.fn().mockResolvedValue(session('u1', [school('s1', 'Solvang skole'), school('s2', 'Fjell skole')])),
      learners: vi.fn().mockResolvedValue({ total: 1, items: [learner('l1', 'Ola Elev')] }),
    } as unknown as ApiClient;
    render(<App client={client} />);
    const schoolSelect = await screen.findByRole('combobox', { name: 'Skoler' });
    expect(getComputedStyle(schoolSelect).display).not.toBe('none');
    await pressTabUntil(user, schoolSelect);
    await user.selectOptions(schoolSelect, 's1');
    expect(schoolSelect).toHaveValue('s1');
    const learnerMeta = await screen.findByText('Trinn 4 · 4A');
    expect(learnerMeta).toHaveClass('learner-meta');
    expect(getComputedStyle(document.documentElement).getPropertyValue('--muted').trim()).toBe('#536057');
    const pageBackground = getComputedStyle(document.documentElement).backgroundColor;
    const muted = 'rgb(83, 96, 87)';
    const headingColor = getComputedStyle(document.querySelector('.topbar .eyebrow')!).color;
    const headerBackground = composite('rgb(255, 255, 255)', pageBackground, 0.55);
    expect(contrast(muted, pageBackground)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(muted, 'rgb(255, 255, 255)')).toBeGreaterThanOrEqual(4.5);
    expect(contrast(headingColor, headerBackground)).toBeGreaterThanOrEqual(4.5);
  });
});


describe("trusted local teaching validation in the actual App", () => {
  async function teachingApp() {
    const record = learner("l1", "Syntetisk elev");
    const client = {
      setSessionExpiredHandler: vi.fn(),
      me: vi.fn().mockResolvedValue(session()),
      schools: vi.fn().mockResolvedValue(session().schools),
      learners: vi.fn().mockResolvedValue({ items: [record], total: 1 }),
      learner: vi.fn().mockResolvedValue(profile(record)),
      schoolGet: vi.fn().mockResolvedValue({ items: [], total: 0 }),
      schoolCommand: vi.fn(),
    } as unknown as ApiClient;
    render(<App client={client} />);
    await userEvent.click(
      await screen.findByRole("button", { name: /Syntetisk elev/ }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Undervisning" }));
    await screen.findByRole("button", { name: "Planlegg ny økt" });
    return client;
  }
  it("shows corrective nonexistent school-time validation without submitting a basis", async () => {
    const client = await teachingApp();
    await userEvent.click(
      screen.getByRole("button", { name: "Planlegg ny økt" }),
    );
    fireEvent.change(
      screen.getByLabelText("Planlagt tidspunkt (Europe/Oslo)"),
      { target: { value: "2027-03-28T02:30" } },
    );
    fireEvent.change(screen.getByLabelText("Arena"), {
      target: { value: "Syntetisk rom" },
    });
    await userEvent.click(
      screen.getByRole("button", { name: "Bekreft valgt grunnlag" }),
    );
    expect(
      await screen.findByText(
        "Klokkeslettet finnes ikke i skolens tidssone. Velg et annet klokkeslett.",
      ),
    ).toBeVisible();
    expect(client.schoolCommand).not.toHaveBeenCalled();
  });
  it("shows the authored ITO instruction and keeps the incomplete actual record unsent", async () => {
    const client = await teachingApp();
    await userEvent.click(
      screen.getByRole("button", { name: "Gjennomføring" }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Registrer faktisk økt" }),
    );
    fireEvent.change(screen.getByLabelText("Faktisk start (Europe/Oslo)"), {
      target: { value: "2026-10-20T12:00" },
    });
    fireEvent.change(
      screen.getByLabelText("Faktisk hendelsesvarighet i minutter"),
      { target: { value: "30" } },
    );
    fireEvent.change(screen.getByLabelText("Faktisk aktivitet"), {
      target: { value: "Syntetisk faktisk aktivitet" },
    });
    await userEvent.selectOptions(
      screen.getByLabelText("Støtteform, registrering 1"),
      "individually_adapted_education",
    );
    fireEvent.change(
      screen.getByLabelText("Faktiske elevminutter, registrering 1"),
      { target: { value: "30" } },
    );
    fireEvent.change(
      screen.getByLabelText("Støtte som ble gitt, registrering 1"),
      { target: { value: "Rapportert støtte" } },
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Bekreft faktisk gjennomføring" }),
    );
    expect(
      await screen.findByText(
        "ITO uten vurdert kvalifikasjonsgrunnlag registreres som delvis gjennomføring med årsak og ansvarlig oppfølging.",
      ),
    ).toBeVisible();
    expect(client.schoolCommand).not.toHaveBeenCalled();
  });
  it("keeps the generic fallback for an unexpected Error rather than exposing its message", async () => {
    const client = {
      setSessionExpiredHandler: vi.fn(),
      me: vi.fn().mockRejectedValue(new Error("PRIVATE_UNEXPECTED_DIAGNOSTIC")),
    } as unknown as ApiClient;
    render(<App client={client} />);
    expect(
      await screen.findByText(
        "Noe gikk galt. Prøv igjen, eller kontakt systemansvarlig.",
      ),
    ).toBeVisible();
    expect(
      screen.queryByText("PRIVATE_UNEXPECTED_DIAGNOSTIC"),
    ).not.toBeInTheDocument();
  });
});

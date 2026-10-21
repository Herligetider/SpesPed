import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { ApiClient, ApiError, api } from './api';
import IntakeWorkspace from './IntakeWorkspace';
import { localizeApiError, translate } from './i18n';
import type { Language, MessageKey } from './i18n';
import type { Learner, LearnerProfile, Session } from './types';

type LoadState<T> = { status: 'loading' } | { status: 'error'; error: unknown } | { status: 'ready'; value: T };
type LearnerPage = { items: Learner[]; total: number; offset: number; limit: number };
const pageSize = 50;

export default function App({ client = api }: { client?: ApiClient }) {
  const [language, setLanguage] = useState<Language>(() => localStorage.getItem('spesped-language') === 'nn' ? 'nn' : 'nb');
  const [session, setSession] = useState<Session | null>(null);
  const [booting, setBooting] = useState(true);
  const [notice, setNotice] = useState('');
  const [selectedSchoolId, setSelectedSchoolId] = useState('');
  const [learnerOffset, setLearnerOffset] = useState(0);
  const [listReload, setListReload] = useState(0);
  const [learners, setLearners] = useState<LoadState<LearnerPage>>({ status: 'loading' });
  const [profile, setProfile] = useState<LoadState<LearnerProfile> | null>(null);
  const [selectedLearner, setSelectedLearner] = useState<Learner | null>(null);
  const [signingOut, setSigningOut] = useState(false);
  const [workspace, setWorkspace] = useState<'learners' | 'intake'>('learners');
  const authGeneration = useRef(0);
  const profileGeneration = useRef(0);
  const languageRef = useRef(language);
  const t = (key: Exclude<MessageKey, 'learnerCount' | 'pageSummary'>) => translate(language, key);
  const school = session?.schools.find((item) => item.id === selectedSchoolId) ?? null;

  function displayError(error: unknown): string {
    if (error instanceof ApiError) return localizeApiError(language, error.code, error.message);
    return translate(language, 'genericError');
  }

  useEffect(() => {
    languageRef.current = language;
    document.documentElement.lang = language;
  }, [language]);

  useEffect(() => {
    let active = true;
    const generation = ++authGeneration.current;
    client.setSessionExpiredHandler(() => {
      authGeneration.current += 1;
      profileGeneration.current += 1;
      setBooting(false);
      setSigningOut(false);
      setSession(null);
      setSelectedSchoolId('');
      setLearnerOffset(0);
      setProfile(null);
      setSelectedLearner(null);
      setNotice(translate(languageRef.current, 'sessionExpired'));
    });
    client.me().then((current) => {
      if (!active || generation !== authGeneration.current) return;
      profileGeneration.current += 1;
      setSession(current);
      setSelectedSchoolId(current.schools.length === 1 ? current.schools[0].id : '');
      setLearnerOffset(0);
    }).catch((error) => {
      if (active && generation === authGeneration.current && !(error instanceof ApiError && error.status === 401)) setNotice(displayError(error));
    }).finally(() => {
      if (active && generation === authGeneration.current) setBooting(false);
    });
    return () => {
      active = false;
      if (authGeneration.current === generation) authGeneration.current += 1;
      client.setSessionExpiredHandler(() => undefined);
    };
  }, [client]);

  useEffect(() => {
    if (!session || !school) {
      setLearners({ status: 'ready', value: { items: [], total: 0, offset: 0, limit: pageSize } });
      return;
    }
    let active = true;
    setLearners({ status: 'loading' });
    setProfile(null);
    setSelectedLearner(null);
    client.learners(school.id, learnerOffset, pageSize).then((result) => {
      if (active) setLearners({ status: 'ready', value: { ...result, offset: learnerOffset, limit: pageSize } });
    }).catch((error) => {
      if (active) setLearners({ status: 'error', error });
    });
    return () => { active = false; };
  }, [client, school?.id, session, learnerOffset, listReload]);

  function changeLanguage(value: Language) {
    setLanguage(value);
    localStorage.setItem('spesped-language', value);
    document.documentElement.lang = value;
  }

  async function signIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const email = String(data.get('email') ?? '').trim();
    const password = String(data.get('password') ?? '');
    const generation = ++authGeneration.current;
    profileGeneration.current += 1;
    setNotice('');
    try {
      const current = await client.login(email, password);
      if (generation !== authGeneration.current) return;
      setSession(current);
      setSelectedSchoolId(current.schools.length === 1 ? current.schools[0].id : '');
      setLearnerOffset(0);
    } catch (error) {
      if (generation === authGeneration.current) setNotice(displayError(error));
    }
  }

  async function signOut() {
    const generation = ++authGeneration.current;
    profileGeneration.current += 1;
    setSigningOut(true);
    setNotice('');
    try {
      await client.logout();
      if (generation !== authGeneration.current) return;
      setSession(null);
      setSelectedSchoolId('');
      setLearnerOffset(0);
      setProfile(null);
      setSelectedLearner(null);
    } catch (error) {
      if (generation === authGeneration.current) setNotice(displayError(error));
    } finally {
      if (generation === authGeneration.current) setSigningOut(false);
    }
  }

  async function openProfile(learner: Learner) {
    if (!school) return;
    const generation = ++profileGeneration.current;
    const schoolId = school.id;
    setSelectedLearner(learner);
    setProfile({ status: 'loading' });
    try {
      const result = await client.learner(schoolId, learner.id);
      if (generation !== profileGeneration.current) return;
      setProfile({ status: 'ready', value: result });
    } catch (error) {
      if (generation === profileGeneration.current) setProfile({ status: 'error', error });
    }
  }

  function changeSchool(value: string) {
    profileGeneration.current += 1;
    setSelectedSchoolId(value);
    setLearnerOffset(0);
    setSelectedLearner(null);
    setProfile(null);
  }

  function leaveProfile() {
    profileGeneration.current += 1;
    setSelectedLearner(null);
    setProfile(null);
  }

  if (booting) return <main className="center-state" aria-live="polite">{t('loading')}</main>;
  if (!session) return <Login t={t} language={language} changeLanguage={changeLanguage} onSubmit={signIn} notice={notice} />;

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">{t('skipToMain')}</a>
      <aside className="sidebar" aria-label={t('workspace')}>
        <a className="brand" href="#main-content" aria-label="SpesPed – arbeidsflate"><span className="brand-mark" aria-hidden="true">S</span><span>SpesPed</span></a>
        <div className="side-section-label">{t('workspace')}</div>
        <label className="field-label" htmlFor="school-select">{t('schools')}</label>
        <select id="school-select" value={selectedSchoolId} onChange={(event) => changeSchool(event.target.value)}>
          <option value="">{t('chooseSchool')}</option>
          {session.schools.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
        </select>
        <nav aria-label={t('workspace')} className="main-nav">
          <button className={`nav-item ${school && workspace === 'learners' ? 'active' : ''}`} aria-current={workspace === 'learners' ? 'page' : undefined} type="button" onClick={() => {setWorkspace('learners');leaveProfile();}}>
            <span className="nav-icon" aria-hidden="true">▦</span>{t('learners')}
          </button>
          <button className={`nav-item ${school && workspace === 'intake' ? 'active' : ''}`} aria-current={workspace === 'intake' ? 'page' : undefined} type="button" onClick={() => {setWorkspace('intake');leaveProfile();}}>
            <span className="nav-icon" aria-hidden="true">⇧</span>Dokumentinnboks
          </button>
        </nav>
        <div className="sidebar-bottom">
          <div className="signed-in"><span className="avatar" aria-hidden="true">{session.user.display_name.slice(0, 1).toLocaleUpperCase(language)}</span><span className="signed-in-copy"><strong>{session.user.display_name}</strong><span>{session.user.email}</span></span></div>
          <label className="field-label" htmlFor="language-select">{t('language')}</label>
          <select id="language-select" value={language} onChange={(event) => changeLanguage(event.target.value as Language)}>
            <option value="nb">{t('bokmal')}</option><option value="nn">{t('nynorsk')}</option>
          </select>
          <button className="logout-button" type="button" onClick={signOut} disabled={signingOut}>{signingOut ? t('signingOut') : t('signOut')}</button>
        </div>
      </aside>
      <main id="main-content" className="main-panel">
        <header className="topbar"><div><div className="eyebrow">{school?.name ?? t('appName')}</div><h1>{selectedLearner ? t('profile') : workspace === 'intake' ? 'Dokumentinnboks' : t('learners')}</h1></div><div className="topbar-user" aria-label={session.user.display_name}>{session.user.display_name}</div></header>
        <div className="content-wrap">
          {notice && <div className="notice" role="status">{notice}</div>}
          {!session.schools.length ? <EmptyState title={t('schools')} message={t('noSchools')} /> : !school ? <EmptyState title={t('chooseSchool')} message={t('selectSchool')} /> : workspace === 'intake' ? (
            <IntakeWorkspace client={client} schoolId={school.id} formatError={displayError} />
          ) : selectedLearner ? (
            <ProfilePanel learner={selectedLearner} profile={profile} t={t} formatError={displayError} onBack={leaveProfile} onRetry={() => openProfile(selectedLearner)} />
          ) : <LearnerList state={learners} t={t} language={language} formatError={displayError} onOpen={openProfile} onRetry={() => setListReload((value) => value + 1)} onPageChange={setLearnerOffset} />}
        </div>
      </main>
    </div>
  );
}

function Login({ t, language, changeLanguage, onSubmit, notice }: { t: (key: Exclude<MessageKey, 'learnerCount' | 'pageSummary'>) => string; language: Language; changeLanguage: (value: Language) => void; onSubmit: (event: FormEvent<HTMLFormElement>) => Promise<void>; notice: string }) {
  const [submitting, setSubmitting] = useState(false);
  return <main className="login-page">
    <div className="login-language"><label htmlFor="login-language">{t('language') as string}</label><select id="login-language" value={language} onChange={(event) => changeLanguage(event.target.value as Language)}><option value="nb">{t('bokmal') as string}</option><option value="nn">{t('nynorsk') as string}</option></select></div>
    <section className="login-card" aria-labelledby="login-title">
      <a className="brand login-brand" href="#login-title"><span className="brand-mark" aria-hidden="true">S</span><span>SpesPed</span></a>
      <p className="eyebrow">{t('appName') as string} · {t('workspace') as string}</p>
      <h1 id="login-title">{t('signInTitle') as string}</h1><p className="muted">{t('signInHelp') as string}</p>
      <form onSubmit={async (event) => { setSubmitting(true); await onSubmit(event); setSubmitting(false); }}>
        <label htmlFor="email">{t('email') as string}</label><input id="email" name="email" type="email" autoComplete="username" required autoFocus />
        <label htmlFor="password">{t('password') as string}</label><input id="password" name="password" type="password" autoComplete="current-password" required />
        {notice && <div className="form-error" role="alert">{notice}</div>}
        <button className="primary-button" type="submit" disabled={submitting}>{submitting ? t('signingIn') as string : t('signIn') as string}</button>
      </form>
    </section>
  </main>;
}

function EmptyState({ title, message }: { title: string; message: string }) {
  return <section className="empty-state"><div className="empty-mark" aria-hidden="true">S</div><h2>{title}</h2><p>{message}</p></section>;
}

function LearnerList({ state, t, language, formatError, onOpen, onRetry, onPageChange }: { state: LoadState<LearnerPage>; t: (key: Exclude<MessageKey, 'learnerCount' | 'pageSummary'>) => string; language: Language; formatError: (error: unknown) => string; onOpen: (learner: Learner) => void; onRetry: () => void; onPageChange: (offset: number) => void }) {
  if (state.status === 'loading') return <div className="inline-state" role="status">{t('loading') as string}</div>;
  if (state.status === 'error') return <div className="error-panel" role="alert"><h2>{t('loadError')}</h2><p>{formatError(state.error)}</p><button className="secondary-button" onClick={onRetry}>{t('retry')}</button></div>;
  if (!state.value.total) return <EmptyState title={t('learners')} message={t('noLearners')} />;
  const count = translate(language, 'learnerCount');
  const summary = translate(language, 'pageSummary');
  const first = state.value.offset + 1;
  const last = Math.min(state.value.offset + state.value.items.length, state.value.total);
  return <section aria-labelledby="learner-list-title"><div className="list-heading"><div><h2 id="learner-list-title">{t('learners')}</h2><p>{count(state.value.total)}</p></div></div>
    <ul className="learner-list">{state.value.items.map((learner) => <li key={learner.id}><button className="learner-row" type="button" onClick={() => onOpen(learner)}><span className="learner-avatar" aria-hidden="true">{learner.display_name.slice(0, 1).toLocaleUpperCase()}</span><span className="learner-name">{learner.display_name}</span><span className="learner-meta">{t('grade')} {learner.grade}{learner.group_name ? ` · ${learner.group_name}` : ''}</span><span className="row-arrow" aria-hidden="true">›</span></button></li>)}</ul>
    <div className="pagination" aria-label={t('pagination')}><button className="secondary-button" type="button" disabled={state.value.offset === 0} onClick={() => onPageChange(Math.max(0, state.value.offset - state.value.limit))}>{t('previousPage')}</button><p aria-live="polite">{summary(first, last, state.value.total)}</p><button className="secondary-button" type="button" disabled={last >= state.value.total} onClick={() => onPageChange(state.value.offset + state.value.limit)}>{t('nextPage')}</button></div>
  </section>;
}

function ProfilePanel({ learner, profile, t, formatError, onBack, onRetry }: { learner: Learner; profile: LoadState<LearnerProfile> | null; t: (key: Exclude<MessageKey, 'learnerCount' | 'pageSummary'>) => string; formatError: (error: unknown) => string; onBack: () => void; onRetry: () => void }) {
  return <section className="profile-panel" aria-labelledby="profile-name">
    <button className="back-link" onClick={onBack} type="button"><span aria-hidden="true">←</span> {t('backToLearners') as string}</button>
    {profile?.status === 'loading' && <div className="inline-state" role="status">{t('loading') as string}</div>}
    {profile?.status === 'error' && <div className="error-panel" role="alert"><h2>{t('loadError')}</h2><p>{formatError(profile.error)}</p><button className="secondary-button" onClick={onRetry}>{t('retry')}</button></div>}
    {profile?.status === 'ready' && <>
      <div className="profile-heading"><span className="profile-avatar" aria-hidden="true">{profile.value.display_name.slice(0, 1).toLocaleUpperCase()}</span><div><p className="eyebrow">{t('overview') as string}</p><h2 id="profile-name">{profile.value.display_name}</h2><p>{t('grade') as string} {profile.value.grade} · {profile.value.group_name || t('unassigned') as string}</p></div></div>
      <div className="profile-details"><Detail label={t('strengths') as string} value={profile.value.strengths} /><Detail label={t('interests') as string} value={profile.value.interests} /><Detail label={t('languages') as string} value={profile.value.languages?.join(', ')} /><Detail label={t('communication') as string} value={profile.value.communication} /><Detail label={t('support') as string} value={profile.value.support_strategies} />
        {!profile.value.strengths && !profile.value.interests && !profile.value.languages?.length && !profile.value.communication && !profile.value.support_strategies && <p className="muted profile-empty">{t('profileDetailsUnavailable')}</p>}
      </div>
      {profile.value.updated_at && <p className="profile-date">{t('lastReviewed') as string}: <time dateTime={profile.value.updated_at}>{new Date(profile.value.updated_at).toLocaleDateString()}</time></p>}
    </>}
    {profile === null && <div className="inline-state" role="status">{t('loading')} {learner.display_name}</div>}
  </section>;
}

function Detail({ label, value }: { label: string; value?: string | null }) {
  if (!value) return null;
  return <div className="detail-row"><h3>{label}</h3><p>{value}</p></div>;
}

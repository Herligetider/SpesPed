export type Language = 'nb' | 'nn';

const messages = {
  nb: {
    appName: 'SpesPed', signIn: 'Logg inn', signInTitle: 'Velkommen tilbake', signInHelp: 'Logg inn med brukerkontoen du har fått fra skolen.', skipToMain: 'Hopp til hovedinnhold',
    email: 'E-postadresse', password: 'Passord', signingIn: 'Logger inn …', loginError: 'Innloggingen mislyktes',
    workspace: 'Arbeidsflate', schools: 'Skoler', chooseSchool: 'Velg skole', learners: 'Elever', selectSchool: 'Velg en skole for å se elever du har tilgang til.',
    pagination: 'Sidenavigering for elevlisten', previousPage: 'Forrige', nextPage: 'Neste',
    noSchools: 'Kontoen din har ingen aktive skoletilknytninger.', loading: 'Laster …', loadError: 'Kunne ikke laste innholdet', retry: 'Prøv igjen',
    noLearners: 'Ingen elever er tilgjengelige i denne skoleoversikten.', learnerCount: (n: number) => `${n} ${n === 1 ? 'elev' : 'elever'}`,
    grade: 'Trinn', group: 'Gruppe', unassigned: 'Ikke oppgitt', profile: 'Elevprofil', backToLearners: 'Tilbake til elevlisten',
    overview: 'Oversikt', strengths: 'Styrker', interests: 'Interesser', languages: 'Språk', communication: 'Kommunikasjon', support: 'Støtte som virker',
    profileDetailsUnavailable: 'Pedagogiske profilopplysninger utover grunnopplysningene vises ikke her ennå.', lastReviewed: 'Sist vurdert',
    signOut: 'Logg ut', signingOut: 'Logger ut …', language: 'Språk', bokmal: 'Bokmål', nynorsk: 'Nynorsk',
    sessionExpired: 'Økten er utløpt. Logg inn på nytt.', genericError: 'Noe gikk galt. Prøv igjen, eller kontakt systemansvarlig.',
    networkError: 'Fikk ikke kontakt med SpesPed. Kontroller tilkoblingen og prøv igjen.', invalidCredentials: 'E-postadressen eller passordet er feil.',
    loginThrottled: 'For mange innloggingsforsøk. Vent litt før du prøver igjen.', csrfError: 'Økten må oppdateres før du kan fortsette. Last inn siden og prøv på nytt.',
    originError: 'Forespørselen kom fra en adresse som ikke er tillatt.', accessDenied: 'Du har ikke tilgang til dette innholdet.',
    versionConflict: 'Oppføringen er endret. Last inn på nytt før du prøver igjen.', validationError: 'Kontroller opplysningene og prøv igjen.',
    pageSummary: (from: number, to: number, total: number) => `Viser ${from}–${to} av ${total}`,
  },
  nn: {
    appName: 'SpesPed', signIn: 'Logg inn', signInTitle: 'Velkomen tilbake', signInHelp: 'Logg inn med brukarkontoen du har fått frå skulen.', skipToMain: 'Hopp til hovudinnhaldet',
    email: 'E-postadresse', password: 'Passord', signingIn: 'Loggar inn …', loginError: 'Innlogginga mislukkast',
    workspace: 'Arbeidsflate', schools: 'Skular', chooseSchool: 'Vel skule', learners: 'Elevar', selectSchool: 'Vel ein skule for å sjå elevar du har tilgang til.',
    pagination: 'Sidenavigering for elevlista', previousPage: 'Førre', nextPage: 'Neste',
    noSchools: 'Kontoen din har ingen aktive skuletilknytingar.', loading: 'Lastar …', loadError: 'Kunne ikkje laste innhaldet', retry: 'Prøv igjen',
    noLearners: 'Ingen elevar er tilgjengelege i denne skuleoversikta.', learnerCount: (n: number) => `${n} ${n === 1 ? 'elev' : 'elevar'}`,
    grade: 'Trinn', group: 'Gruppe', unassigned: 'Ikkje oppgitt', profile: 'Elevprofil', backToLearners: 'Tilbake til elevlista',
    overview: 'Oversikt', strengths: 'Styrkar', interests: 'Interesser', languages: 'Språk', communication: 'Kommunikasjon', support: 'Støtte som verkar',
    profileDetailsUnavailable: 'Pedagogiske profilopplysningar utover grunnopplysningane blir ikkje viste her enno.', lastReviewed: 'Sist vurdert',
    signOut: 'Logg ut', signingOut: 'Loggar ut …', language: 'Språk', bokmal: 'Bokmål', nynorsk: 'Nynorsk',
    sessionExpired: 'Økta er utløpt. Logg inn på nytt.', genericError: 'Noko gjekk gale. Prøv igjen, eller kontakt systemansvarleg.',
    networkError: 'Fekk ikkje kontakt med SpesPed. Kontroller tilkoplinga og prøv igjen.', invalidCredentials: 'E-postadressa eller passordet er feil.',
    loginThrottled: 'For mange innloggingsforsøk. Vent litt før du prøver igjen.', csrfError: 'Økta må oppdaterast før du kan halde fram. Last inn sida og prøv på nytt.',
    originError: 'Førespurnaden kom frå ei adresse som ikkje er tillaten.', accessDenied: 'Du har ikkje tilgang til dette innhaldet.',
    versionConflict: 'Oppføringa er endra. Last inn på nytt før du prøver igjen.', validationError: 'Kontroller opplysningane og prøv igjen.',
    pageSummary: (from: number, to: number, total: number) => `Viser ${from}–${to} av ${total}`,
  },
} as const;

export type MessageKey = keyof typeof messages.nb;
export function translate(language: Language, key: 'learnerCount'): (n: number) => string;
export function translate(language: Language, key: 'pageSummary'): (from: number, to: number, total: number) => string;
export function translate(language: Language, key: Exclude<MessageKey, 'learnerCount' | 'pageSummary'>): string;
export function translate(language: Language, key: MessageKey): string | ((...args: number[]) => string) {
  return messages[language][key] as string | ((...args: number[]) => string);
}

export function localizeApiError(language: Language, code: string, safeMessage: string): string {
  const translated: Partial<Record<string, Exclude<MessageKey, 'learnerCount' | 'pageSummary'>>> = {
    NETWORK_ERROR: 'networkError',
    invalid_credentials: 'invalidCredentials',
    login_throttled: 'loginThrottled',
    authentication_required: 'sessionExpired',
    csrf_failed: 'csrfError',
    origin_denied: 'originError',
    access_denied: 'accessDenied',
    version_conflict: 'versionConflict',
    conflict: 'versionConflict',
    validation_error: 'validationError',
    request_error: 'genericError',
    internal_error: 'genericError',
  };
  const key = translated[code] ?? (code.startsWith('HTTP_') ? 'genericError' : undefined);
  if (key) return translate(language, key);
  return safeMessage || translate(language, 'genericError');
}

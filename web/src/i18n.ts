export type Language = 'nb' | 'nn';

const messages = {
  nb: {
    appName: 'SpesPed', signIn: 'Logg inn', signInTitle: 'Velkommen tilbake', signInHelp: 'Logg inn med brukerkontoen du har fått fra skolen.',
    email: 'E-postadresse', password: 'Passord', signingIn: 'Logger inn …', loginError: 'Innloggingen mislyktes',
    workspace: 'Arbeidsflate', schools: 'Skoler', chooseSchool: 'Velg skole', learners: 'Elever', selectSchool: 'Velg en skole for å se elever du har tilgang til.',
    noSchools: 'Kontoen din har ingen aktive skoletilknytninger.', loading: 'Laster …', loadError: 'Kunne ikke laste innholdet', retry: 'Prøv igjen',
    noLearners: 'Ingen elever er tilgjengelige i denne skoleoversikten.', learnerCount: (n: number) => `${n} ${n === 1 ? 'elev' : 'elever'}`,
    grade: 'Trinn', group: 'Gruppe', unassigned: 'Ikke oppgitt', profile: 'Elevprofil', backToLearners: 'Tilbake til elevlisten',
    overview: 'Oversikt', strengths: 'Styrker', interests: 'Interesser', languages: 'Språk', communication: 'Kommunikasjon', support: 'Støtte som virker',
    noProfileDetails: 'Det er ikke registrert flere pedagogiske profilopplysninger her.', lastReviewed: 'Sist vurdert',
    signOut: 'Logg ut', signingOut: 'Logger ut …', language: 'Språk', bokmal: 'Bokmål', nynorsk: 'Nynorsk',
    sessionExpired: 'Økten er utløpt. Logg inn på nytt.',
  },
  nn: {
    appName: 'SpesPed', signIn: 'Logg inn', signInTitle: 'Velkomen tilbake', signInHelp: 'Logg inn med brukarkontoen du har fått frå skulen.',
    email: 'E-postadresse', password: 'Passord', signingIn: 'Loggar inn …', loginError: 'Innlogginga mislukkast',
    workspace: 'Arbeidsflate', schools: 'Skular', chooseSchool: 'Vel skule', learners: 'Elevar', selectSchool: 'Vel ein skule for å sjå elevar du har tilgang til.',
    noSchools: 'Kontoen din har ingen aktive skuletilknytingar.', loading: 'Lastar …', loadError: 'Kunne ikkje laste innhaldet', retry: 'Prøv igjen',
    noLearners: 'Ingen elevar er tilgjengelege i denne skuleoversikta.', learnerCount: (n: number) => `${n} ${n === 1 ? 'elev' : 'elevar'}`,
    grade: 'Trinn', group: 'Gruppe', unassigned: 'Ikkje oppgitt', profile: 'Elevprofil', backToLearners: 'Tilbake til elevlista',
    overview: 'Oversikt', strengths: 'Styrkar', interests: 'Interesser', languages: 'Språk', communication: 'Kommunikasjon', support: 'Støtte som verkar',
    noProfileDetails: 'Det er ikkje registrert fleire pedagogiske profilopplysningar her.', lastReviewed: 'Sist vurdert',
    signOut: 'Logg ut', signingOut: 'Loggar ut …', language: 'Språk', bokmal: 'Bokmål', nynorsk: 'Nynorsk',
    sessionExpired: 'Økta er utløpt. Logg inn på nytt.',
  },
} as const;

export type MessageKey = keyof typeof messages.nb;
export function translate(language: Language, key: 'learnerCount'): (n: number) => string;
export function translate(language: Language, key: Exclude<MessageKey, 'learnerCount'>): string;
export function translate(language: Language, key: MessageKey): string | ((n: number) => string) {
  return messages[language][key];
}

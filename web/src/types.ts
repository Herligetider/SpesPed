export type School = {
  id: string;
  name: string;
  kind: string;
  timezone: string;
  role: string;
};

export type User = {
  id: string;
  email: string;
  display_name: string;
};

export type Session = {
  user: User;
  csrf_token: string;
  schools: School[];
};

export type Learner = {
  id: string;
  display_name: string;
  grade: number;
  group_name: string | null;
  version: number;
};

export type LearnerProfile = Learner & {
  strengths?: string | null;
  interests?: string | null;
  languages?: string[];
  communication?: string | null;
  support_strategies?: string | null;
  updated_at?: string | null;
};

export type ListResponse<T> = { items: T[]; total: number };

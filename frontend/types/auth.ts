export type UserRole =
  | "platform_admin"
  | "college_admin"
  | "admissions_staff"
  | "counselor"
  | "student"
  | "parent";

export type AuthUser = {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  college_id: string | null;
  is_active: boolean;
};

export type LoginRequest = {
  email: string;
  password: string;
};

export type AuthTokens = {
  access_token: string;
  refresh_token: string;
  expires_in: number;
};

export type AuthResponse = AuthTokens & {
  user: AuthUser;
};

export type StoredSession = AuthTokens & {
  user: AuthUser;
  issued_at: number;
};

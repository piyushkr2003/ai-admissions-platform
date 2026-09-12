export type ConfigurationStatus = {
  identity: string;
  branding: string;
  languages: string;
  admissions: string;
  knowledge: string;
  agent: string;
};

export type College = {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  logo_url: string | null;
  website_url: string | null;
  email: string | null;
  phone: string | null;
  city: string | null;
  state: string | null;
  country: string | null;
  timezone: string;
  default_language: string;
  supported_languages: string[];
  feature_flags: Record<string, boolean | string | number | null>;
  status: string;
  configuration_status: ConfigurationStatus;
};

export type CollegeIdentityUpdate = Partial<{
  name: string;
  description: string | null;
  website_url: string | null;
  email: string | null;
  phone: string | null;
  address: string | null;
  city: string | null;
  state: string | null;
  country: string | null;
  postal_code: string | null;
}>;

export type CollegeConfigurationUpdate = Partial<{
  timezone: string;
  default_language: string;
  supported_languages: string[];
  feature_flags: Record<string, boolean | string | number | null>;
  logo_url: string | null;
}>;

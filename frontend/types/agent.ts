export type AgentConfig = {
  id: string;
  agent_name: string;
  personality: string | null;
  default_language: string;
  supported_languages: string[];
  greeting_message: string | null;
  fallback_message: string | null;
  escalation_message: string | null;
  lead_scoring_config: Record<string, unknown> | null;
  active: boolean;
};

export type AgentConfigUpdate = Partial<{
  agent_name: string;
  personality: string | null;
  default_language: string;
  supported_languages: string[];
  greeting_message: string | null;
  fallback_message: string | null;
  escalation_message: string | null;
  active: boolean;
}>;

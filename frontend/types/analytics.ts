/**
 * Mirrors backend/app/analytics/service.py and router.py exactly
 * (docs/api-contract.md section 64). Every field here is something the
 * backend actually returns - nothing is invented on the frontend.
 */

export type AnalyticsDateRangePreset = "today" | "last_7_days" | "last_30_days" | "last_90_days" | "custom";

export type AnalyticsDateRangeParams = {
  range: AnalyticsDateRangePreset;
  start_date?: string;
  end_date?: string;
};

export type AnalyticsRange = {
  range: string;
  timezone: string;
  start_date: string;
  end_date: string;
  start_utc: string;
  end_utc: string;
};

/** Metric provenance labels the backend attaches to every derived/uncertain figure. */
export type MeasurementProvenance = "directly_measured" | "derived" | "unavailable";

export type MeasuredValue = {
  measurement: MeasurementProvenance;
  value: number | null;
  sample_size: number;
  note?: string;
};

export type ConversionMetric = {
  measurement: MeasurementProvenance;
  definition: string;
  leads_student_count: number;
  converted_student_count: number;
  rate: number | null;
};

/** A fixed-vocabulary breakdown (status/temperature/channel/language/category), keyed by value. */
export type CountBreakdown = Record<string, number>;

export type NamedCount = { count: number; [key: string]: string | number };

export type ConversationsSection = {
  total_conversations: number;
  by_status: CountBreakdown;
  by_channel: CountBreakdown;
  by_language: CountBreakdown;
  average_duration_seconds: MeasuredValue;
};

export type LeadsSection = {
  total_leads: number;
  new_leads: number;
  by_status: CountBreakdown;
  by_temperature: CountBreakdown;
  by_course: { course: string; count: number }[];
  appointment_conversion: ConversionMetric;
  application_conversion: ConversionMetric;
};

export type AppointmentsSection = {
  total_appointments: number;
  by_status: CountBreakdown;
  by_counselor: { counselor: string; count: number }[];
};

export type CompletionDistribution = {
  "0": number;
  "1-25": number;
  "26-50": number;
  "51-75": number;
  "76-100": number;
};

export type ApplicationsSection = {
  total_applications: number;
  by_status: CountBreakdown;
  by_course: { course: string; count: number }[];
  completion_percentage_distribution: CompletionDistribution;
};

export type SupportSection = {
  total_tickets: number;
  by_status: CountBreakdown;
  by_category: CountBreakdown;
  escalated_tickets: number;
  average_resolution_seconds: MeasuredValue;
};

export type VoiceSection = {
  total_sessions: number;
  by_status: CountBreakdown;
  by_channel: CountBreakdown;
  by_language: CountBreakdown;
  failed_sessions: number;
  average_duration_seconds: MeasuredValue;
};

export type EscalationsMetric = {
  measurement: MeasurementProvenance;
  definition: string;
  escalated_conversations: number;
  total_conversations: number;
  escalation_rate: number | null;
};

export type ToolUsageMetric = {
  measurement: MeasurementProvenance;
  definition: string;
  ai_turns_with_tool_calls: number;
  total_tool_invocations: number;
};

export type UnansweredQuestionsMetric = {
  measurement: MeasurementProvenance;
  definition: string;
  count: number;
};

export type QueryCategoriesMetric = {
  measurement: MeasurementProvenance;
  definition: string;
  breakdown: { intent: string; count: number }[];
};

/** Always `"unavailable"` today - the backend never fabricates this. */
export type UnavailableMetric = {
  measurement: "unavailable";
  reason: string;
};

export type AiOperationsSection = {
  escalations: EscalationsMetric;
  tool_usage: ToolUsageMetric;
  unanswered_questions: UnansweredQuestionsMetric;
  query_categories: QueryCategoriesMetric;
  ai_resolution_rate: UnavailableMetric;
};

export type AnalyticsOverview = {
  range: AnalyticsRange;
  conversations: ConversationsSection;
  leads: LeadsSection;
  appointments: AppointmentsSection;
  applications: ApplicationsSection;
  support: SupportSection;
  voice: VoiceSection;
  ai_operations: AiOperationsSection;
};

export type TrendPoint = { date: string; count: number };

export type AnalyticsTrends = {
  range: AnalyticsRange;
  conversations_per_day: TrendPoint[];
  leads_per_day: TrendPoint[];
  appointments_per_day: TrendPoint[];
  applications_per_day: TrendPoint[];
  support_tickets_per_day: TrendPoint[];
  voice_sessions_per_day: TrendPoint[];
};

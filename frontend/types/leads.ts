export type LeadTemperature = "hot" | "warm" | "cold";

export type LeadStatus =
  | "new"
  | "contacted"
  | "qualifying"
  | "qualified"
  | "appointment_booked"
  | "application_started"
  | "converted"
  | "lost"
  | "disqualified";

export type LeadStudent = {
  id: string;
  name: string | null;
  phone: string | null;
  email: string | null;
  qualification: string | null;
  qualification_score: number | null;
  entrance_exam: string | null;
  entrance_exam_score: number | null;
  budget: string | null;
  location: string | null;
  parent_name: string | null;
  parent_phone: string | null;
};

export type Lead = {
  id: string;
  college_id: string;
  student_id: string;
  course_id: string | null;
  course_name: string | null;
  status: LeadStatus | string;
  intent: string | null;
  lead_score: number;
  lead_temperature: LeadTemperature | string;
  source: string;
  notes: string | null;
  next_action: string | null;
  hostel_interest: boolean | null;
  scholarship_interest: boolean | null;
  parent_involvement: boolean | null;
  last_contacted_at: string | null;
  last_activity_at: string;
  created_at: string;
  updated_at: string;
  student: LeadStudent | null;
};

export type LeadListParams = {
  status?: string;
  temperature?: string;
  intent?: string;
  source?: string;
  sort?: "newest" | "recently_active" | "recently_updated" | "highest_score" | "lowest_score";
  page?: number;
  page_size?: number;
};

export type LeadScoreEvent = {
  id: string;
  lead_id: string;
  event_type: string;
  points: number;
  reason: string | null;
  source: string | null;
  created_at: string;
};

export type LeadScoreEvents = {
  lead_id: string;
  score: number;
  temperature: string;
  events: LeadScoreEvent[];
};

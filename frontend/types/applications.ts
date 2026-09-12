export type ApplicationStatus =
  | "draft"
  | "in_progress"
  | "submitted"
  | "under_review"
  | "documents_pending"
  | "approved"
  | "rejected"
  | "withdrawn";

export type Application = {
  id: string;
  college_id: string;
  student_id: string;
  student_name: string | null;
  course_id: string;
  course_name: string | null;
  application_number: string | null;
  intake: string | null;
  status: ApplicationStatus | string;
  completion_percentage: number;
  notes: string | null;
  submitted_at: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
};

export type ApplicationListParams = {
  status?: string;
  course_id?: string;
  student_id?: string;
  page?: number;
  page_size?: number;
};

export type ApplicationStatusReport = {
  application_id: string;
  status: string;
  completion_percentage: number;
  missing_information: string[];
  next_steps: string[];
  application_number: string | null;
  submitted_at: string | null;
};

export type ApplicationDocumentStatus = "missing" | "pending" | "verified" | "rejected" | string;

export type ApplicationChecklistItem = {
  document_type: string;
  mandatory?: boolean;
  status: ApplicationDocumentStatus;
  document_id: string | null;
};

export type ApplicationDocument = {
  id: string;
  application_id: string;
  document_type: string;
  file_name: string | null;
  file_url: string | null;
  status: ApplicationDocumentStatus;
  verified_at: string | null;
  created_at: string;
};

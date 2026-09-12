export type AppointmentStatus = "requested" | "confirmed" | "cancelled" | "completed" | "no_show";

export type Appointment = {
  id: string;
  college_id: string;
  student_id: string;
  student_name: string | null;
  counselor_id: string;
  counselor_name: string | null;
  course_id: string | null;
  course_name: string | null;
  start_time: string;
  end_time: string;
  status: AppointmentStatus | string;
  meeting_type: string | null;
  meeting_link: string | null;
  notes: string | null;
  cancellation_reason: string | null;
  source: string;
  created_at: string;
  updated_at: string;
};

export type AppointmentListParams = {
  status?: string;
  counselor_id?: string;
  student_id?: string;
  from?: string;
  to?: string;
  page?: number;
  page_size?: number;
};

export type Counselor = {
  id: string;
  college_id: string;
  user_id: string | null;
  name: string;
  email: string | null;
  phone: string | null;
  specialization: string | null;
  active: boolean;
  created_at: string;
  updated_at: string;
};

export type AvailabilitySlot = {
  start_time: string;
  duration_minutes: number;
};

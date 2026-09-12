import type { ApiClient } from "@/lib/api/client";
import { toQueryString } from "@/lib/api/query";
import type { Appointment, AppointmentListParams, AvailabilitySlot, Counselor } from "@/types/appointments";

export const appointmentsApi = {
  list(client: ApiClient, collegeId: string | null, params: AppointmentListParams = {}) {
    return client.get<Appointment[]>(`/appointments${toQueryString({ college_id: collegeId, ...params })}`);
  },
  get(client: ApiClient, collegeId: string | null, appointmentId: string) {
    return client.get<Appointment>(`/appointments/${appointmentId}${toQueryString({ college_id: collegeId })}`);
  },
  update(client: ApiClient, collegeId: string | null, appointmentId: string, payload: Record<string, unknown>) {
    return client.patch<Appointment>(`/appointments/${appointmentId}${toQueryString({ college_id: collegeId })}`, payload);
  },
  reschedule(client: ApiClient, collegeId: string | null, appointmentId: string, newStartTime: string) {
    return client.patch<Appointment>(
      `/appointments/${appointmentId}/reschedule${toQueryString({ college_id: collegeId })}`,
      { new_start_time: newStartTime },
    );
  },
  cancel(client: ApiClient, collegeId: string | null, appointmentId: string, reason?: string) {
    return client.post<Appointment>(
      `/appointments/${appointmentId}/cancel${toQueryString({ college_id: collegeId })}`,
      { reason: reason ?? null },
    );
  },
  complete(client: ApiClient, collegeId: string | null, appointmentId: string) {
    return client.post<Appointment>(`/appointments/${appointmentId}/complete${toQueryString({ college_id: collegeId })}`);
  },
  markNoShow(client: ApiClient, collegeId: string | null, appointmentId: string) {
    return client.post<Appointment>(`/appointments/${appointmentId}/no-show${toQueryString({ college_id: collegeId })}`);
  },
};

export const counselorsApi = {
  list(client: ApiClient, collegeId: string | null, activeOnly = true) {
    return client.get<Counselor[]>(`/counselors${toQueryString({ college_id: collegeId, active_only: activeOnly })}`);
  },
  availability(client: ApiClient, collegeId: string | null, counselorId: string, date?: string) {
    return client.get<{ counselor_id: string; slots: AvailabilitySlot[] }>(
      `/counselors/${counselorId}/availability${toQueryString({ college_id: collegeId, date })}`,
    );
  },
};

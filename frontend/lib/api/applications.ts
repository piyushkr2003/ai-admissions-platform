import type { ApiClient } from "@/lib/api/client";
import { toQueryString } from "@/lib/api/query";
import type {
  Application,
  ApplicationChecklistItem,
  ApplicationDocument,
  ApplicationListParams,
  ApplicationStatusReport,
} from "@/types/applications";

export const applicationsApi = {
  list(client: ApiClient, collegeId: string | null, params: ApplicationListParams = {}) {
    return client.get<Application[]>(`/applications${toQueryString({ college_id: collegeId, ...params })}`);
  },
  get(client: ApiClient, collegeId: string | null, applicationId: string) {
    return client.get<Application>(`/applications/${applicationId}${toQueryString({ college_id: collegeId })}`);
  },
  status(client: ApiClient, collegeId: string | null, applicationId: string) {
    return client.get<ApplicationStatusReport>(
      `/applications/${applicationId}/status${toQueryString({ college_id: collegeId })}`,
    );
  },
  update(client: ApiClient, collegeId: string | null, applicationId: string, payload: Record<string, unknown>) {
    return client.patch<Application>(`/applications/${applicationId}${toQueryString({ college_id: collegeId })}`, payload);
  },
  submit(client: ApiClient, collegeId: string | null, applicationId: string) {
    return client.post<Application>(`/applications/${applicationId}/submit${toQueryString({ college_id: collegeId })}`, {});
  },
  withdraw(client: ApiClient, collegeId: string | null, applicationId: string, reason?: string) {
    return client.post<Application>(`/applications/${applicationId}/withdraw${toQueryString({ college_id: collegeId })}`, {
      reason: reason ?? null,
    });
  },
  documents(client: ApiClient, collegeId: string | null, applicationId: string) {
    return client.get<ApplicationChecklistItem[]>(
      `/applications/${applicationId}/documents${toQueryString({ college_id: collegeId })}`,
    );
  },
  addDocument(
    client: ApiClient,
    collegeId: string | null,
    applicationId: string,
    payload: { document_type: string; file_name?: string; file_url?: string },
  ) {
    return client.post<ApplicationDocument>(
      `/applications/${applicationId}/documents${toQueryString({ college_id: collegeId })}`,
      payload,
    );
  },
  updateDocumentStatus(
    client: ApiClient,
    collegeId: string | null,
    applicationId: string,
    documentId: string,
    status: string,
  ) {
    return client.patch<ApplicationDocument>(
      `/applications/${applicationId}/documents/${documentId}${toQueryString({ college_id: collegeId })}`,
      { status },
    );
  },
  removeDocument(client: ApiClient, collegeId: string | null, applicationId: string, documentId: string) {
    return client.delete<{ success: boolean }>(
      `/applications/${applicationId}/documents/${documentId}${toQueryString({ college_id: collegeId })}`,
    );
  },
};

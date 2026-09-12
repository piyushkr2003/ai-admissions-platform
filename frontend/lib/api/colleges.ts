import type { ApiClient } from "@/lib/api/client";
import type { College, CollegeConfigurationUpdate, CollegeIdentityUpdate } from "@/types/college";

export const collegesApi = {
  list(client: ApiClient) {
    return client.get<College[]>("/colleges");
  },
  get(client: ApiClient, collegeId: string) {
    return client.get<College>(`/colleges/${collegeId}`);
  },
  getConfiguration(client: ApiClient, collegeId: string) {
    return client.get<College>(`/colleges/${collegeId}/configuration`);
  },
  updateIdentity(client: ApiClient, collegeId: string, payload: CollegeIdentityUpdate) {
    return client.patch<College>(`/colleges/${collegeId}`, payload);
  },
  updateConfiguration(client: ApiClient, collegeId: string, payload: CollegeConfigurationUpdate) {
    return client.patch<College>(`/colleges/${collegeId}/configuration`, payload);
  },
};

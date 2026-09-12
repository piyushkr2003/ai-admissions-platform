import type { ApiClient } from "@/lib/api/client";
import { toQueryString } from "@/lib/api/query";
import type { KnowledgeSearchResponse, KnowledgeSource, KnowledgeSourceCreate } from "@/types/knowledge";

export const knowledgeApi = {
  listSources(client: ApiClient, collegeId: string | null) {
    return client.get<KnowledgeSource[]>(`/knowledge/sources${toQueryString({ college_id: collegeId })}`);
  },
  getSource(client: ApiClient, collegeId: string | null, sourceId: string) {
    return client.get<KnowledgeSource>(`/knowledge/sources/${sourceId}${toQueryString({ college_id: collegeId })}`);
  },
  createSource(client: ApiClient, collegeId: string | null, payload: KnowledgeSourceCreate) {
    return client.post<KnowledgeSource>(`/knowledge/sources${toQueryString({ college_id: collegeId })}`, payload);
  },
  reprocess(client: ApiClient, collegeId: string | null, sourceId: string) {
    return client.post<KnowledgeSource>(`/knowledge/sources/${sourceId}/reprocess${toQueryString({ college_id: collegeId })}`);
  },
  archive(client: ApiClient, collegeId: string | null, sourceId: string) {
    return client.delete<KnowledgeSource>(`/knowledge/sources/${sourceId}${toQueryString({ college_id: collegeId })}`);
  },
  search(client: ApiClient, collegeId: string | null, query: string, topK?: number) {
    return client.post<KnowledgeSearchResponse>(`/knowledge/search${toQueryString({ college_id: collegeId })}`, {
      query,
      top_k: topK,
    });
  },
};

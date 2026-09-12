import type { ApiClient } from "@/lib/api/client";
import { toQueryString } from "@/lib/api/query";
import type { AgentConfig, AgentConfigUpdate } from "@/types/agent";

export const agentApi = {
  getConfig(client: ApiClient, collegeId: string | null) {
    return client.get<AgentConfig>(`/agent/config${toQueryString({ college_id: collegeId })}`);
  },
  updateConfig(client: ApiClient, collegeId: string | null, payload: AgentConfigUpdate) {
    return client.patch<AgentConfig>(`/agent/config${toQueryString({ college_id: collegeId })}`, payload);
  },
};

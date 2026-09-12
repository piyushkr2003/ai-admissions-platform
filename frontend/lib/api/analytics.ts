import type { ApiClient } from "@/lib/api/client";
import { toQueryString } from "@/lib/api/query";
import type { AnalyticsDateRangeParams, AnalyticsOverview, AnalyticsTrends } from "@/types/analytics";

/**
 * Task 014: consumes the real backend analytics endpoints
 * (backend/app/analytics/router.py, docs/api-contract.md section 64)
 * directly - no more composing totals from the leads/appointments/
 * applications/support/voice list endpoints. `college_id` is only ever
 * honored by the backend for a platform_admin; a college-scoped
 * caller's value is ignored server-side (resolve_tenant_college_id),
 * so passing the tenant-provider's current collegeId here is always
 * safe and never itself an authorization decision.
 */
export const analyticsApi = {
  overview(client: ApiClient, collegeId: string | null, params: AnalyticsDateRangeParams) {
    return client.get<AnalyticsOverview>(
      `/analytics/overview${toQueryString({
        college_id: collegeId,
        range: params.range,
        start_date: params.start_date,
        end_date: params.end_date,
      })}`,
    );
  },
  trends(client: ApiClient, collegeId: string | null, params: AnalyticsDateRangeParams) {
    return client.get<AnalyticsTrends>(
      `/analytics/trends${toQueryString({
        college_id: collegeId,
        range: params.range,
        start_date: params.start_date,
        end_date: params.end_date,
      })}`,
    );
  },
};

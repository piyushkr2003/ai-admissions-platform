import { describe, expect, it, vi } from "vitest";
import { ApiClient } from "@/lib/api/client";
import { dashboardApi } from "@/lib/api/dashboard";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function collection(total: number) {
  return jsonResponse({ data: [], meta: { request_id: "req_1", page: 1, page_size: 5, total, total_pages: 1 } });
}

describe("dashboardApi.overview", () => {
  it("composes metrics from the real list endpoints and degrades a single failing section", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/support-tickets")) {
        return jsonResponse(
          { error: { code: "FORBIDDEN", message: "Your role is not permitted to perform this action." } },
          403,
        );
      }
      return collection(3);
    });
    const client = new ApiClient({ baseUrl: "http://api.test/api/v1", fetchImpl });

    const { data } = await dashboardApi.overview(client, "college-1");

    expect(data.section_status.support_tickets).toBe("unavailable");
    expect(data.metrics.support_tickets).toBeUndefined();
    expect(data.section_status.leads).toBe("ok");
    expect(data.metrics.new_leads).toBe(3);
    expect(data.metrics.hot_leads).toBe(3);
    expect(data.recent_support_tickets).toEqual([]);
  });

  it("appends the tenant college_id to every underlying request", async () => {
    const fetchImpl = vi.fn(async (..._args: unknown[]) => collection(0));
    const client = new ApiClient({ baseUrl: "http://api.test/api/v1", fetchImpl });

    await dashboardApi.overview(client, "college-42");

    const urls = fetchImpl.mock.calls.map((call) => String(call[0]));
    expect(urls.every((url) => url.includes("college_id=college-42"))).toBe(true);
  });
});

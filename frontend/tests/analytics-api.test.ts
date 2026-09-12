import { describe, expect, it, vi } from "vitest";
import { ApiClient, ApiError } from "@/lib/api/client";
import { analyticsApi } from "@/lib/api/analytics";
import type { AnalyticsOverview, AnalyticsTrends } from "@/types/analytics";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

const OVERVIEW_STUB: AnalyticsOverview = {
  range: { range: "last_30_days", timezone: "Asia/Kolkata", start_date: "2026-08-14", end_date: "2026-09-12", start_utc: "2026-08-13T18:30:00Z", end_utc: "2026-09-12T18:30:00Z" },
  conversations: { total_conversations: 0, by_status: {}, by_channel: {}, by_language: {}, average_duration_seconds: { measurement: "unavailable", value: null, sample_size: 0, note: "none" } },
  leads: { total_leads: 0, new_leads: 0, by_status: {}, by_temperature: {}, by_course: [], appointment_conversion: { measurement: "derived", definition: "d", leads_student_count: 0, converted_student_count: 0, rate: null }, application_conversion: { measurement: "derived", definition: "d", leads_student_count: 0, converted_student_count: 0, rate: null } },
  appointments: { total_appointments: 0, by_status: {}, by_counselor: [] },
  applications: { total_applications: 0, by_status: {}, by_course: [], completion_percentage_distribution: { "0": 0, "1-25": 0, "26-50": 0, "51-75": 0, "76-100": 0 } },
  support: { total_tickets: 0, by_status: {}, by_category: {}, escalated_tickets: 0, average_resolution_seconds: { measurement: "unavailable", value: null, sample_size: 0 } },
  voice: { total_sessions: 0, by_status: {}, by_channel: {}, by_language: {}, failed_sessions: 0, average_duration_seconds: { measurement: "unavailable", value: null, sample_size: 0 } },
  ai_operations: {
    escalations: { measurement: "directly_measured", definition: "d", escalated_conversations: 0, total_conversations: 0, escalation_rate: null },
    tool_usage: { measurement: "directly_measured", definition: "d", ai_turns_with_tool_calls: 0, total_tool_invocations: 0 },
    unanswered_questions: { measurement: "directly_measured", definition: "d", count: 0 },
    query_categories: { measurement: "directly_measured", definition: "d", breakdown: [] },
    ai_resolution_rate: { measurement: "unavailable", reason: "no trustworthy signal" },
  },
};

const TRENDS_STUB: AnalyticsTrends = {
  range: OVERVIEW_STUB.range,
  conversations_per_day: [],
  leads_per_day: [],
  appointments_per_day: [],
  applications_per_day: [],
  support_tickets_per_day: [],
  voice_sessions_per_day: [],
};

describe("analyticsApi.overview", () => {
  it("calls GET /analytics/overview with college_id and range query params", async () => {
    const fetchImpl = vi.fn(async (_input: RequestInfo | URL) => jsonResponse({ data: OVERVIEW_STUB, meta: { request_id: "req_1" } }));
    const client = new ApiClient({ baseUrl: "http://api.test/api/v1", fetchImpl });

    await analyticsApi.overview(client, "college-1", { range: "last_30_days" });

    expect(fetchImpl).toHaveBeenCalledTimes(1);
    const url = String(fetchImpl.mock.calls[0][0]);
    expect(url).toBe("http://api.test/api/v1/analytics/overview?college_id=college-1&range=last_30_days");
  });

  it("sends start_date/end_date for a custom range and omits them otherwise", async () => {
    const fetchImpl = vi.fn(async (_input: RequestInfo | URL) => jsonResponse({ data: OVERVIEW_STUB, meta: { request_id: "req_1" } }));
    const client = new ApiClient({ baseUrl: "http://api.test/api/v1", fetchImpl });

    await analyticsApi.overview(client, "college-1", { range: "custom", start_date: "2026-01-01", end_date: "2026-01-31" });
    const customUrl = String(fetchImpl.mock.calls[0][0]);
    expect(customUrl).toContain("range=custom");
    expect(customUrl).toContain("start_date=2026-01-01");
    expect(customUrl).toContain("end_date=2026-01-31");

    await analyticsApi.overview(client, "college-1", { range: "today" });
    const todayUrl = String(fetchImpl.mock.calls[1][0]);
    expect(todayUrl).not.toContain("start_date");
    expect(todayUrl).not.toContain("end_date");
  });

  it("returns the real backend response shape unchanged (no client-side reshaping)", async () => {
    const fetchImpl = vi.fn(async (_input: RequestInfo | URL) => jsonResponse({ data: OVERVIEW_STUB, meta: { request_id: "req_1" } }));
    const client = new ApiClient({ baseUrl: "http://api.test/api/v1", fetchImpl });

    const { data } = await analyticsApi.overview(client, "college-1", { range: "today" });
    expect(data).toEqual(OVERVIEW_STUB);
  });

  it("propagates a 403 as an ApiError with status 403", async () => {
    const fetchImpl = vi.fn(async (_input: RequestInfo | URL) =>
      jsonResponse({ error: { code: "FORBIDDEN", message: "Role not permitted.", request_id: "req_1" } }, 403),
    );
    const client = new ApiClient({ baseUrl: "http://api.test/api/v1", fetchImpl });

    await expect(analyticsApi.overview(client, "college-1", { range: "today" })).rejects.toMatchObject({
      status: 403,
      code: "FORBIDDEN",
    });
  });

  it("propagates a 401 as an ApiError and triggers onUnauthorized", async () => {
    const fetchImpl = vi.fn(async (_input: RequestInfo | URL) =>
      jsonResponse({ error: { code: "UNAUTHORIZED", message: "Invalid token.", request_id: "req_1" } }, 401),
    );
    const onUnauthorized = vi.fn();
    const client = new ApiClient({ baseUrl: "http://api.test/api/v1", fetchImpl, onUnauthorized });

    await expect(analyticsApi.overview(client, "college-1", { range: "today" })).rejects.toBeInstanceOf(ApiError);
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
  });

  it("never calls a legacy list endpoint (leads/appointments/applications/support-tickets/voice)", async () => {
    const fetchImpl = vi.fn(async (_input: RequestInfo | URL) => jsonResponse({ data: OVERVIEW_STUB, meta: { request_id: "req_1" } }));
    const client = new ApiClient({ baseUrl: "http://api.test/api/v1", fetchImpl });

    await analyticsApi.overview(client, "college-1", { range: "last_7_days" });
    await analyticsApi.trends(client, "college-1", { range: "last_7_days" });

    const urls = fetchImpl.mock.calls.map((call) => String(call[0]));
    for (const url of urls) {
      expect(url).toMatch(/\/analytics\/(overview|trends)\b/);
      expect(url).not.toMatch(/\/(leads|appointments|applications|support-tickets|voice\/sessions)\b/);
    }
  });
});

describe("analyticsApi.trends", () => {
  it("calls GET /analytics/trends with the resolved range params", async () => {
    const fetchImpl = vi.fn(async (_input: RequestInfo | URL) => jsonResponse({ data: TRENDS_STUB, meta: { request_id: "req_1" } }));
    const client = new ApiClient({ baseUrl: "http://api.test/api/v1", fetchImpl });

    await analyticsApi.trends(client, "college-1", { range: "last_90_days" });

    const url = String(fetchImpl.mock.calls[0][0]);
    expect(url).toBe("http://api.test/api/v1/analytics/trends?college_id=college-1&range=last_90_days");
  });

  it("returns the trends response shape unchanged", async () => {
    const fetchImpl = vi.fn(async (_input: RequestInfo | URL) => jsonResponse({ data: TRENDS_STUB, meta: { request_id: "req_1" } }));
    const client = new ApiClient({ baseUrl: "http://api.test/api/v1", fetchImpl });

    const { data } = await analyticsApi.trends(client, "college-1", { range: "last_90_days" });
    expect(data).toEqual(TRENDS_STUB);
  });
});

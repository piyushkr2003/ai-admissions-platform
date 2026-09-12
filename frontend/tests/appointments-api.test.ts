import { describe, expect, it, vi } from "vitest";
import { appointmentsApi } from "@/lib/api/appointments";
import { ApiClient } from "@/lib/api/client";

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
}

describe("appointmentsApi", () => {
  it("requires college_id on every call so a platform_admin can select a tenant", async () => {
    const fetchImpl = vi.fn().mockImplementation(async () => jsonResponse({ data: {}, meta: { request_id: "req_1" } }));
    const client = new ApiClient({ baseUrl: "http://api.test/api/v1", fetchImpl });

    await appointmentsApi.reschedule(client, "college-9", "appt-1", "2026-09-20T10:00:00.000Z");
    await appointmentsApi.cancel(client, "college-9", "appt-1", "no longer needed");
    await appointmentsApi.complete(client, "college-9", "appt-1");

    const calls = fetchImpl.mock.calls.map((call) => {
      const [url, init] = call as [string, RequestInit];
      return { url: String(url), method: init.method };
    });

    expect(calls).toEqual([
      { url: "http://api.test/api/v1/appointments/appt-1/reschedule?college_id=college-9", method: "PATCH" },
      { url: "http://api.test/api/v1/appointments/appt-1/cancel?college_id=college-9", method: "POST" },
      { url: "http://api.test/api/v1/appointments/appt-1/complete?college_id=college-9", method: "POST" },
    ]);
  });

  it("omits college_id entirely for a college-scoped caller with no selected tenant", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({ data: [], meta: { request_id: "req_1" } }));
    const client = new ApiClient({ baseUrl: "http://api.test/api/v1", fetchImpl });

    await appointmentsApi.list(client, null, { status: "confirmed" });

    const url = fetchImpl.mock.calls[0]?.[0];
    expect(String(url)).toBe("http://api.test/api/v1/appointments?status=confirmed");
  });
});

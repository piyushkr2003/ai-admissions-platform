import { describe, expect, it, vi } from "vitest";
import { ApiClient } from "@/lib/api/client";
import { voiceApi } from "@/lib/api/voice";

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
}

describe("voiceApi (Task 015)", () => {
  it("createSession posts college_id and channel without any auth-derived tenant param", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({ data: {}, meta: { request_id: "req_1" } }));
    const client = new ApiClient({ baseUrl: "http://api.test/api/v1", fetchImpl });

    await voiceApi.createSession(client, "college-9", "en");

    const [url, init] = fetchImpl.mock.calls[0] as [string, RequestInit];
    expect(String(url)).toBe("http://api.test/api/v1/voice/sessions");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ college_id: "college-9", channel: "web_voice", language: "en" });
  });

  it("createSession omits language when not provided", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({ data: {}, meta: { request_id: "req_1" } }));
    const client = new ApiClient({ baseUrl: "http://api.test/api/v1", fetchImpl });

    await voiceApi.createSession(client, "college-9");

    const [, init] = fetchImpl.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(init.body as string)).toEqual({ college_id: "college-9", channel: "web_voice" });
  });

  it("postEvent hits the session-scoped event endpoint with the event payload", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({ data: {}, meta: { request_id: "req_1" } }));
    const client = new ApiClient({ baseUrl: "http://api.test/api/v1", fetchImpl });

    await voiceApi.postEvent(client, "sess-1", { event_type: "final_transcript", text: "hello" });

    const [url, init] = fetchImpl.mock.calls[0] as [string, RequestInit];
    expect(String(url)).toBe("http://api.test/api/v1/voice/sessions/sess-1/events");
    expect(JSON.parse(init.body as string)).toEqual({ event_type: "final_transcript", text: "hello" });
  });

  it("endSession posts an optional reason to the end endpoint", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({ data: {}, meta: { request_id: "req_1" } }));
    const client = new ApiClient({ baseUrl: "http://api.test/api/v1", fetchImpl });

    await voiceApi.endSession(client, "sess-1", "completed");

    const [url, init] = fetchImpl.mock.calls[0] as [string, RequestInit];
    expect(String(url)).toBe("http://api.test/api/v1/voice/sessions/sess-1/end");
    expect(JSON.parse(init.body as string)).toEqual({ reason: "completed" });
  });
});

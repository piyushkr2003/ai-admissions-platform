import { describe, expect, it, vi } from "vitest";
import { ApiClient, ApiError } from "@/lib/api/client";

describe("ApiClient", () => {
  it("adds auth and request correlation headers", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ data: { ok: true }, meta: { request_id: "req_backend" } }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const client = new ApiClient({
      baseUrl: "http://api.test/api/v1",
      fetchImpl,
      getAccessToken: () => "access-token",
    });

    const result = await client.post<{ ok: boolean }>("/leads", { name: "Asha" }, { requestId: "req_frontend" });
    const [url, init] = fetchImpl.mock.calls[0] as [string, RequestInit];
    const headers = init.headers as Headers;

    expect(url).toBe("http://api.test/api/v1/leads");
    expect(headers.get("Authorization")).toBe("Bearer access-token");
    expect(headers.get("X-Request-ID")).toBe("req_frontend");
    expect(headers.get("Content-Type")).toBe("application/json");
    expect(init.body).toBe(JSON.stringify({ name: "Asha" }));
    expect(result.data.ok).toBe(true);
  });

  it("converts API error envelopes into ApiError", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          error: {
            code: "TENANT_ACCESS_DENIED",
            message: "This resource does not belong to your college",
            details: {},
            request_id: "req_denied",
          },
        }),
        { status: 403, headers: { "Content-Type": "application/json" } },
      ),
    );
    const client = new ApiClient({ baseUrl: "http://api.test/api/v1", fetchImpl });

    await expect(client.get("/colleges/other", { requestId: "req_frontend" })).rejects.toMatchObject({
      status: 403,
      code: "TENANT_ACCESS_DENIED",
      requestId: "req_denied",
    });
  });

  it("uses a safe network error when fetch fails", async () => {
    const client = new ApiClient({
      baseUrl: "http://api.test/api/v1",
      fetchImpl: vi.fn().mockRejectedValue(new Error("socket closed")),
    });

    await expect(client.get("/auth/me", { requestId: "req_frontend" })).rejects.toBeInstanceOf(ApiError);
    await expect(client.get("/auth/me", { requestId: "req_frontend" })).rejects.toMatchObject({
      status: 0,
      code: "NETWORK_ERROR",
    });
  });
});

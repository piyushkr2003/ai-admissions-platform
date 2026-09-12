import { getApiBaseUrl } from "@/lib/api/config";
import type { ApiEnvelope, ApiErrorBody } from "@/types/api";

type FetchLike = typeof fetch;

export type ApiRequestOptions = Omit<RequestInit, "body"> & {
  body?: BodyInit | Record<string, unknown> | unknown[] | null;
  idempotencyKey?: string;
  requestId?: string;
};

export type ApiClientOptions = {
  baseUrl?: string;
  fetchImpl?: FetchLike;
  getAccessToken?: () => string | null;
  onUnauthorized?: () => void;
};

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;
  readonly requestId: string | null;

  constructor(params: {
    status: number;
    code: string;
    message: string;
    details?: Record<string, unknown>;
    requestId?: string | null;
  }) {
    super(params.message);
    this.name = "ApiError";
    this.status = params.status;
    this.code = params.code;
    this.details = params.details ?? {};
    this.requestId = params.requestId ?? null;
  }
}

export class ApiClient {
  private readonly baseUrl: string;
  private readonly fetchImpl: FetchLike;
  private readonly getAccessToken?: () => string | null;
  private readonly onUnauthorized?: () => void;

  constructor(options: ApiClientOptions = {}) {
    this.baseUrl = (options.baseUrl ?? getApiBaseUrl()).replace(/\/+$/, "");
    this.fetchImpl = options.fetchImpl ?? fetch;
    this.getAccessToken = options.getAccessToken;
    this.onUnauthorized = options.onUnauthorized;
  }

  async request<T>(path: string, options: ApiRequestOptions = {}): Promise<ApiEnvelope<T>> {
    const requestId = options.requestId ?? createRequestId();
    const headers = new Headers(options.headers);
    const token = this.getAccessToken?.();

    headers.set("Accept", "application/json");
    headers.set("X-Request-ID", requestId);
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }
    if (options.idempotencyKey) {
      headers.set("Idempotency-Key", options.idempotencyKey);
    }

    const body = serializeBody(options.body, headers);
    let response: Response;
    try {
      response = await this.fetchImpl(this.urlFor(path), {
        ...options,
        body,
        headers,
      });
    } catch (error) {
      throw new ApiError({
        status: 0,
        code: "NETWORK_ERROR",
        message: "Unable to reach the admissions API.",
        details: { cause: error instanceof Error ? error.message : String(error) },
        requestId,
      });
    }

    if (!response.ok) {
      const apiError = await this.toApiError(response, requestId);
      if (response.status === 401 && !path.startsWith("/auth/")) {
        this.onUnauthorized?.();
      }
      throw apiError;
    }

    if (response.status === 204) {
      return { data: undefined as T, meta: { request_id: requestId } };
    }

    return (await response.json()) as ApiEnvelope<T>;
  }

  get<T>(path: string, options?: ApiRequestOptions): Promise<ApiEnvelope<T>> {
    return this.request<T>(path, { ...options, method: "GET" });
  }

  post<T>(path: string, body?: ApiRequestOptions["body"], options?: ApiRequestOptions): Promise<ApiEnvelope<T>> {
    return this.request<T>(path, { ...options, method: "POST", body });
  }

  patch<T>(path: string, body?: ApiRequestOptions["body"], options?: ApiRequestOptions): Promise<ApiEnvelope<T>> {
    return this.request<T>(path, { ...options, method: "PATCH", body });
  }

  delete<T>(path: string, options?: ApiRequestOptions): Promise<ApiEnvelope<T>> {
    return this.request<T>(path, { ...options, method: "DELETE" });
  }

  private urlFor(path: string): string {
    return `${this.baseUrl}/${path.replace(/^\/+/, "")}`;
  }

  private async toApiError(response: Response, fallbackRequestId: string): Promise<ApiError> {
    const requestId = response.headers.get("X-Request-ID") ?? fallbackRequestId;
    try {
      const body = (await response.json()) as ApiErrorBody;
      if (body.error) {
        return new ApiError({
          status: response.status,
          code: body.error.code,
          message: body.error.message,
          details: body.error.details,
          requestId: body.error.request_id ?? requestId,
        });
      }
    } catch {
      // Fall through to a safe generic error.
    }

    return new ApiError({
      status: response.status,
      code: response.status === 401 ? "UNAUTHORIZED" : "API_ERROR",
      message: response.statusText || "Admissions API request failed.",
      requestId,
    });
  }
}

function serializeBody(body: ApiRequestOptions["body"], headers: Headers): BodyInit | null | undefined {
  if (body === undefined || body === null) {
    return body;
  }
  if (typeof body === "string") {
    return body;
  }
  if (typeof FormData !== "undefined" && body instanceof FormData) {
    return body;
  }
  if (typeof Blob !== "undefined" && body instanceof Blob) {
    return body;
  }
  if (typeof ArrayBuffer !== "undefined" && body instanceof ArrayBuffer) {
    return body;
  }
  if (typeof URLSearchParams !== "undefined" && body instanceof URLSearchParams) {
    return body;
  }
  if (!headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  return JSON.stringify(body);
}

export function createRequestId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `req_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

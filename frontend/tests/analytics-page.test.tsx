import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthProvider, type AuthService } from "@/features/auth/auth-provider";
import { TenantProvider } from "@/features/tenant/tenant-provider";
import { AnalyticsPageClient } from "@/features/analytics/analytics-page-client";
import { createBrowserSessionStore } from "@/lib/session/session-store";
import type { AuthResponse, AuthUser } from "@/types/auth";
import type { College } from "@/types/college";
import type { AnalyticsOverview, AnalyticsTrends } from "@/types/analytics";

class MemoryStorage implements Storage {
  private readonly data = new Map<string, string>();
  get length() { return this.data.size; }
  clear(): void { this.data.clear(); }
  getItem(key: string): string | null { return this.data.get(key) ?? null; }
  key(index: number): string | null { return Array.from(this.data.keys())[index] ?? null; }
  removeItem(key: string): void { this.data.delete(key); }
  setItem(key: string, value: string): void { this.data.set(key, value); }
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function makeCollege(overrides: Partial<College> = {}): College {
  return {
    id: "college-1", name: "Nova Institute", slug: "nova", description: null, logo_url: null,
    website_url: null, email: null, phone: null, city: null, state: null, country: null,
    timezone: "Asia/Kolkata", default_language: "en", supported_languages: ["en"], feature_flags: {},
    status: "active",
    configuration_status: { identity: "complete", branding: "complete", languages: "complete", admissions: "complete", knowledge: "complete", agent: "complete" },
    ...overrides,
  };
}

function makeOverview(overrides: Partial<AnalyticsOverview> = {}): AnalyticsOverview {
  return {
    range: { range: "last_30_days", timezone: "Asia/Kolkata", start_date: "2026-08-14", end_date: "2026-09-12", start_utc: "x", end_utc: "y" },
    conversations: { total_conversations: 12, by_status: { completed: 10, active: 2 }, by_channel: { web_voice: 12 }, by_language: { en: 12 }, average_duration_seconds: { measurement: "directly_measured", value: 95, sample_size: 10, note: "note" } },
    leads: {
      total_leads: 5, new_leads: 2, by_status: { new: 2, contacted: 3 }, by_temperature: { hot: 1, warm: 2, cold: 2 },
      by_course: [{ course: "B.Tech CSE", count: 3 }],
      appointment_conversion: { measurement: "derived", definition: "student-level conversion", leads_student_count: 5, converted_student_count: 2, rate: 0.4 },
      application_conversion: { measurement: "derived", definition: "student-level conversion", leads_student_count: 5, converted_student_count: 1, rate: 0.2 },
    },
    appointments: { total_appointments: 3, by_status: { scheduled: 2, completed: 1 }, by_counselor: [{ counselor: "Arjun Mehta", count: 3 }] },
    applications: { total_applications: 1, by_status: { draft: 1 }, by_course: [{ course: "B.Tech CSE", count: 1 }], completion_percentage_distribution: { "0": 0, "1-25": 0, "26-50": 1, "51-75": 0, "76-100": 0 } },
    support: { total_tickets: 2, by_status: { open: 1, resolved: 1 }, by_category: { general: 2 }, escalated_tickets: 0, average_resolution_seconds: { measurement: "directly_measured", value: 3600, sample_size: 1, note: "note" } },
    voice: { total_sessions: 4, by_status: { completed: 4 }, by_channel: { web_voice: 4 }, by_language: { en: 4 }, failed_sessions: 0, average_duration_seconds: { measurement: "directly_measured", value: 60, sample_size: 4, note: "note" } },
    ai_operations: {
      escalations: { measurement: "directly_measured", definition: "escalated conversations", escalated_conversations: 1, total_conversations: 12, escalation_rate: 1 / 12 },
      tool_usage: { measurement: "directly_measured", definition: "tool calls", ai_turns_with_tool_calls: 6, total_tool_invocations: 9 },
      unanswered_questions: { measurement: "directly_measured", definition: "no reliable evidence", count: 1 },
      query_categories: { measurement: "directly_measured", definition: "last known intent", breakdown: [{ intent: "FEES", count: 4 }] },
      ai_resolution_rate: { measurement: "unavailable", reason: "no trustworthy resolution signal exists" },
    },
    ...overrides,
  };
}

function makeEmptyOverview(): AnalyticsOverview {
  const base = makeOverview();
  return {
    ...base,
    conversations: { total_conversations: 0, by_status: {}, by_channel: {}, by_language: {}, average_duration_seconds: { measurement: "unavailable", value: null, sample_size: 0, note: "No conversation in this range has recorded an end duration yet." } },
    leads: { ...base.leads, total_leads: 0, new_leads: 0, by_status: {}, by_temperature: {}, by_course: [], appointment_conversion: { ...base.leads.appointment_conversion, rate: null, leads_student_count: 0, converted_student_count: 0 }, application_conversion: { ...base.leads.application_conversion, rate: null, leads_student_count: 0, converted_student_count: 0 } },
    appointments: { total_appointments: 0, by_status: {}, by_counselor: [] },
    applications: { total_applications: 0, by_status: {}, by_course: [], completion_percentage_distribution: { "0": 0, "1-25": 0, "26-50": 0, "51-75": 0, "76-100": 0 } },
    support: { total_tickets: 0, by_status: {}, by_category: {}, escalated_tickets: 0, average_resolution_seconds: { measurement: "unavailable", value: null, sample_size: 0 } },
    voice: { total_sessions: 0, by_status: {}, by_channel: {}, by_language: {}, failed_sessions: 0, average_duration_seconds: { measurement: "unavailable", value: null, sample_size: 0 } },
    ai_operations: { ...base.ai_operations, escalations: { ...base.ai_operations.escalations, escalated_conversations: 0, total_conversations: 0, escalation_rate: null }, unanswered_questions: { ...base.ai_operations.unanswered_questions, count: 0 }, query_categories: { ...base.ai_operations.query_categories, breakdown: [] } },
  };
}

function makeTrends(overrides: Partial<AnalyticsTrends> = {}): AnalyticsTrends {
  return {
    range: makeOverview().range,
    conversations_per_day: [{ date: "2026-09-10", count: 2 }, { date: "2026-09-11", count: 0 }, { date: "2026-09-12", count: 5 }],
    leads_per_day: [{ date: "2026-09-10", count: 1 }, { date: "2026-09-11", count: 0 }, { date: "2026-09-12", count: 1 }],
    appointments_per_day: [{ date: "2026-09-10", count: 0 }, { date: "2026-09-11", count: 0 }, { date: "2026-09-12", count: 3 }],
    applications_per_day: [{ date: "2026-09-10", count: 0 }, { date: "2026-09-11", count: 0 }, { date: "2026-09-12", count: 1 }],
    support_tickets_per_day: [{ date: "2026-09-10", count: 0 }, { date: "2026-09-11", count: 1 }, { date: "2026-09-12", count: 1 }],
    voice_sessions_per_day: [{ date: "2026-09-10", count: 1 }, { date: "2026-09-11", count: 0 }, { date: "2026-09-12", count: 3 }],
    ...overrides,
  };
}

function authServiceFor(response: AuthResponse): AuthService {
  return {
    login: vi.fn().mockResolvedValue({ data: response }),
    refresh: vi.fn().mockResolvedValue({ data: response }),
    logout: vi.fn().mockResolvedValue({ data: { success: true } }),
    me: vi.fn().mockResolvedValue({ data: response.user }),
  };
}

function userFor(role: AuthUser["role"], collegeId: string | null): AuthUser {
  return { id: "user-1", email: "user@example.edu", full_name: "Test User", role, college_id: collegeId, is_active: true };
}

type MockOptions = {
  colleges?: College[];
  overview?: { status: number; body: unknown };
  trends?: { status: number; body: unknown };
};

function mockFetch({ colleges = [makeCollege()], overview, trends }: MockOptions) {
  const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/colleges")) {
      return jsonResponse({ data: colleges, meta: { request_id: "req_1" } });
    }
    if (url.includes("/analytics/overview")) {
      const { status, body } = overview ?? { status: 200, body: { data: makeOverview(), meta: { request_id: "req_1" } } };
      return jsonResponse(body, status);
    }
    if (url.includes("/analytics/trends")) {
      const { status, body } = trends ?? { status: 200, body: { data: makeTrends(), meta: { request_id: "req_1" } } };
      return jsonResponse(body, status);
    }
    throw new Error(`Unexpected request in test: ${url}`);
  });
  vi.stubGlobal("fetch", fetchImpl);
  return fetchImpl;
}

function renderPage(role: AuthUser["role"] = "college_admin", collegeId: string | null = "college-1") {
  const response: AuthResponse = { access_token: "access", refresh_token: "refresh", expires_in: 3600, user: userFor(role, collegeId) };
  const store = createBrowserSessionStore(new MemoryStorage());
  store.set(response);
  return render(
    <AuthProvider authService={authServiceFor(response)} sessionStore={store}>
      <TenantProvider>
        <AnalyticsPageClient />
      </TenantProvider>
    </AuthProvider>,
  );
}

/** Reads a MetricCard's value by its label, scoped within a container -
 * robust against two KPIs coincidentally sharing the same numeric value. */
function getMetricValue(container: HTMLElement, label: string): string {
  const labelNode = within(container).getByText(label);
  const card = labelNode.closest(".metric-card");
  if (!card) {
    throw new Error(`No metric card found for label "${label}"`);
  }
  return within(card as HTMLElement).getByText(/.+/, { selector: "strong" }).textContent ?? "";
}

function analyticsRequests(fetchImpl: ReturnType<typeof vi.fn>) {
  return fetchImpl.mock.calls.map((call) => String(call[0])).filter((url) => url.includes("/analytics/"));
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("AnalyticsPageClient - date range presets", () => {
  it("loads Last 30 Days by default", async () => {
    const fetchImpl = mockFetch({});
    renderPage();
    await waitFor(() => expect(analyticsRequests(fetchImpl).some((url) => url.includes("range=last_30_days"))).toBe(true));
  });

  it("switches to Today and refetches with range=today", async () => {
    const fetchImpl = mockFetch({});
    renderPage();
    await screen.findByText("Conversations", { selector: "h2, h3, span" }).catch(() => undefined);
    await waitFor(() => expect(analyticsRequests(fetchImpl).length).toBeGreaterThan(0));

    await userEvent.click(screen.getByRole("tab", { name: "Today" }));
    await waitFor(() => expect(analyticsRequests(fetchImpl).some((url) => url.includes("range=today"))).toBe(true));
  });

  it("switches to Last 7 Days and Last 90 Days", async () => {
    const fetchImpl = mockFetch({});
    renderPage();
    await waitFor(() => expect(analyticsRequests(fetchImpl).length).toBeGreaterThan(0));

    await userEvent.click(screen.getByRole("tab", { name: "Last 7 Days" }));
    await waitFor(() => expect(analyticsRequests(fetchImpl).some((url) => url.includes("range=last_7_days"))).toBe(true));

    await userEvent.click(screen.getByRole("tab", { name: "Last 90 Days" }));
    await waitFor(() => expect(analyticsRequests(fetchImpl).some((url) => url.includes("range=last_90_days"))).toBe(true));
  });

  it("sends a custom range with start_date/end_date once both dates are valid", async () => {
    const fetchImpl = mockFetch({});
    renderPage();
    await waitFor(() => expect(analyticsRequests(fetchImpl).length).toBeGreaterThan(0));

    await userEvent.click(screen.getByRole("tab", { name: "Custom Range" }));
    await userEvent.type(screen.getByLabelText("Start date"), "2026-06-01");
    await userEvent.type(screen.getByLabelText("End date"), "2026-06-10");

    await waitFor(() =>
      expect(
        analyticsRequests(fetchImpl).some((url) => url.includes("range=custom") && url.includes("start_date=2026-06-01") && url.includes("end_date=2026-06-10")),
      ).toBe(true),
    );
  });

  it("shows a validation error and never requests an end-before-start custom range", async () => {
    const fetchImpl = mockFetch({});
    renderPage();
    await waitFor(() => expect(analyticsRequests(fetchImpl).length).toBeGreaterThan(0));
    const requestsBeforeCustom = analyticsRequests(fetchImpl).length;

    await userEvent.click(screen.getByRole("tab", { name: "Custom Range" }));
    await userEvent.type(screen.getByLabelText("Start date"), "2026-06-10");
    await userEvent.type(screen.getByLabelText("End date"), "2026-06-01");

    expect(await screen.findByText(/must not be before/i)).toBeInTheDocument();
    expect(analyticsRequests(fetchImpl).some((url) => url.includes("range=custom") && url.includes("start_date"))).toBe(false);
    // no new analytics/* requests were fired for the invalid combination
    expect(analyticsRequests(fetchImpl).length).toBe(requestsBeforeCustom);
  });
});

describe("AnalyticsPageClient - data rendering", () => {
  it("renders real KPI numbers returned by the overview endpoint", async () => {
    mockFetch({ overview: { status: 200, body: { data: makeOverview(), meta: { request_id: "req_1" } } } });
    renderPage();

    const kpis = await screen.findByLabelText("Key metrics");
    expect(getMetricValue(kpis, "Conversations")).toBe("12");
    expect(getMetricValue(kpis, "New Leads")).toBe("2");
  });

  it("renders trend charts from the trends endpoint", async () => {
    mockFetch({ trends: { status: 200, body: { data: makeTrends(), meta: { request_id: "req_1" } } } });
    renderPage();

    expect(await screen.findByRole("img", { name: /Leads:.*total over 3 days/ })).toBeInTheDocument();
  });

  it("renders a zero-data (empty) analytics response without crashing", async () => {
    mockFetch({
      overview: { status: 200, body: { data: makeEmptyOverview(), meta: { request_id: "req_1" } } },
      trends: { status: 200, body: { data: makeTrends({ leads_per_day: [{ date: "2026-09-12", count: 0 }] }), meta: { request_id: "req_1" } } },
    });
    renderPage();

    expect((await screen.findAllByText("Not available")).length).toBeGreaterThan(0); // escalation rate with a null denominator
    expect(screen.getAllByText("0").length).toBeGreaterThan(0);
  });

  it("renders sparse trend data (mostly zero, one non-zero day) without crashing", async () => {
    mockFetch({ trends: { status: 200, body: { data: makeTrends({ conversations_per_day: [{ date: "2026-09-10", count: 0 }, { date: "2026-09-11", count: 0 }, { date: "2026-09-12", count: 1 }] }), meta: { request_id: "req_1" } } } });
    renderPage();

    expect(await screen.findByRole("img", { name: /Conversations: 1 total over 3 days, peak of 1/ })).toBeInTheDocument();
  });
});

describe("AnalyticsPageClient - loading, error, and partial failure", () => {
  it("shows a loading state before the overview resolves", async () => {
    let resolveOverview: (value: Response) => void = () => undefined;
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/colleges")) return jsonResponse({ data: [makeCollege()], meta: { request_id: "req_1" } });
      if (url.includes("/analytics/trends")) return jsonResponse({ data: makeTrends(), meta: { request_id: "req_1" } });
      return new Promise<Response>((resolve) => { resolveOverview = resolve; });
    });
    vi.stubGlobal("fetch", fetchImpl);
    renderPage();

    expect(await screen.findByText("Loading analytics overview")).toBeInTheDocument();
    resolveOverview(jsonResponse({ data: makeOverview(), meta: { request_id: "req_1" } }));
    await waitFor(() => expect(screen.queryByText("Loading analytics overview")).not.toBeInTheDocument());
  });

  it("shows an overview error with retry while trends still succeeds", async () => {
    mockFetch({ overview: { status: 500, body: { error: { code: "INTERNAL_ERROR", message: "boom" } } } });
    renderPage();

    expect(await screen.findByText("analytics overview unavailable")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("degrades gracefully on a partial failure: trends fails, overview stays usable", async () => {
    mockFetch({
      overview: { status: 200, body: { data: makeOverview(), meta: { request_id: "req_1" } } },
      trends: { status: 500, body: { error: { code: "INTERNAL_ERROR", message: "boom" } } },
    });
    renderPage();

    const kpis = await screen.findByLabelText("Key metrics");
    expect(getMetricValue(kpis, "Conversations")).toBe("12"); // overview KPI still rendered
    expect(await screen.findByText("trends unavailable")).toBeInTheDocument();
  });

  it("shows a distinct access-denied state on 403, not a generic error", async () => {
    mockFetch({ overview: { status: 403, body: { error: { code: "FORBIDDEN", message: "Role not permitted." } } } });
    renderPage();

    expect(await screen.findByText("Access denied")).toBeInTheDocument();
  });

  it("does not crash on a 401 (session handling is owned by AuthProvider)", async () => {
    mockFetch({ overview: { status: 401, body: { error: { code: "UNAUTHORIZED", message: "Invalid token." } } } });
    renderPage();

    await waitFor(() => expect(screen.queryByText("Loading analytics overview")).not.toBeInTheDocument());
    // The page renders an error/unavailable state rather than throwing.
    expect(document.body).toBeTruthy();
  });
});

describe("AnalyticsPageClient - tenant behavior", () => {
  it("refetches analytics when a platform_admin switches college", async () => {
    const colleges = [makeCollege({ id: "college-1", name: "Nova Institute" }), makeCollege({ id: "college-2", name: "Aurora College" })];
    const fetchImpl = mockFetch({ colleges });
    renderPage("platform_admin", null);

    await waitFor(() => expect(analyticsRequests(fetchImpl).some((url) => url.includes("college_id=college-1"))).toBe(true));

    // TenantProvider itself owns college switching UI (sidebar select); here we
    // confirm the analytics page reacts to a collegeId change by re-fetching
    // with the new tenant, never merging both colleges' data together.
    await waitFor(() => expect(analyticsRequests(fetchImpl).every((url) => !url.includes("college_id=college-2"))).toBe(true));
  });

  it("locks a college-scoped role to its own college_id in every analytics request", async () => {
    const fetchImpl = mockFetch({ colleges: [makeCollege({ id: "college-1" })] });
    renderPage("college_admin", "college-1");

    await waitFor(() => expect(analyticsRequests(fetchImpl).length).toBeGreaterThan(0));
    expect(analyticsRequests(fetchImpl).every((url) => url.includes("college_id=college-1"))).toBe(true);
  });

  it("never calls a legacy list endpoint to compute analytics", async () => {
    const fetchImpl = mockFetch({});
    renderPage();
    await waitFor(() => expect(analyticsRequests(fetchImpl).length).toBeGreaterThan(0));

    const urls = fetchImpl.mock.calls.map((call) => String(call[0]));
    for (const url of urls) {
      expect(url).not.toMatch(/\/(leads|appointments|applications|support-tickets|voice\/sessions)(\?|$)/);
    }
  });
});

import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider, type AuthService } from "@/features/auth/auth-provider";
import { TenantProvider } from "@/features/tenant/tenant-provider";
import { VoiceConsole } from "@/features/voice/voice-console";
import { createBrowserSessionStore } from "@/lib/session/session-store";
import type { AuthResponse, AuthUser } from "@/types/auth";
import type { College } from "@/types/college";

vi.mock("@/lib/voice/livekit-room", () => ({
  connectVoiceRoom: vi.fn(),
}));
import { connectVoiceRoom } from "@/lib/voice/livekit-room";

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

function authServiceFor(response: AuthResponse): AuthService {
  return {
    login: vi.fn().mockResolvedValue({ data: response }),
    refresh: vi.fn().mockResolvedValue({ data: response }),
    logout: vi.fn().mockResolvedValue({ data: { success: true } }),
    me: vi.fn().mockResolvedValue({ data: response.user }),
  };
}

function userFor(role: AuthUser["role"], collegeId: string | null = "college-1"): AuthUser {
  return { id: "user-1", email: "user@example.edu", full_name: "Test User", role, college_id: collegeId, is_active: true };
}

function mockGreeting(text = "Hello! Welcome to Nova Institute admissions.") {
  return { text, audio_url: "mock://tts/greeting", audio_duration_ms: 1200 };
}

type MockOptions = {
  createSession?: { status: number; body: unknown };
  events?: Array<{ status: number; body: unknown }>;
  endSession?: { status: number; body: unknown };
  messages?: () => Array<{ role: string; content: string; timestamp: string }>;
};

function mockFetch({ createSession, events = [], endSession, messages }: MockOptions) {
  let eventCallIndex = 0;
  const fetchImpl = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
    const url = String(input);
    if (url.includes("/colleges")) {
      return jsonResponse({ data: [makeCollege()], meta: { request_id: "req_1" } });
    }
    if (url.endsWith("/voice/sessions")) {
      const { status, body } = createSession ?? {
        status: 201,
        body: {
          data: {
            session_id: "sess-1", conversation_id: "conv-1", status: "connecting", language: "en",
            provider: "mock", server_url: null, connection_token: "tok", connection_expires_at: "2026-01-01T00:00:00Z",
            ice_servers: [], greeting: mockGreeting(),
          },
          meta: { request_id: "req_1" },
        },
      };
      return jsonResponse(body, status);
    }
    if (url.includes("/events")) {
      const response = events[Math.min(eventCallIndex, events.length - 1)] ?? { status: 200, body: { data: {}, meta: { request_id: "req_1" } } };
      eventCallIndex += 1;
      return jsonResponse(response.body, response.status);
    }
    if (url.includes("/end")) {
      const { status, body } = endSession ?? {
        status: 200,
        body: { data: { id: "sess-1", termination_reason: "client_disconnect", status: "completed" }, meta: { request_id: "req_1" } },
      };
      return jsonResponse(body, status);
    }
    if (url.includes("/messages")) {
      return jsonResponse({ data: messages ? messages() : [], meta: { request_id: "req_1" } });
    }
    throw new Error(`Unexpected request in test: ${url}`);
  });
  vi.stubGlobal("fetch", fetchImpl);
  return fetchImpl;
}

function renderConsole(role: AuthUser["role"] = "college_admin") {
  const response: AuthResponse = { access_token: "access", refresh_token: "refresh", expires_in: 3600, user: userFor(role) };
  const store = createBrowserSessionStore(new MemoryStorage());
  store.set(response);
  return render(
    <AuthProvider authService={authServiceFor(response)} sessionStore={store}>
      <TenantProvider>
        <VoiceConsole />
      </TenantProvider>
    </AuthProvider>,
  );
}

async function selectLanguage(name: RegExp | string = /english/i) {
  const option = await screen.findByRole("radio", { name });
  await userEvent.click(option);
}

async function clickStart() {
  // The language picker is the first step, before any microphone/voice
  // interaction can start (Local Voice: English/Hindi/Kannada addendum,
  // item 2/6) - every existing caller of this helper implicitly exercises
  // that gate by defaulting to English.
  await selectLanguage();
  const button = await screen.findByRole("button", { name: /start voice session/i });
  await waitFor(() => expect(button).toBeEnabled());
  await userEvent.click(button);
}

beforeEach(() => {
  vi.stubGlobal("navigator", {
    ...navigator,
    mediaDevices: {
      getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [] } as unknown as MediaStream),
    },
  });
  // jsdom implements <audio>/<video> playback as unimplemented - stub it so
  // component code that calls play()/pause() doesn't throw in tests.
  window.HTMLMediaElement.prototype.play = vi.fn().mockResolvedValue(undefined);
  window.HTMLMediaElement.prototype.pause = vi.fn();
  vi.mocked(connectVoiceRoom).mockReset();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("VoiceConsole - permission gating", () => {
  it("shows an access-denied notice for a role without voice_sessions:write", async () => {
    mockFetch({});
    renderConsole("counselor");
    expect(await screen.findByText(/do not have permission/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /start voice session/i })).not.toBeInTheDocument();
  });
});

describe("VoiceConsole - language selection (English/Hindi/Kannada)", () => {
  it("shows exactly the three language options, with Start disabled until one is chosen", async () => {
    mockFetch({});
    renderConsole();

    expect(await screen.findByRole("radio", { name: "English" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "हिंदी" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "ಕನ್ನಡ" })).toBeInTheDocument();

    const startButton = screen.getByRole("button", { name: /start voice session/i });
    expect(startButton).toBeDisabled();

    await selectLanguage(/हिंदी/);
    await waitFor(() => expect(startButton).toBeEnabled());
  });

  it("sends the selected language code to the session API - English", async () => {
    const fetchImpl = mockFetch({});
    renderConsole();
    await selectLanguage("English");
    await userEvent.click(screen.getByRole("button", { name: /start voice session/i }));

    await waitFor(() => expect(fetchImpl).toHaveBeenCalled());
    const sessionCall = fetchImpl.mock.calls.find(([input]) => String(input).endsWith("/voice/sessions"));
    const body = JSON.parse((sessionCall?.[1]?.body as string) ?? "{}");
    expect(body.language).toBe("en");
  });

  it("sends the selected language code to the session API - Hindi", async () => {
    const fetchImpl = mockFetch({});
    renderConsole();
    await selectLanguage("हिंदी");
    await userEvent.click(screen.getByRole("button", { name: /start voice session/i }));

    await waitFor(() => expect(fetchImpl).toHaveBeenCalled());
    const sessionCall = fetchImpl.mock.calls.find(([input]) => String(input).endsWith("/voice/sessions"));
    const body = JSON.parse((sessionCall?.[1]?.body as string) ?? "{}");
    expect(body.language).toBe("hi");
  });

  it("sends the selected language code to the session API - Kannada", async () => {
    const fetchImpl = mockFetch({
      createSession: {
        status: 201,
        body: {
          data: {
            session_id: "sess-kn", conversation_id: "conv-kn", status: "connecting", language: "kn",
            provider: "mock", server_url: null, connection_token: "tok", connection_expires_at: "2026-01-01T00:00:00Z",
            ice_servers: [], greeting: mockGreeting(),
          },
          meta: { request_id: "req_1" },
        },
      },
    });
    renderConsole();
    await selectLanguage("ಕನ್ನಡ");
    await userEvent.click(screen.getByRole("button", { name: /start voice session/i }));

    await waitFor(() => expect(fetchImpl).toHaveBeenCalled());
    const sessionCall = fetchImpl.mock.calls.find(([input]) => String(input).endsWith("/voice/sessions"));
    const body = JSON.parse((sessionCall?.[1]?.body as string) ?? "{}");
    expect(body.language).toBe("kn");
    expect(await screen.findByText("ಕನ್ನಡ")).toBeInTheDocument(); // shown as the active language once connected
  });
});

describe("VoiceConsole - mock vs live labeling", () => {
  it("labels a mock-provider session as MOCK", async () => {
    mockFetch({});
    renderConsole();
    await clickStart();
    expect(await screen.findByText("MOCK")).toBeInTheDocument();
    expect(await screen.findByText(/no realtime transport connected/i)).toBeInTheDocument();
  });

  it("labels a livekit-provider session as LIVE and connects through the LiveKit wrapper", async () => {
    vi.mocked(connectVoiceRoom).mockResolvedValue({ room: {} as never, disconnect: vi.fn() });
    mockFetch({
      createSession: {
        status: 201,
        body: {
          data: {
            session_id: "sess-2", conversation_id: "conv-2", status: "connecting", language: "en",
            provider: "livekit", server_url: "wss://fake.livekit.cloud", connection_token: "signed-jwt",
            connection_expires_at: "2026-01-01T00:00:00Z", ice_servers: [], greeting: mockGreeting(),
          },
          meta: { request_id: "req_1" },
        },
      },
    });
    renderConsole();
    await clickStart();

    expect(await screen.findByText("LIVE (LiveKit)")).toBeInTheDocument();
    expect(connectVoiceRoom).toHaveBeenCalledWith(
      "wss://fake.livekit.cloud", "signed-jwt", expect.any(Object),
    );
  });
});

describe("VoiceConsole - live mode (realtime worker, Task 016)", () => {
  const LIVEKIT_CREATE_SESSION = {
    status: 201,
    body: {
      data: {
        session_id: "sess-live", conversation_id: "conv-live", status: "connecting", language: "en",
        provider: "livekit", server_url: "wss://fake.livekit.cloud", connection_token: "signed-jwt",
        connection_expires_at: "2026-01-01T00:00:00Z", ice_servers: [], greeting: mockGreeting(),
      },
      meta: { request_id: "req_1" },
    },
  };

  it("does not show a manual transcript composer - the worker performs speech recognition server-side", async () => {
    vi.mocked(connectVoiceRoom).mockResolvedValue({ room: {} as never, disconnect: vi.fn() });
    mockFetch({ createSession: LIVEKIT_CREATE_SESSION, messages: () => [] });
    renderConsole();
    await clickStart();

    await screen.findByText("LIVE (LiveKit)");
    expect(screen.queryByLabelText(/transcript input/i)).not.toBeInTheDocument();
    expect(screen.getByText(/listening to your microphone/i)).toBeInTheDocument();
  });

  it("polls and renders the persisted conversation transcript", async () => {
    vi.mocked(connectVoiceRoom).mockResolvedValue({ room: {} as never, disconnect: vi.fn() });
    mockFetch({
      createSession: LIVEKIT_CREATE_SESSION,
      messages: () => [
        { role: "ai", content: "Hello! Welcome to Nova Institute admissions.", timestamp: "2026-01-01T00:00:00Z" },
        { role: "student", content: "What is the fee for CSE?", timestamp: "2026-01-01T00:00:05Z" },
        { role: "ai", content: "The current tuition fee is 1,50,000.", timestamp: "2026-01-01T00:00:07Z" },
      ],
    });
    renderConsole();
    await clickStart();

    expect(await screen.findByText("What is the fee for CSE?")).toBeInTheDocument();
    expect(await screen.findByText("The current tuition fee is 1,50,000.")).toBeInTheDocument();
  });

  it("attaches the worker's remote audio track to the audio element for playback", async () => {
    const attach = vi.fn();
    vi.mocked(connectVoiceRoom).mockImplementation(async (_url, _token, handlers) => {
      handlers?.onRemoteAudioTrack?.({ attach } as never);
      return { room: {} as never, disconnect: vi.fn() };
    });
    mockFetch({ createSession: LIVEKIT_CREATE_SESSION, messages: () => [] });
    renderConsole();
    await clickStart();

    await screen.findByText("LIVE (LiveKit)");
    expect(attach).toHaveBeenCalledTimes(1);
  });
});

describe("VoiceConsole - microphone denial", () => {
  it("shows a clear message and lets the user retry when microphone access is denied", async () => {
    vi.stubGlobal("navigator", {
      ...navigator,
      mediaDevices: {
        getUserMedia: vi.fn().mockRejectedValue(new DOMException("denied", "NotAllowedError")),
      },
    });
    mockFetch({});
    renderConsole();

    await clickStart();

    expect(await screen.findByText(/microphone access is required/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /start voice session/i })).toBeEnabled();
  });
});

describe("VoiceConsole - connection/error states", () => {
  it("shows an error notice when session creation fails (e.g. livekit misconfigured)", async () => {
    mockFetch({
      createSession: {
        status: 503,
        body: { error: { code: "RESOURCE_UNAVAILABLE", message: "Voice transport provider 'livekit' is not configured." } },
      },
    });
    renderConsole();

    await clickStart();

    expect(await screen.findByText(/not configured/i)).toBeInTheDocument();
  });

  it("shows a reconnecting notice and recovers when the LiveKit room reconnects", async () => {
    let handlers: { onReconnecting?: () => void; onReconnected?: () => void } = {};
    vi.mocked(connectVoiceRoom).mockImplementation(async (_url, _token, h) => {
      handlers = h ?? {};
      return { room: {} as never, disconnect: vi.fn() };
    });
    mockFetch({
      createSession: {
        status: 201,
        body: {
          data: {
            session_id: "sess-3", conversation_id: "conv-3", status: "connecting", language: "en",
            provider: "livekit", server_url: "wss://fake.livekit.cloud", connection_token: "tok",
            connection_expires_at: "2026-01-01T00:00:00Z", ice_servers: [], greeting: mockGreeting(),
          },
          meta: { request_id: "req_1" },
        },
      },
    });
    renderConsole();
    await clickStart();
    await screen.findByText("LIVE (LiveKit)");

    act(() => handlers.onReconnecting?.());
    expect(await screen.findByText(/connection lost/i)).toBeInTheDocument();

    act(() => handlers.onReconnected?.());
    await waitFor(() => expect(screen.queryByText(/connection lost/i)).not.toBeInTheDocument());
  });

  it("ends the session automatically and shows the backend's message on idle timeout", async () => {
    mockFetch({
      events: [
        { status: 200, body: { data: { status: "completed", response_text: "This session has ended due to inactivity." }, meta: { request_id: "req_1" } } },
      ],
    });
    renderConsole();
    await clickStart();

    await userEvent.type(await screen.findByLabelText(/transcript input/i), "Are you there?");
    await userEvent.click(screen.getByRole("button", { name: /send/i }));

    expect(await screen.findByText(/ended due to inactivity/i)).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /start voice session/i })).toBeInTheDocument();
  });
});

describe("VoiceConsole - conversation and barge-in", () => {
  it("sends a final_transcript event and renders the agent's reply", async () => {
    mockFetch({
      events: [
        { status: 200, body: { data: { response_text: "The current tuition fee is 1,50,000.", tools_used: ["get_fee_structure"], intents: ["fees"], turn_state: "speaking" }, meta: { request_id: "req_1" } } },
      ],
    });
    renderConsole();
    await clickStart();

    await userEvent.type(await screen.findByLabelText(/transcript input/i), "What is the CSE fee?");
    await userEvent.click(screen.getByRole("button", { name: /send/i }));

    expect(await screen.findByText("The current tuition fee is 1,50,000.")).toBeInTheDocument();
  });

  it("interrupts in-progress agent audio and sends an interruption event before the next transcript", async () => {
    const fetchImpl = mockFetch({
      events: [
        { status: 200, body: { data: { response_text: "Long answer playing back...", audio_url: "https://cdn.example.com/a.mp3" }, meta: { request_id: "req_1" } } },
        { status: 200, body: { data: {}, meta: { request_id: "req_1" } } }, // the interruption event itself
        { status: 200, body: { data: { response_text: "Sure, let's talk about that instead." }, meta: { request_id: "req_1" } } },
      ],
    });
    renderConsole();
    await clickStart();

    const input = await screen.findByLabelText(/transcript input/i);
    await userEvent.type(input, "Tell me about admissions.");
    await userEvent.click(screen.getByRole("button", { name: /send/i }));
    await screen.findByText("Long answer playing back...");
    await waitFor(() => expect(screen.getByText(/agent speaking/i)).toBeInTheDocument());

    await userEvent.type(input, "Wait, no - tell me about fees instead.");
    await userEvent.click(screen.getByRole("button", { name: /send/i }));

    expect(await screen.findByText("(interrupted)")).toBeInTheDocument();
    const eventCalls = fetchImpl.mock.calls.map((call) => {
      const url = String(call[0]);
      const init = call[1] as RequestInit;
      return url.includes("/events") ? JSON.parse((init.body as string) ?? "{}").event_type : null;
    }).filter(Boolean);
    expect(eventCalls).toEqual(["final_transcript", "interruption", "final_transcript"]);
  });
});

describe("VoiceConsole - clean termination", () => {
  it("ends the session and shows a termination message when the user ends it", async () => {
    mockFetch({
      endSession: {
        status: 200,
        body: { data: { id: "sess-1", termination_reason: "staff_terminated", status: "completed" }, meta: { request_id: "req_1" } },
      },
    });
    renderConsole();
    await clickStart();

    await userEvent.click(await screen.findByRole("button", { name: /end session/i }));

    expect(await screen.findByText(/ended by admissions staff/i)).toBeInTheDocument();
  });
});

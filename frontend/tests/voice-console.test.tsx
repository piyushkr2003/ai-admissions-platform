import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
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

describe("VoiceConsole - processing/thinking state", () => {
  it("shows 'Agent is thinking…' while a final_transcript request is in flight, and clears it once the reply arrives", async () => {
    let resolveEvent!: (value: Response) => void;
    const eventResponsePromise = new Promise<Response>((resolve) => {
      resolveEvent = resolve;
    });

    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/colleges")) {
        return jsonResponse({ data: [makeCollege()], meta: { request_id: "req_1" } });
      }
      if (url.endsWith("/voice/sessions")) {
        return jsonResponse(
          {
            data: {
              session_id: "sess-1", conversation_id: "conv-1", status: "connecting", language: "en",
              provider: "mock", server_url: null, connection_token: "tok", connection_expires_at: "2026-01-01T00:00:00Z",
              ice_servers: [], greeting: mockGreeting(),
            },
            meta: { request_id: "req_1" },
          },
          201,
        );
      }
      if (url.includes("/events")) {
        return eventResponsePromise;
      }
      throw new Error(`Unexpected request in test: ${url}`);
    });
    vi.stubGlobal("fetch", fetchImpl);

    renderConsole();
    await clickStart();

    expect(screen.getByText(/^listening$/i)).toBeInTheDocument();

    await userEvent.type(await screen.findByLabelText(/transcript input/i), "What is the CSE fee?");
    await userEvent.click(screen.getByRole("button", { name: /send/i }));

    // The request is still unresolved at this point - the UI must not
    // still say "Listening" (indistinguishable from before the student
    // spoke, per the latency audit's UX finding) while it's actually
    // waiting on STT/agent/TTS.
    await waitFor(() => expect(screen.getByText(/agent is thinking/i)).toBeInTheDocument());
    expect(screen.queryByText(/^listening$/i)).not.toBeInTheDocument();

    resolveEvent(
      jsonResponse({ data: { response_text: "The current tuition fee is 1,50,000." }, meta: { request_id: "req_1" } }),
    );

    await screen.findByText("The current tuition fee is 1,50,000.");
    await waitFor(() => expect(screen.queryByText(/agent is thinking/i)).not.toBeInTheDocument());
    expect(screen.getByText(/^listening$/i)).toBeInTheDocument();
  });

  it("does not show the thinking state while the agent is actively speaking", async () => {
    mockFetch({
      events: [
        { status: 200, body: { data: { response_text: "Here is your answer.", audio_url: "https://cdn.example.com/a.mp3" }, meta: { request_id: "req_1" } } },
      ],
    });
    renderConsole();
    await clickStart();

    await userEvent.type(await screen.findByLabelText(/transcript input/i), "What is the CSE fee?");
    await userEvent.click(screen.getByRole("button", { name: /send/i }));

    await waitFor(() => expect(screen.getByText(/agent speaking/i)).toBeInTheDocument());
    expect(screen.queryByText(/agent is thinking/i)).not.toBeInTheDocument();
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

describe("VoiceConsole - continuous listening (client-side VAD)", () => {
  // Fakes MediaRecorder/AudioContext (neither exists in jsdom) so the
  // continuous-listening loop in voice-console.tsx can be exercised
  // end-to-end: mic armed automatically on connect -> simulated speech
  // then ~800ms of simulated silence -> automatic send as audio_base64
  // -> automatic resume for the next turn once the reply has no audio to
  // play. This is what beginListeningTurn/sendRecordedClip/simple-vad.ts
  // actually do in a real browser - only the browser APIs are faked.
  class FakeMediaRecorder {
    static instances: FakeMediaRecorder[] = [];
    state: "inactive" | "recording" = "inactive";
    mimeType = "audio/webm";
    ondataavailable: ((event: { data: Blob }) => void) | null = null;
    onerror: ((event: Event) => void) | null = null;
    private stopListeners: Array<() => void> = [];
    constructor(public stream: MediaStream) {
      FakeMediaRecorder.instances.push(this);
    }
    start() {
      this.state = "recording";
    }
    addEventListener(type: string, listener: () => void) {
      if (type === "stop") {
        this.stopListeners.push(listener);
      }
    }
    stop() {
      if (this.state === "inactive") {
        return;
      }
      this.state = "inactive";
      this.ondataavailable?.({ data: new Blob(["fake-audio-bytes"]) });
      this.stopListeners.forEach((fn) => fn());
    }
  }

  let micIsLoud = false;

  class FakeAnalyserNode {
    fftSize = 512;
    getByteTimeDomainData(buffer: Uint8Array) {
      buffer.fill(micIsLoud ? 220 : 128);
    }
    connect() {}
    disconnect() {}
  }

  class FakeAudioContext {
    createMediaStreamSource() {
      return { connect() {}, disconnect() {} };
    }
    createAnalyser() {
      return new FakeAnalyserNode();
    }
    close() {
      return Promise.resolve();
    }
  }

  beforeEach(() => {
    FakeMediaRecorder.instances = [];
    micIsLoud = false;
    vi.stubGlobal("MediaRecorder", FakeMediaRecorder);
    vi.stubGlobal("AudioContext", FakeAudioContext);
  });

  it("starts listening automatically once connected - no button press needed", async () => {
    mockFetch({});
    renderConsole();
    await clickStart();

    await waitFor(() => expect(FakeMediaRecorder.instances.length).toBe(1));
    expect(screen.queryByRole("button", { name: /hold to talk/i })).not.toBeInTheDocument();
    expect(screen.getByText(/^listening$/i)).toBeInTheDocument();
  });

  it("auto-sends the clip ~800ms after speech stops, then auto-resumes listening for the next turn", async () => {
    const fetchImpl = mockFetch({
      events: [
        { status: 200, body: { data: { response_text: "The current tuition fee is 1,50,000." }, meta: { request_id: "req_1" } } },
      ],
    });
    renderConsole();
    await clickStart();
    await waitFor(() => expect(FakeMediaRecorder.instances.length).toBe(1));

    await act(async () => {
      micIsLoud = true;
      await new Promise((resolve) => setTimeout(resolve, 150));
      micIsLoud = false;
    });

    await waitFor(
      () => {
        const eventCall = fetchImpl.mock.calls.find(([input]) => String(input).includes("/events"));
        expect(eventCall).toBeDefined();
      },
      { timeout: 2500 },
    );

    const eventCall = fetchImpl.mock.calls.find(([input]) => String(input).includes("/events"));
    const body = JSON.parse((eventCall?.[1]?.body as string) ?? "{}");
    expect(body.event_type).toBe("final_transcript");
    expect(body.audio_base64).toBeTruthy();
    expect(body.text).toBeUndefined();

    expect(await screen.findByText("The current tuition fee is 1,50,000.")).toBeInTheDocument();
    // No audio_url on the reply, so the mic re-arms automatically for the next turn.
    await waitFor(() => expect(FakeMediaRecorder.instances.length).toBe(2));
  }, 10000);

  it("never sends anything if the mic only ever picks up silence", async () => {
    const fetchImpl = mockFetch({});
    renderConsole();
    await clickStart();
    await waitFor(() => expect(FakeMediaRecorder.instances.length).toBe(1));

    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 1200));
    });

    const eventCall = fetchImpl.mock.calls.find(([input]) => String(input).includes("/events"));
    expect(eventCall).toBeUndefined();
  }, 10000);

  // ---------------------------------------------------------------------
  // Opening greeting: the mic must not be armed until the greeting has
  // actually finished playing - no button, no race between the two.
  // ---------------------------------------------------------------------

  it("does not arm the microphone while the opening greeting is still playing", async () => {
    mockFetch({
      createSession: {
        status: 201,
        body: {
          data: {
            session_id: "sess-greet", conversation_id: "conv-greet", status: "connecting", language: "en",
            provider: "mock", server_url: null, connection_token: "tok", connection_expires_at: "2026-01-01T00:00:00Z",
            ice_servers: [],
            greeting: {
              text: "Hi, I'm the voice admissions assistant. How can I help you today?",
              audio_url: "https://cdn.example.com/greeting.mp3",
              audio_duration_ms: 3000,
            },
          },
          meta: { request_id: "req_1" },
        },
      },
    });
    renderConsole();
    await clickStart();

    await waitFor(() => expect(screen.getByText(/agent speaking/i)).toBeInTheDocument());
    // The greeting is a playable URL, so playGreetingThenListen must not
    // have fallen back to arming the mic immediately.
    expect(FakeMediaRecorder.instances.length).toBe(0);
    expect(screen.queryByText(/^listening$/i)).not.toBeInTheDocument();
  });

  it("automatically starts listening as soon as the greeting audio finishes - no button press", async () => {
    mockFetch({
      createSession: {
        status: 201,
        body: {
          data: {
            session_id: "sess-greet-2", conversation_id: "conv-greet-2", status: "connecting", language: "en",
            provider: "mock", server_url: null, connection_token: "tok", connection_expires_at: "2026-01-01T00:00:00Z",
            ice_servers: [],
            greeting: {
              text: "Hi, I'm the voice admissions assistant. How can I help you today?",
              audio_url: "https://cdn.example.com/greeting.mp3",
              audio_duration_ms: 3000,
            },
          },
          meta: { request_id: "req_1" },
        },
      },
    });
    renderConsole();
    await clickStart();

    await waitFor(() => expect(screen.getByText(/agent speaking/i)).toBeInTheDocument());
    expect(FakeMediaRecorder.instances.length).toBe(0);

    const audioEl = document.querySelector("audio")!;
    fireEvent.ended(audioEl);

    await waitFor(() => expect(FakeMediaRecorder.instances.length).toBe(1));
    expect(screen.getByText(/^listening$/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /start voice session/i })).not.toBeInTheDocument();
  });

  it("falls back to listening immediately if the greeting audio fails to play", async () => {
    window.HTMLMediaElement.prototype.play = vi.fn().mockRejectedValue(new Error("playback blocked"));
    mockFetch({
      createSession: {
        status: 201,
        body: {
          data: {
            session_id: "sess-greet-3", conversation_id: "conv-greet-3", status: "connecting", language: "en",
            provider: "mock", server_url: null, connection_token: "tok", connection_expires_at: "2026-01-01T00:00:00Z",
            ice_servers: [],
            greeting: {
              text: "Hi, I'm the voice admissions assistant. How can I help you today?",
              audio_url: "https://cdn.example.com/greeting.mp3",
              audio_duration_ms: 3000,
            },
          },
          meta: { request_id: "req_1" },
        },
      },
    });
    renderConsole();
    await clickStart();

    await waitFor(() => expect(FakeMediaRecorder.instances.length).toBe(1));
    expect(screen.getByText(/^listening$/i)).toBeInTheDocument();
  });

  it("falls back to listening immediately when there is no playable greeting audio (e.g. mock TTS)", async () => {
    // mockFetch's default greeting() uses a non-playable "mock://tts/..." URL.
    mockFetch({});
    renderConsole();
    await clickStart();

    await waitFor(() => expect(FakeMediaRecorder.instances.length).toBe(1));
    expect(screen.getByText(/^listening$/i)).toBeInTheDocument();
  });

  // ---------------------------------------------------------------------
  // Session lifecycle recovery: a transient failure during an ongoing
  // conversation must never force the whole session back to the "Start
  // voice session" screen - only an explicit "End session" click or a
  // genuinely unrecoverable condition (the session itself is gone) may
  // do that. See voice-console.tsx's noteTurnFailure/noteTurnSuccess/
  // isUnrecoverableTurnError/handleMicTrackEnded.
  // ---------------------------------------------------------------------

  it("recovers from a transient API failure during a spoken turn - stays connected and automatically listens again", async () => {
    mockFetch({
      events: [
        { status: 500, body: { error: { code: "INTERNAL", message: "Temporary backend hiccup" } } },
        { status: 200, body: { data: { response_text: "The current tuition fee is 1,50,000." }, meta: { request_id: "req_1" } } },
      ],
    });
    renderConsole();
    await clickStart();
    await waitFor(() => expect(FakeMediaRecorder.instances.length).toBe(1));

    await act(async () => {
      micIsLoud = true;
      await new Promise((resolve) => setTimeout(resolve, 150));
      micIsLoud = false;
    });

    // The turn failed - the session must stay connected (no reversion to
    // the start screen) and automatically re-arm listening for a retry.
    await waitFor(() => expect(screen.getByText(/temporary backend hiccup/i)).toBeInTheDocument(), { timeout: 2500 });
    expect(screen.queryByRole("button", { name: /start voice session/i })).not.toBeInTheDocument();
    await waitFor(() => expect(FakeMediaRecorder.instances.length).toBe(2));
    expect(screen.getByText(/^listening$/i)).toBeInTheDocument();
  }, 10000);

  it("gives up on automatic listening after repeated consecutive failures, without ending the session", async () => {
    mockFetch({
      events: [
        { status: 500, body: { error: { code: "INTERNAL", message: "boom" } } },
        { status: 500, body: { error: { code: "INTERNAL", message: "boom" } } },
        { status: 500, body: { error: { code: "INTERNAL", message: "boom" } } },
      ],
    });
    renderConsole();
    await clickStart();

    const input = await screen.findByLabelText(/transcript input/i);
    for (let i = 0; i < 3; i += 1) {
      await userEvent.type(input, `message ${i}`);
      await userEvent.click(screen.getByRole("button", { name: /send/i }));
      await waitFor(() => expect(screen.getByText(/boom/i)).toBeInTheDocument());
    }

    expect(await screen.findByText(/automatic listening has been paused/i)).toBeInTheDocument();
    // The session itself is untouched - still connected, typed composer
    // and End session both remain usable.
    expect(screen.queryByRole("button", { name: /start voice session/i })).not.toBeInTheDocument();
    expect(screen.getByLabelText(/transcript input/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /end session/i })).toBeInTheDocument();
  });

  it("recovers automatically when the MediaRecorder itself errors mid-turn", async () => {
    mockFetch({});
    renderConsole();
    await clickStart();
    await waitFor(() => expect(FakeMediaRecorder.instances.length).toBe(1));

    const firstRecorder = FakeMediaRecorder.instances[0];
    act(() => firstRecorder.onerror?.(new Event("error")));

    // A fresh recorder is armed automatically - the session stays connected.
    await waitFor(() => expect(FakeMediaRecorder.instances.length).toBe(2));
    expect(screen.queryByRole("button", { name: /start voice session/i })).not.toBeInTheDocument();
    expect(screen.getByText(/^listening$/i)).toBeInTheDocument();
  });

  it("degrades to typed-only when the microphone track ends, without ending the session", async () => {
    const fakeTrack: { onended: (() => void) | null } = { onended: null };
    vi.stubGlobal("navigator", {
      ...navigator,
      mediaDevices: {
        getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [fakeTrack] } as unknown as MediaStream),
      },
    });
    mockFetch({});
    renderConsole();
    await clickStart();
    await waitFor(() => expect(FakeMediaRecorder.instances.length).toBe(1));

    act(() => fakeTrack.onended?.());

    await waitFor(() => expect(screen.getByText(/microphone disconnected/i)).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: /start voice session/i })).not.toBeInTheDocument();
    expect(screen.getByLabelText(/transcript input/i)).toBeInTheDocument();
    // No further (pointless) listening attempts against the dead stream.
    expect(FakeMediaRecorder.instances.length).toBe(1);
  });

  it("ends the session when the backend reports it as genuinely gone (404) - the one unrecoverable case", async () => {
    mockFetch({
      events: [{ status: 404, body: { error: { code: "NOT_FOUND", message: "Voice session not found." } } }],
    });
    renderConsole();
    await clickStart();

    const input = await screen.findByLabelText(/transcript input/i);
    await userEvent.type(input, "hello");
    await userEvent.click(screen.getByRole("button", { name: /send/i }));

    expect(await screen.findByText(/voice session not found/i)).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /start voice session/i })).toBeInTheDocument();
  });

  // ---------------------------------------------------------------------
  // Root cause coverage: the backend's idle-timeout/max-duration check
  // (VoiceSessionService.record_event()) can legitimately end a session
  // on ANY event, including the "interruption" event this console sends
  // before a new turn. Before this fix, that response was thrown away
  // unread, so the console went on to send the turn's real event anyway,
  // which then 409'd against the now-ended session - a confusing failure
  // that (pre-fix) wasn't even recognized as unrecoverable.
  // ---------------------------------------------------------------------

  it("ends the session cleanly when the backend ends it on the interruption event itself - no confusing follow-up request", async () => {
    const fetchImpl = mockFetch({
      events: [
        { status: 200, body: { data: { response_text: "Long answer playing back...", audio_url: "https://cdn.example.com/a.mp3" }, meta: { request_id: "req_1" } } },
        { status: 200, body: { data: { status: "completed", response_text: "Are you still there? This session has ended due to inactivity." }, meta: { request_id: "req_1" } } },
      ],
    });
    renderConsole();
    await clickStart();

    const input = await screen.findByLabelText(/transcript input/i);
    await userEvent.type(input, "Tell me about admissions.");
    await userEvent.click(screen.getByRole("button", { name: /send/i }));
    await screen.findByText("Long answer playing back...");
    await waitFor(() => expect(screen.getByText(/agent speaking/i)).toBeInTheDocument());

    // A second turn while the agent is still "speaking" triggers the
    // interruption event first - the backend's idle-timeout check fires
    // on THAT request in this test.
    await userEvent.type(input, "Wait, I have another question.");
    await userEvent.click(screen.getByRole("button", { name: /send/i }));

    expect(await screen.findByText(/ended due to inactivity/i)).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /start voice session/i })).toBeInTheDocument();

    // Exactly 2 /events calls: turn 1's final_transcript, then the
    // interruption that ended the session - never a 3rd, doomed request
    // for "Wait, I have another question."
    const eventCalls = fetchImpl.mock.calls.filter(([reqInput]) => String(reqInput).includes("/events"));
    expect(eventCalls).toHaveLength(2);
  });

  it("ends the session (does not endlessly retry) when the backend rejects an event with 409 because it already ended", async () => {
    mockFetch({
      events: [{ status: 409, body: { error: { code: "VOICE_SESSION_ENDED", message: "This voice session has already ended." } } }],
    });
    renderConsole();
    await clickStart();

    const input = await screen.findByLabelText(/transcript input/i);
    await userEvent.type(input, "hello");
    await userEvent.click(screen.getByRole("button", { name: /send/i }));

    expect(await screen.findByText(/voice session has already ended/i)).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /start voice session/i })).toBeInTheDocument();
  });
});

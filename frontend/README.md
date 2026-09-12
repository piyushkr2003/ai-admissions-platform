# AI Admissions Platform — Admin Dashboard

Next.js (App Router) admin dashboard for the multi-tenant AI admissions platform. It is a pure API
consumer of the FastAPI backend (`docs/api-contract.md`) — it holds no college-specific data or
business logic of its own.

## Setup

```bash
npm install
cp .env.example .env.local   # then edit NEXT_PUBLIC_API_BASE_URL if needed
npm run dev                  # http://localhost:3000
```

Requires the backend (`backend/`) running separately and reachable at the configured API base URL.

## Environment variables

| Variable | Purpose |
| --- | --- |
| `NEXT_PUBLIC_API_BASE_URL` | Base URL of the backend API, e.g. `http://localhost:8000/api/v1`. This is the only environment variable the frontend reads. |

Only `NEXT_PUBLIC_*` variables that are safe to ship to the browser belong here. Backend secrets
(database credentials, provider API keys, JWT signing secrets) must never be added as
`NEXT_PUBLIC_*` variables — they belong exclusively to `backend/.env`.

## Authentication

- Login posts to `/auth/login`; the returned access/refresh tokens and user are kept in
  `sessionStorage` (cleared on tab close, never `localStorage`) via `lib/session/session-store.ts`.
- On load, `AuthProvider` (`features/auth/auth-provider.tsx`) restores the session via `/auth/me`,
  transparently refreshing through `/auth/refresh` if the stored session has expired.
- Every subsequent request goes through `ApiClient` (`lib/api/client.ts`), which attaches the
  bearer token and a per-request `X-Request-ID`. A `401` from any non-auth endpoint (token expired
  or revoked mid-session) immediately clears the session, and `AuthGuard` redirects to `/login`.
- Route protection (`AuthGuard`) and navigation/action visibility (`lib/rbac.ts`) are UX-only. The
  backend (`backend/app/auth/permissions.py`) is the sole authorization boundary — every list/action
  page still reflects a `403` from the API as an honest "unavailable" state rather than assuming the
  frontend check was sufficient.

## Tenant context

`features/tenant/tenant-provider.tsx` resolves the active college:

- `college_admin` / `admissions_staff` / `counselor` are locked to their own `user.college_id`.
- `platform_admin` (no home college) gets a college switcher in the sidebar, backed by `GET
  /colleges`; the selection is remembered per-browser in `sessionStorage` and sent as `?college_id=`
  on every tenant-scoped request, as required by `resolve_tenant_college_id` on the backend.

A client-supplied `college_id` is never trusted as authorization by itself — the backend
independently re-derives and checks it for every request.

## Commands

```bash
npm run dev         # start the dev server
npm run typecheck   # tsc --noEmit
npm test            # vitest run (unit/component tests)
npm run test:watch  # vitest watch mode
npm run build        # production build (next build)
npm start            # serve the production build
```

## Voice UI limitations

Task 011 ships a provider-neutral voice backend, but this environment's providers
(`stt_provider`, `tts_provider`, `voice_transport_provider`, `telephony_provider`) all default to
`mock`. The dashboard reflects this honestly:

- **Voice Monitoring** (`/dashboard/voice`) lists real `voice_sessions` rows and labels a session's
  provider as "Mock (simulated)" when applicable, instead of implying a live vendor is connected.
- No browser microphone/WebRTC capture is wired up yet — that requires a real realtime transport
  provider. The session lifecycle (create → connect → speak → end) and its admin visibility are
  real and functional against the mock provider; only the live audio path is not yet connected.
- **Conversations** (`/dashboard/conversations`) shows conversations that originated as voice
  sessions, since that is the only tenant-scoped, permission-checked way the backend currently
  exposes conversation history to staff. There is no backend endpoint yet for listing every
  text-channel conversation; the page says so rather than fabricating one.

## Known backend gaps this frontend adapts to

`docs/api-contract.md` documents a few endpoints that are not yet mounted in
`backend/app/api/v1/router.py`: `/dashboard/overview`, `/analytics/*`, and REST listing for
`courses`/`scholarships`/`faqs`. Rather than call routes that would always 404:

- **Overview** and **Analytics** are composed client-side from real, tenant-scoped counts (`meta.total`)
  returned by the leads/appointments/applications/support-tickets/voice-sessions list endpoints. A
  section whose underlying call fails (e.g. a missing permission) degrades to "unavailable"
  independently of the others — it is never backfilled with a fabricated number.
- There is no course/scholarship/FAQ picker anywhere in the dashboard, since there is no way to
  list them through the API yet; course/scholarship names already embedded in lead/appointment/
  application responses are shown as read-only text.

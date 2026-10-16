# @chattie/web

Chat UI for the Chattie API (`services/llm`). Next.js 16 (App Router, Cache Components) + Vercel AI SDK v7 (`useChat`) + shadcn/ui primitives. Markdown streaming via `streamdown`, auto-scroll via `use-stick-to-bottom`.

## Run

From the repo root (npm workspaces):

```bash
make web-install   # npm install
make dev-stack     # API on :8000 (+ Langfuse on :3000)
make web           # UI on http://localhost:3001
```

`NEXT_PUBLIC_API_URL` in `.env.local` points at the API (see `.env.example`). The API must list `http://localhost:3001` in its `CORS_ORIGINS`.

Open the app at `http://localhost:3001` or `http://127.0.0.1:3001`. Any other host (e.g. the LAN "Network" URL `next dev` prints) must be added to both `allowedDevOrigins` in `next.config.ts` (otherwise the dev server blocks its JS and no button works) and the API's `CORS_ORIGINS`.

## How it works

- **Auth** (Better Auth, `lib/auth.ts`): email + password; users/sessions in the `auth` schema of the `chattie` DB (`make web-migrate`). `proxy.ts` sends visitors without a session cookie to `/sign-in` (an optimistic check); the real check is the server-only data access layer `lib/session.ts`. Calls to the API carry a short-lived JWT (`lib/api/server.ts` on the server, `lib/api/client.ts` in the browser) that the API verifies via `/api/auth/jwks`.

- `/` redirects (in `proxy.ts`) to `/chat/<uuid>`; "New chat" navigates there directly. The uuid (`lib/routes.ts`) is the LangGraph thread id.
- `app/chat/[id]/page.tsx` loads the stored thread on the server (`GET /threads/{id}/messages`) and hands it to the `Chat` client component.
- `useChat` sends only the newest message to `POST /chat` and renders the streamed reply: text and tool calls, the latter as collapsible tool cards.
- **Data fetching** (TanStack Query, `components/providers/query-provider.tsx`, `lib/query-client.ts`): the sidebar's thread list is the `["threads"]` query (`hooks/use-threads.ts`), seeded on the server via `HydrationBoundary` and invalidated exactly when it can change — a reply finishes (`use-chat-session.ts`) or "New chat" (`use-new-chat.ts`). Sign-in/up and sign-out are mutations (`use-auth-form.ts`, `use-sign-out.ts`) that clear the cache; sign-out also does a full page load so no previous user's page stays mounted. Any API 401 sends the user to `/sign-in`. The chat stream itself stays with the AI SDK's `useChat`.
- With Cache Components, Next keeps up to 3 visited pages mounted but hidden (React `<Activity>`), so switching between recent chats keeps drafts and scroll position.

## Code layout

| Path | What |
|---|---|
| `components/chat/` | Chat UI components (rendering only) |
| `components/sidebar/` | Thread history: `SidebarContent` is rendered by the desktop sidebar (md+) and inside the mobile drawer (`MobileNav`, shadcn Sheet) |
| `components/ui/` | shadcn/ui primitives in use (button, collapsible, textarea); add more with `npx shadcn@latest add <name>` |
| `hooks/` | React hooks: chat session (`useChat` + transport), prompt input |
| `types/` | Shared TypeScript types, including component props |
| `lib/tool-status.ts` | Maps a tool call's state to running / done / error |
| `lib/api/server.ts`, `lib/api/client.ts` | API client: server-side reads (threads, history) / browser chat transport, both sending the user's JWT |
| `lib/auth.ts`, `lib/auth-client.ts`, `lib/session.ts` | Better Auth server config, browser client, server-only session access |
| `app/(auth)/`, `components/auth/` | Sign-in / sign-up pages and form |
| `lib/env.ts` | Environment validation (zod) |

## Conventions

- `.tsx` files hold UI only and stay under 150 lines; hooks live in `hooks/`, types in `types/`.

## Checks

```bash
npx tsc --noEmit && npm run lint   # or: make web-lint
npm run build
```

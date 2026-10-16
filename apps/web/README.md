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

- `/` redirects (in `proxy.ts`) to `/chat/<uuid>`; "New chat" navigates there directly. The uuid (`lib/routes.ts`) is the LangGraph thread id.
- `app/chat/[id]/page.tsx` loads the stored thread on the server (`GET /threads/{id}/messages`) and hands it to the `Chat` client component.
- `useChat` sends only the newest message to `POST /chat` and renders the streamed reply: text and tool calls, the latter as collapsible tool cards.
- The sidebar (`components/sidebar/`, rendered by the root layout) lists `GET /threads`; after each reply and on "New chat" (`hooks/use-new-chat.ts`), `router.refresh()` re-fetches it — the root layout isn't re-rendered by plain navigation.
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
| `lib/api.ts` | API client: thread history + chat transport |
| `lib/env.ts` | Environment validation (zod) |

## Conventions

- `.tsx` files hold UI only and stay under 150 lines; hooks live in `hooks/`, types in `types/`.

## Checks

```bash
npx tsc --noEmit && npm run lint   # or: make web-lint
npm run build
```

# Chattie

A minimal FastAPI service that fronts an LLM (via OpenRouter + `langchain-openai`) with a Langfuse-instrumented pipeline. Ships with a local Docker Compose stack that can boot a self-hosted Langfuse v3 alongside the app.

## Architecture

```mermaid
flowchart TB
    %% ─── Top: UI → Edge → (Auth / API) ──────────────────────────
    UI["User interface"] --> Edge["Edge layer"]
    Edge --> Auth["Authentication"]
    Edge --> API["API"]
    API --> Orch

    %% ─── Middle row: three columns side-by-side ────────────────
    subgraph MID [" "]
        direction LR

        subgraph LCOL [" "]
            direction TB
            Authz["Authorization"]
            Cost["Cost Tracker"]
            Obs["Observability<br/>Prompts / hardware"]
        end

        subgraph Orch["Agent orchestrator"]
            direction LR
            A1["Agent01"]
            A2["Agent02"]
            A3["Agent03"]
        end

        subgraph RCOL [" "]
            direction TB
            PII["PII"]
            LLM["LLM"]
            Eval["Evaluation"]
            SessionDB[("Session db")]
        end
    end

    %% ─── Sidecar wiring from orchestrator ──────────────────────
    Orch --> Authz
    Orch --> Cost
    Orch --> Obs
    Orch --> PII
    Orch --> LLM
    Orch --> Eval
    Orch --> SessionDB

    %% ─── Below: each agent → its MCP → its Tools ───────────────
    A1 --> MCP1["MCP"] --> T1["Tools"]
    A2 --> MCP2["MCP"] --> T2["Tools"]
    A3 --> MCP3["MCP"] --> T3["Tools"]

    %% ─── Palette: pastel blue for infra, pastel mint for compute
    classDef infra   fill:#BFDBFE,stroke:#1E40AF,color:#0F172A,stroke-width:1.5px
    classDef compute fill:#A7F3D0,stroke:#047857,color:#064E3B,stroke-width:1.5px
    classDef store   fill:#A7F3D0,stroke:#047857,color:#064E3B,stroke-width:1.5px
    classDef group   fill:#FFFFFF,stroke:#CBD5E1,color:#334155,stroke-dasharray:4 3

    class UI,Edge,Auth,API,PII,Authz,Cost,Obs,Eval infra
    class A1,A2,A3,MCP1,MCP2,MCP3,T1,T2,T3,LLM compute
    class SessionDB store
    class MID,LCOL,RCOL,Orch group
```

### What exists today vs. planned

| Box | Status | Where it lives |
|---|---|---|
| User interface | **Implemented** (Next.js 16 + AI SDK v7 + shadcn/ui, streams from `POST /chat`) | `apps/web/` |
| Edge layer | Planned (reverse proxy / rate limit / WAF) | — |
| Authentication | **Implemented** — email + password via Better Auth in the web app; its JWT plugin signs short-lived EdDSA tokens that the API verifies against `/api/auth/jwks` | `apps/web/lib/auth.ts`, `services/llm/core_llm/auth.py` |
| API | **Implemented** | `services/llm/app.py`, FastAPI |
| Agent orchestrator (Agent01/02/03) | **Implemented (router + 3 specialists)**: an LLM router classifies each message (structured output, sees recent turns for follow-ups) and hands it to `general` (date, weather, web search), `company` (read-only company SQL) or `other` (no tools: unclear or out-of-scope requests). Each specialist has its own prompt and tools | `services/llm/core_llm/graph.py`, `router.py`, `agents.py` |
| MCP + Tools | Partial — local LangChain tools, no API keys needed: `get_current_datetime`, `get_weather` (Open-Meteo), `web_search` (DuckDuckGo via `ddgs`); MCP planned | `services/llm/core_llm/tools/` |
| LLM | **Implemented** (OpenRouter via `langchain-openai`) | `services/llm/core_llm/builder.py` |
| Session db | **Implemented** — the graph is compiled with LangGraph's `AsyncPostgresSaver` (database `chattie` on a Postgres running on the host machine); `session_id` is the `thread_id`, so `/query` is multi-turn per session and history survives restarts. A small `chat_threads` table (title, timestamps) indexes threads for the UI sidebar. | `services/llm/core_llm/builder.py` |
| Observability | **Implemented** (Langfuse client wired in `lifespan`) | `services/llm/app.py`, `services/llm/ops/health.py` |
| Cost Tracker | Partial — Langfuse captures token/cost, no dedicated tracker | via Langfuse |
| Evaluation | Planned (Langfuse Datasets/Scores or local harness) | — |
| PII redaction | Planned | — |
| Authorization | Partial — every API route except `/health` requires a valid token; threads are owned by their user (others get 404). Company data is protected by Postgres row-level security per user/role (employee, manager, hr, admin). Per-agent / per-tool policy planned | `services/llm/core_llm/threads.py`, `services/llm/db/company/schema.sql` |

## Layout

```
services/
  llm/                        the FastAPI chat service
    app.py                    entrypoint + lifespan wiring
    config.py                 Pydantic settings (loaded from root .env)
    core_llm/
      builder.py              build_llm / build_memory
      graph.py                LangGraph StateGraph: router → general | company | other
      router.py               router node: structured-output route decision (falls back to general)
      agents.py               specialist agent nodes, each with its own tool loop
      tools/                  LangChain tools exposed to the agent (TOOLS list in __init__.py)
        clock.py              get_current_datetime
        weather.py            get_weather (Open-Meteo)
        search.py             web_search (DuckDuckGo via ddgs)
        company_sql.py        query_company_data: read-only SQL over the company schema, as the signed-in user
      prompt.py               system prompts: router + one per specialist
      routes.py               POST /query (single JSON reply)
      chat.py                 POST /chat (streaming), GET /threads, GET /threads/{id}/messages
      threads.py              chat_threads table: thread titles + timestamps for the sidebar
      ui_stream.py            LangGraph → AI SDK UI message stream (SSE) + history conversion
      tracing.py              shared run config: thread id + Langfuse callback/metadata
    ops/
      health.py               /health probe (LLM + Langfuse)
    db/company/
      schema.sql              company schema: tables, row-level security, views, query-role grants
      setup.py                creates the read-only role, applies schema.sql, seeds data, links personas
    Dockerfile                multi-stage, python:3.12-slim
    requirements.txt
apps/
  web/                        Next.js chat UI (port 3001)
    app/chat/[id]/            one page per thread; history loaded on the server
    components/chat/          chat UI components (rendering only, ≤150 lines each)
    components/sidebar/       thread history sidebar + New chat button
    components/ui/            shadcn/ui primitives in use
    hooks/                    React hooks (chat session, prompt input)
    types/                    shared TypeScript types
    lib/                      env validation, API client + chat transport
    proxy.ts                  `/` → `/chat/<new uuid>`
packages/                     placeholder — shared contracts (OpenAPI → TS)
docker-compose.yml            profiles: prod | dev | langfuse
Makefile                      convenience targets
package.json                  npm workspaces root (apps/*, packages/*)
.env                          loaded by docker-compose
```

## Requirements

- Docker Desktop (or Docker Engine) with Compose v2
- Python 3.12 (only if you want to run outside containers)
- Node.js 20+ and npm (for the web UI)
- A `.env` file (see below)

## Configuration

`config.py` reads these from the environment or `./.env`:

| Variable | Purpose |
|---|---|
| `OPENROUTER_API_KEY` | OpenRouter credential used by `langchain-openai` |
| `LLM_BASE_URL` | OpenRouter-compatible base URL (default: `https://openrouter.ai/api/v1`) |
| `LLM_MODEL` | Model identifier (e.g. `openai/gpt-4o-mini`) |
| `LLM_TEMPERATURE` | Float, e.g. `0` |
| `LANGFUSE_PUBLIC_KEY` | Langfuse project public key (`pk-lf-…`) |
| `LANGFUSE_SECRET_KEY` | Langfuse project secret key (`sk-lf-…`) |
| `LANGFUSE_BASE_URL` | Langfuse host URL |
| `DB_HOST` / `DB_PORT` | Host Postgres for chat history (default `localhost` / `5432`) |
| `DOCKER_DB_HOST` | `DB_HOST` to use inside Docker containers (required by Compose; normally `host.docker.internal`) |
| `DB_USER` / `DB_PASSWORD` | Credentials for that Postgres |
| `DB_NAME` | Database for the LangGraph checkpointer (default `chattie`; must already exist) |
| `CORS_ORIGINS` | JSON list of browser origins allowed to call the API, e.g. `["http://localhost:3001"]` |
| `QUERY_DB_USER` / `QUERY_DB_PASSWORD` | Read-only Postgres role used by the company SQL tool (default user `chattie_query`; created by `make company-db`) |
| `AUTH_JWKS_URL` | Web app's public signing keys, `http://localhost:3001/api/auth/jwks` |
| `DOCKER_AUTH_JWKS_URL` | `AUTH_JWKS_URL` to use inside Docker (normally `http://host.docker.internal:3001/api/auth/jwks`) |
| `AUTH_ISSUER` / `AUTH_AUDIENCE` | Expected JWT `iss` / `aud`: the web app's `BETTER_AUTH_URL` (`http://localhost:3001`) |

The web UI reads `NEXT_PUBLIC_API_URL` (the API base URL, default `http://localhost:8000`) from `apps/web/.env.local`; see `apps/web/.env.example`.

When you run through Compose, `LANGFUSE_BASE_URL` is **overridden to `http://langfuse-web:3000`** so the chattie container can reach the in-network Langfuse service. The value in `.env` only matters when running outside Docker. Likewise, inside containers `DB_HOST` is **replaced by `DOCKER_DB_HOST`** from `.env` (normally `host.docker.internal`) so the container reaches the Postgres on your machine; the other `DB_*` values are used as-is in both modes.

## Running

### Option A — Docker (recommended)

The Makefile wraps the common flows:

```bash
make build       # build the chattie image
make prod        # chattie only, uvicorn (no reload) on :8000
make dev         # chattie only, uvicorn --reload with source bind-mounted
make stack       # chattie (prod) + full Langfuse stack
make dev-stack   # chattie (dev)  + full Langfuse stack
make down        # stop everything (keeps volumes)
make clean       # stop + delete all volumes (destructive)
make logs        # tail logs
make health      # curl /health and pretty-print
make shell       # bash into the running chattie container
```

Under the hood these are just `docker compose --profile <...> up` commands. Three profiles are defined:

- `prod` — `chattie` service, no reload
- `dev`  — `chattie-dev` service, `--reload`, source mounted at `/app`
- `langfuse` — the self-hosted Langfuse v3 stack: `langfuse-web`, `langfuse-worker`, `postgres`, `clickhouse`, `redis`, `minio`

Mix profiles freely:

```bash
docker compose --profile dev --profile langfuse up
```

### Option B — Local Python

```bash
cd services/llm
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload
```

Both Docker and local runs need the host Postgres from `DB_*` to be running, with the `DB_NAME` database created. The checkpointer creates its own tables on startup. With Homebrew: `brew services start postgresql@15`, then `createdb chattie`.

## Web UI

Ports on this machine: **3000** Langfuse · **3001** web UI · **8000** API · **5432** Postgres · **9090/9091** MinIO.

```bash
make web-install   # once: npm install at the repo root (workspaces)
psql -d chattie -c 'CREATE SCHEMA IF NOT EXISTS auth'   # once
make web-migrate   # once (and after auth upgrades): Better Auth tables
make dev-stack     # terminal 1: API on :8000 + Langfuse on :3000
make web           # terminal 2: UI on http://localhost:3001
make web-lint      # type-check + Biome
```

Sign up at `/sign-up` (email + password). The **first** account also takes ownership of chats created before sign-in existed. The API trusts only tokens signed by the web app, so the web app must be running for the API to accept requests.

Opening `/` starts a new thread at `/chat/<uuid>`; that id is the LangGraph `thread_id` and the Langfuse session, so reloading the page restores the conversation. The browser sends only the newest message to `POST /chat`, which streams back the [AI SDK UI message stream protocol](https://ai-sdk.dev/docs/ai-sdk-ui/stream-protocol) — text deltas plus tool calls/results, rendered as tool cards.

## Company data (SQL tool)

The agent's `query_company_data` tool runs model-written, read-only SQL over sample business data in the `company` schema (departments, employees, salaries, customers, products, orders).

```bash
make company-db                                         # (re)create schema, read-only role and data
make company-link EMAIL=you@example.com ROLE=manager    # act as a persona: employee | manager | hr | admin
```

Authorization is enforced by Postgres, not by the model. The tool connects as `chattie_query` (SELECT-only, no other roles), runs each query in a read-only transaction with a 5 s timeout, and sets `app.user_id` to the verified JWT subject; row-level security policies filter every table by it. Model SQL is wrapped as a subquery (one SELECT only, no `SET`), and `set_config()` is revoked so the identity can't be changed from a query. Salaries are column-protected and only readable through `company.employee_salaries`.

| Role | Employee directory | Salaries | Customers & orders |
|---|---|---|---|
| employee | everyone | own | own |
| manager | everyone | own | own + team |
| hr | everyone | all | own |
| admin | everyone | all | all |
| not linked | none | none | none (departments and products only) |

The directory (name, title, role, department, manager) is company-wide so counts like "how many HR people" are correct for everyone. For restricted data, every tool result carries the user's scope (`company.my_access`) and a `scope_note` when the query touched partially visible data, so the agent says e.g. "your team had 9 orders; the company-wide total isn't available to you" instead of presenting a partial number as a company total.

`make company-db` recreates the schema, which drops persona links; re-run `make company-link` afterwards.

## First boot with Langfuse

The compose file seeds the Langfuse database using `LANGFUSE_INIT_*` variables so the keys in your `.env` work on first run:

- An org/project named **chattie** is created.
- The project public/secret keys are set to whatever is in your `.env`.
- An admin user `admin@langfuse.local` / `ChangeMe123!` is created so you can sign in to the Langfuse UI at <http://localhost:3000>.

After the first successful boot the seeding env vars are idempotent — leaving them in place is fine, but you can also strip them and manage keys through the UI.

## Health check

```bash
curl -s http://localhost:8000/health | python3 -m json.tool
```

Returns `200` when both the LLM `/models` probe and the Langfuse `auth_check` succeed; otherwise `503` with per-service detail.

## Security notes

- `docker-compose.yml` ships with **development-only** values for `SALT`, `ENCRYPTION_KEY`, `NEXTAUTH_SECRET`, Postgres/MinIO/Redis passwords, and the Langfuse admin password. Rotate every one of these before exposing the stack beyond localhost.
- `.env` is in `.gitignore`. If you ever commit it by accident, rotate every key in it — treat anything that touched a repo as leaked.
- Clickhouse/MinIO/Postgres/Redis are not exposed to the host network (only MinIO's console on `:9091`). The only publicly bound ports are `8000` (chattie) and `3000` (Langfuse UI); the web UI dev server adds `3001`.

## Common issues

- **`host.docker.internal` doesn't resolve** — only an issue when running outside the compose network. Inside compose, chattie talks to `langfuse-web` by service name.
- **Langfuse keys don't authenticate** — the seeded project uses the keys from your `.env`. If you changed `.env` after first boot, either reset with `make clean` (nukes volumes) or regenerate keys in the Langfuse UI and sync them back to `.env`.
- **`AttributeError` on `/health`** — if you edited `services/llm/ops/health.py` and introduced lowercase attribute access on `Settings`, remember the fields are uppercase (`settings.LLM_BASE_URL`, not `settings.llm_base_url`).

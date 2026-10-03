import asyncio
import logging

import httpx
from fastapi import APIRouter, Request, Response, status

from config import Settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["ops"])
_PROBE_TIMEOUT_S = 2.0

async def _get(client: httpx.AsyncClient, url: str, **kwargs) -> dict:
    r = await client.get(url, timeout=_PROBE_TIMEOUT_S, **kwargs)
    r.raise_for_status()
    return {"ok": True}


async def _check_llm(client: httpx.AsyncClient, settings: Settings) -> dict:
    try:
        return await _get(
            client,
            settings.LLM_BASE_URL.rstrip("/") + "/models",
            headers={"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}"},
        )
    except Exception as exc:
        return {"ok": False, "detail": f"{type(exc).__name__}: {exc}"}


async def _check_langfuse(request: Request) -> dict:
    lf = getattr(request.app.state, "langfuse", None)
    if lf is None:
        return {"ok": False, "detail": "client not initialized"}
    try:
        ok = await asyncio.to_thread(lf.auth_check)
        return {"ok": bool(ok)} if ok else {"ok": False, "detail": "auth_check returned False"}
    except Exception as exc:
        return {"ok": False, "detail": f"{type(exc).__name__}: {exc}"}


@router.get("/health", summary="Health Check", response_model=dict)
async def health(request: Request, response: Response) -> dict:
    settings: Settings = request.app.state.settings

    async with httpx.AsyncClient() as client:
        llm, langfuse = await asyncio.gather(
            _check_llm(client, settings),
            _check_langfuse(request),
        )

    services = {
        "llm": llm,
        "langfuse": langfuse,
    }
    ok = all(s["ok"] for s in services.values())
    if not ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"ok": ok, "services": services}
import asyncio
import logging

from ddgs import DDGS
from ddgs.exceptions import DDGSException
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

MAX_RESULTS = 5
TIMEOUT_S = 10
SNIPPET_CHARS = 300


def _search(query: str) -> list[dict]:
    return DDGS(timeout=TIMEOUT_S).text(query, max_results=MAX_RESULTS)


@tool
async def web_search(query: str) -> str:
    """Search the web for up-to-date information: news, recent events, facts, prices, docs.

    Pass a short, specific search query. Returns titles, URLs and snippets; cite the URLs you use.
    """
    try:
        # ddgs is synchronous; run it off the event loop.
        results = await asyncio.to_thread(_search, query)
    except DDGSException as exc:
        logger.warning("web search failed for %r: %s", query, exc)
        return f"Web search failed or found nothing for '{query}'. Try a different query."

    if not results:
        return f"No web results for '{query}'."
    return "\n\n".join(
        f"{i}. {r.get('title', '')}\n{r.get('href', '')}\n{r.get('body', '')[:SNIPPET_CHARS]}"
        for i, r in enumerate(results, start=1)
    )

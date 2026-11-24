from core_llm.tools.clock import format_now, get_current_datetime
from core_llm.tools.weather import get_weather
from core_llm.tools.search import web_search

# Tools of the general agent. The company agent's SQL tool needs a DB pool, so the app builds it.
GENERAL_TOOLS = [get_current_datetime, get_weather, web_search]

__all__ = ["GENERAL_TOOLS", "format_now"]

from datetime import datetime

from langchain_core.tools import tool


def format_now() -> str:
    return datetime.now().astimezone().strftime("%A, %d %B %Y, %H:%M %Z")


@tool
def get_current_datetime() -> str:
    """Return the current local date, day of the week, and time."""
    return format_now()


TOOLS = [get_current_datetime]

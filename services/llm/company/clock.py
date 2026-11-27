from datetime import date, datetime
from zoneinfo import ZoneInfo

from config import Settings


def company_today(settings: Settings) -> date:
    """Today's date in the company's time zone (COMPANY_TIMEZONE, default UTC)."""
    return datetime.now(ZoneInfo(settings.COMPANY_TIMEZONE)).date()

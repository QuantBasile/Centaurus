from __future__ import annotations

from datetime import date, datetime, time

def parse_iso_date(s: str) -> date:
    try:
        return datetime.strptime(s.strip(), "%Y-%m-%d").date()
    except Exception as e:
        raise ValueError("Please enter dates as YYYY-MM-DD (e.g., 2026-01-21).") from e

def us_open_berlin(day: date) -> time:
    """US equities open at 09:30 America/New_York, converted to Europe/Berlin time (DST-aware)."""
    try:
        from zoneinfo import ZoneInfo
        ny = ZoneInfo("America/New_York")
        ber = ZoneInfo("Europe/Berlin")
        dt_ny = datetime(day.year, day.month, day.day, 9, 30, tzinfo=ny)
        dt_ber = dt_ny.astimezone(ber)
        return dt_ber.timetz().replace(tzinfo=None)
    except Exception:
        return time(15, 30)

"""Timezone utilities."""
import os
from datetime import date, datetime, time
from zoneinfo import ZoneInfo


DEFAULT_TIMEZONE = os.environ.get("DEFAULT_TIMEZONE", "Europe/Berlin")


def get_user_timezone(user_timezone: str | None) -> ZoneInfo:
    """Get ZoneInfo for user timezone, fallback to default."""
    try:
        return ZoneInfo(user_timezone or DEFAULT_TIMEZONE)
    except Exception:
        return ZoneInfo(DEFAULT_TIMEZONE)


def utc_to_local(utc_dt: datetime, tz: ZoneInfo) -> datetime:
    """Convert UTC datetime to local timezone."""
    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=ZoneInfo("UTC"))
    return utc_dt.astimezone(tz)


def get_local_date(utc_dt: datetime, tz: ZoneInfo) -> date:
    """Get local date from UTC datetime."""
    local_dt = utc_to_local(utc_dt, tz)
    return local_dt.date()


def get_local_time(utc_dt: datetime, tz: ZoneInfo) -> time:
    """Get local time from UTC datetime."""
    local_dt = utc_to_local(utc_dt, tz)
    return local_dt.time()


def is_time_in_range(current_time: time, target_time: time, window_minutes: int = 5) -> bool:
    """Check if current time is within window_minutes of target_time."""
    current_minutes = current_time.hour * 60 + current_time.minute
    target_minutes = target_time.hour * 60 + target_time.minute
    window_start = target_minutes
    window_end = target_minutes + window_minutes

    return window_start <= current_minutes < window_end


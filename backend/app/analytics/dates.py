"""Date-range resolution for analytics queries (Task 013).

Convention (documented in docs/api-contract.md's analytics section):

- All range presets are resolved in the *college's configured timezone*
  (`colleges.timezone`), not UTC and not the server/client timezone. This
  avoids off-by-one-day errors for colleges outside UTC - "today" means
  today in Pune, not today in whatever timezone the container happens to
  run in.
- A resolved range is a half-open UTC interval: [start_utc, end_utc). The
  start instant is included, the end instant is excluded. This makes
  adjacent ranges (e.g. yesterday and today) compose without double-counting
  or gaps at the boundary.
- Local calendar boundaries are converted to UTC using a timezone-aware
  `datetime` (via `zoneinfo`), so DST transitions in the college's timezone
  are handled correctly rather than assuming a fixed UTC offset.
- `custom` ranges are inclusive of both `start_date` and `end_date` as
  local calendar dates.
- A range entirely in the future is valid and simply yields zero results -
  only a malformed range (end before start, missing required fields, an
  unrecognized preset, or an excessively large span) is rejected.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.errors import ValidationAppError

DateRangePreset = Literal["today", "last_7_days", "last_30_days", "last_90_days", "custom"]

_MAX_RANGE_DAYS = 366


@dataclass(frozen=True)
class ResolvedRange:
    range: str
    timezone: str
    start_date: date
    end_date: date
    start_utc: datetime
    end_utc: datetime

    def as_meta(self) -> dict:
        return {
            "range": self.range,
            "timezone": self.timezone,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "start_utc": self.start_utc.isoformat(),
            "end_utc": self.end_utc.isoformat(),
        }


def _load_timezone(tz_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def resolve_date_range(
    *,
    range_: str,
    start_date: date | None,
    end_date: date | None,
    tz_name: str,
) -> ResolvedRange:
    tz = _load_timezone(tz_name)
    today_local = datetime.now(tz).date()

    if range_ == "today":
        local_start, local_end = today_local, today_local
    elif range_ == "last_7_days":
        local_start, local_end = today_local - timedelta(days=6), today_local
    elif range_ == "last_30_days":
        local_start, local_end = today_local - timedelta(days=29), today_local
    elif range_ == "last_90_days":
        local_start, local_end = today_local - timedelta(days=89), today_local
    elif range_ == "custom":
        if start_date is None or end_date is None:
            raise ValidationAppError("start_date and end_date are both required when range=custom.")
        local_start, local_end = start_date, end_date
    else:
        raise ValidationAppError(
            f"Unknown range '{range_}'. Expected one of: today, last_7_days, last_30_days, last_90_days, custom."
        )

    if local_end < local_start:
        raise ValidationAppError("end_date must not be before start_date.")
    if (local_end - local_start).days + 1 > _MAX_RANGE_DAYS:
        raise ValidationAppError(f"Date range cannot exceed {_MAX_RANGE_DAYS} days.")

    start_utc = datetime.combine(local_start, time.min, tzinfo=tz).astimezone(timezone.utc)
    end_utc = (datetime.combine(local_end, time.min, tzinfo=tz) + timedelta(days=1)).astimezone(timezone.utc)

    return ResolvedRange(
        range=range_, timezone=tz_name, start_date=local_start, end_date=local_end,
        start_utc=start_utc, end_utc=end_utc,
    )


def local_day_sequence(resolved: ResolvedRange) -> list[date]:
    """Every local calendar date in the range, inclusive - used to fill
    zero-count days in "over time" series so charts never show gaps."""
    days = (resolved.end_date - resolved.start_date).days
    return [resolved.start_date + timedelta(days=i) for i in range(days + 1)]

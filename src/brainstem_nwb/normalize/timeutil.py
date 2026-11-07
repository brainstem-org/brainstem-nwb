"""
Parse the date, datetime and duration strings found in a BrainSTEM project export.

The export writes values with Django's serializer and ``DjangoJSONEncoder``:

- datetimes as ISO 8601 cut to milliseconds, with UTC written as ``Z``
  (``2024-01-01T08:00:00.123Z``), which ``datetime.fromisoformat`` rejects before Python 3.11;
- dates as ``YYYY-MM-DD``;
- ``DurationField`` values (epoch start and end) with Django's ``duration_string``:
  ``"00:05:00"``, ``"01:02:03.500000"``, ``"1 02:00:00"`` and ``"-1 23:59:59"`` for negative ones.

ISO 8601 durations (``PT1H2M3.5S``, ``P1DT2H``) are accepted too, in case a later format uses them.
"""

from __future__ import annotations

import datetime as dt
import re

_DATETIME = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})[T ](?P<time>\d{2}:\d{2}(?::\d{2}(?:\.\d{1,9})?)?)"
    r"(?P<tz>Z|[+-]\d{2}:?\d{2})?$"
)
_DJANGO_DURATION = re.compile(
    r"^(?:(?P<days>-?\d+) )?(?P<sign>-?)(?P<hours>\d+):(?P<minutes>\d{1,2}):(?P<seconds>\d{1,2})"
    r"(?:\.(?P<fraction>\d{1,6}))?$"
)
_ISO_DURATION = re.compile(
    r"^(?P<sign>-)?P(?:(?P<days>\d+(?:\.\d+)?)D)?"
    r"(?:T(?:(?P<hours>\d+(?:\.\d+)?)H)?(?:(?P<minutes>\d+(?:\.\d+)?)M)?(?:(?P<seconds>\d+(?:\.\d+)?)S)?)?$"
)


def parse_datetime(value: str) -> dt.datetime:
    """Parse an export datetime into an aware datetime. Naive values are taken as UTC (the server's zone)."""
    if not isinstance(value, str):
        raise ValueError(f"expected a datetime string, got {type(value).__name__}")
    match = _DATETIME.match(value.strip())
    if not match:
        raise ValueError(f"not an ISO 8601 datetime: {value!r}")
    time = match["time"]
    if "." in time:  # fromisoformat on 3.10 accepts only 3 or 6 fraction digits
        head, fraction = time.split(".")
        time = f"{head}.{(fraction + '000000')[:6]}"
    parsed = dt.datetime.fromisoformat(f"{match['date']}T{time}")
    tz = match["tz"]
    if tz in (None, "Z"):
        return parsed.replace(tzinfo=dt.timezone.utc)
    sign = 1 if tz[0] == "+" else -1
    digits = tz[1:].replace(":", "")
    offset = dt.timedelta(hours=int(digits[:2]), minutes=int(digits[2:]))
    return parsed.replace(tzinfo=dt.timezone(sign * offset))


def parse_date(value: str) -> dt.date:
    """Parse an export date (``YYYY-MM-DD``)."""
    if not isinstance(value, str):
        raise ValueError(f"expected a date string, got {type(value).__name__}")
    return dt.date.fromisoformat(value.strip()[:10])


def parse_duration(value: str | int | float) -> dt.timedelta:
    """Parse a Django ``duration_string``, an ISO 8601 duration, or a number of seconds."""
    if isinstance(value, bool):
        raise ValueError("expected a duration, got a boolean")
    if isinstance(value, (int, float)):
        return dt.timedelta(seconds=value)
    if not isinstance(value, str):
        raise ValueError(f"expected a duration string, got {type(value).__name__}")
    text = value.strip()
    match = _DJANGO_DURATION.match(text)
    if match:
        fraction = (match["fraction"] or "").ljust(6, "0")
        clock = dt.timedelta(
            hours=int(match["hours"]),
            minutes=int(match["minutes"]),
            seconds=int(match["seconds"]),
            microseconds=int(fraction or 0),
        )
        if match["sign"] == "-":
            clock = -clock
        return dt.timedelta(days=int(match["days"] or 0)) + clock
    match = _ISO_DURATION.match(text)
    if match and any(match[part] for part in ("days", "hours", "minutes", "seconds")):
        total = dt.timedelta(
            days=float(match["days"] or 0),
            hours=float(match["hours"] or 0),
            minutes=float(match["minutes"] or 0),
            seconds=float(match["seconds"] or 0),
        )
        return -total if match["sign"] else total
    raise ValueError(f"not a duration: {value!r}")


def to_seconds(delta: dt.timedelta) -> float:
    return delta.total_seconds()


def isoformat_utc(value: dt.datetime) -> str:
    """Canonical text form for manifests: UTC, ``Z`` suffix, microseconds only when present."""
    value = value.astimezone(dt.timezone.utc)
    text = value.isoformat()
    return text.replace("+00:00", "Z")


def iso_duration_days(days: int) -> str:
    """ISO 8601 duration in whole days, as NWB and DANDI expect for subject age (``P90D``)."""
    if days < 0:
        raise ValueError("a duration in days cannot be negative")
    return f"P{days}D"

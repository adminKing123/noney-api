"""
fuse/nodes/schedule.py
======================
Schedule starter node handler + APScheduler trigger builder.

Supported ``repeat`` values
---------------------------
  none           — run once at the specified date + time (DateTrigger)
  hourly         — every hour, starting at the specified time (IntervalTrigger)
  daily          — every day at the specified time (CronTrigger)
  weekly_monday  — every Monday at the specified time (CronTrigger)
  weekdays       — Mon–Fri at the specified time (CronTrigger)
  monthly        — on the same day-of-month as the selected date (CronTrigger)
  annually       — same month + day each year (CronTrigger)

Supported ``ends`` values
-------------------------
  1y   — one year from now
  6m   — six months (~182 days) from now
  3m   — three months (~91 days) from now
  1m   — one month (~31 days) from now
  never — no end date
"""

import logging
from datetime import date, datetime, timedelta

import pytz
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .base import NodeHandler

logger = logging.getLogger(__name__)

# Map repeat enum value -> APScheduler day_of_week string
_WEEKLY_DAY_MAP: dict[str, str] = {
    "weekly_monday":    "mon",
    "weekly_tuesday":   "tue",
    "weekly_wednesday": "wed",
    "weekly_thursday":  "thu",
    "weekly_friday":    "fri",
    "weekly_saturday":  "sat",
    "weekly_sunday":    "sun",
}


# ─── Date / time parsing helpers ───────────────────────────────────────────────

def _parse_date(date_str: str) -> date:
    """
    Parse a date string into a ``datetime.date``.

    Handles:
      - ISO format "YYYY-MM-DD"
      - Relative "today"
      - Relative "next-<weekday>" (e.g. "next-monday")
    """
    today = datetime.utcnow().date()

    if not date_str or date_str.lower() == "today":
        return today

    if date_str.lower().startswith("next-"):
        day_name = date_str[5:].lower()
        day_map = {
            "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
            "friday": 4, "saturday": 5, "sunday": 6,
        }
        target = day_map.get(day_name, 0)
        days_ahead = (target - today.weekday() + 7) % 7
        if days_ahead == 0:
            days_ahead = 7  # Ensure "next-monday" never means today
        return today + timedelta(days=days_ahead)

    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        logger.warning("[FUSE] Could not parse date '%s' — defaulting to today.", date_str)
        return today


def _parse_time(time_str: str) -> tuple[int, int]:
    """
    Parse a time string into ``(hour, minute)``.

    Handles:
      - "HH:MM"
      - "+<N>min" relative offset from now
    """
    if time_str.startswith("+") and time_str.endswith("min"):
        try:
            minutes = int(time_str[1:-3])
            dt = datetime.utcnow() + timedelta(minutes=minutes)
            return dt.hour, dt.minute
        except ValueError:
            pass

    try:
        parts = time_str.split(":")
        return int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        logger.warning("[FUSE] Could not parse time '%s' — defaulting to 08:00.", time_str)
        return 8, 0


def _get_timezone(tz_name: str) -> pytz.BaseTzInfo:
    """Return a pytz timezone, falling back to UTC on error."""
    try:
        return pytz.timezone(tz_name)
    except Exception:
        logger.warning("[FUSE] Unknown timezone '%s' — falling back to UTC.", tz_name)
        return pytz.utc


# ─── Public trigger builder ────────────────────────────────────────────────────

def build_aps_trigger(config: dict):
    """
    Build an APScheduler trigger object from a schedule node config dict.

    The returned trigger can be passed directly to ``scheduler.add_job(trigger=...)``.
    """
    date_str = config.get("date", "today") or "today"
    time_str = config.get("time", "08:00") or "08:00"
    repeat   = (config.get("repeat") or "none").lower()
    tz_name  = config.get("timezone", "UTC") or "UTC"

    timezone     = _get_timezone(tz_name)
    parsed_date  = _parse_date(date_str)
    hour, minute = _parse_time(time_str)

    # ── One-time ──────────────────────────────────────────────────────────────
    if repeat == "none":
        run_at = timezone.localize(
            datetime(
                parsed_date.year, parsed_date.month, parsed_date.day,
                hour, minute, 0,
            )
        )
        return DateTrigger(run_date=run_at)

    # ── Hourly ────────────────────────────────────────────────────────────────
    if repeat == "hourly":
        start = timezone.localize(
            datetime(
                parsed_date.year, parsed_date.month, parsed_date.day,
                hour, minute, 0,
            )
        )
        return IntervalTrigger(hours=1, start_date=start, timezone=timezone)

    # ── Daily ─────────────────────────────────────────────────────────────────
    if repeat == "daily":
        return CronTrigger(hour=hour, minute=minute, timezone=timezone)

    # ── Weekly (Monday – Sunday) ──────────────────────────────────────────────
    if repeat in _WEEKLY_DAY_MAP:
        day = _WEEKLY_DAY_MAP[repeat]
        return CronTrigger(day_of_week=day, hour=hour, minute=minute, timezone=timezone)

    # ── Weekdays (Mon–Fri) ────────────────────────────────────────────────────
    if repeat == "weekdays":
        return CronTrigger(
            day_of_week="mon-fri", hour=hour, minute=minute, timezone=timezone
        )

    # ── Monthly (same day-of-month as chosen date) ────────────────────────────
    if repeat == "monthly":
        return CronTrigger(
            day=parsed_date.day, hour=hour, minute=minute, timezone=timezone
        )

    # ── Annually ──────────────────────────────────────────────────────────────
    if repeat == "annually":
        return CronTrigger(
            month=parsed_date.month,
            day=parsed_date.day,
            hour=hour,
            minute=minute,
            timezone=timezone,
        )

    # Fallback — treat as one-time
    logger.warning("[FUSE] Unknown repeat value '%s' — treating as one-time.", repeat)
    run_at = timezone.localize(
        datetime(
            parsed_date.year, parsed_date.month, parsed_date.day,
            hour, minute, 0,
        )
    )
    return DateTrigger(run_date=run_at)


def compute_end_date(ends: str) -> datetime | None:
    """Compute the absolute end datetime from an 'ends' config value."""
    now = datetime.utcnow()
    mapping: dict[str, timedelta | None] = {
        "1y":    timedelta(days=365),
        "6m":    timedelta(days=182),
        "3m":    timedelta(days=91),
        "1m":    timedelta(days=31),
        "never": None,
    }
    delta = mapping.get(ends)
    return (now + delta) if delta is not None else None


# ─── Handler ───────────────────────────────────────────────────────────────────

class ScheduleHandler(NodeHandler):
    """
    Schedule starter node.

    The trigger data (``fired_at`` timestamp) is injected by the ScheduleExecution
    job callback before execution begins, so execute() just passes it through.
    """

    def execute(self, config: dict, context) -> dict:  # noqa: ARG002
        logger.info(
            "[FUSE] schedule trigger fired — workflow=%s run=%s fired_at=%s",
            context.workflow_id,
            context.run_id,
            context.trigger_data.get("fired_at", context.triggered_at),
        )
        logger.info(
            "[FUSE]   trigger_data = %s",
            context.trigger_data,
        )
        return context.trigger_data

"""
News & Economic Calendar Engine — Feature 7

Fetches upcoming economic events and adds signal warnings.

Live data path (PR #3):
    `app.services.calendar_provider.refresh_calendar_loop()` runs every 6h
    and pulls real published times from the ForexFactory weekly JSON mirror.
    When live data is available, events have `is_indicative=False` and a
    `source` tag (e.g. "forexfactory").

Fallback path (used until the first successful fetch, or when the upstream
mirror is offline): a hardcoded recurring schedule that *synthesizes*
plausible upcoming events. Every event in this path has `is_indicative=True`
so the frontend can render an "approximate" badge.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

import pytz

from app.services.calendar_provider import (
    filter_events_by_window,
    get_cached_events,
)

logger = logging.getLogger(__name__)

PKT = pytz.timezone("Asia/Karachi")

# Hardcoded recurring high-impact events used ONLY when the live calendar
# fetch returns nothing. Every event emitted from this path is tagged
# `is_indicative=True`.
_HARDCODED_EVENTS = [
    {"name": "FOMC Meeting", "impact": "HIGH", "currency": "USD", "recurring": "monthly"},
    {"name": "CPI Release", "impact": "HIGH", "currency": "USD", "recurring": "monthly"},
    {"name": "NFP (Non-Farm Payrolls)", "impact": "HIGH", "currency": "USD", "recurring": "monthly"},
    {"name": "PPI Release", "impact": "MEDIUM", "currency": "USD", "recurring": "monthly"},
    {"name": "GDP Release", "impact": "MEDIUM", "currency": "USD", "recurring": "quarterly"},
    {"name": "Unemployment Claims", "impact": "MEDIUM", "currency": "USD", "recurring": "weekly"},
    {"name": "Fed Chair Speech", "impact": "HIGH", "currency": "USD", "recurring": "occasional"},
]


def _get_impact_minutes(impact: str) -> Dict:
    """Get warning window minutes for each impact level."""
    if impact == "HIGH":
        return {"before": 30, "after": 60}
    elif impact == "MEDIUM":
        return {"before": 15, "after": 30}
    else:
        return {"before": 0, "after": 0}


def _generate_synthesized_events(days_ahead: int = 7) -> List[Dict]:
    """Fallback event generator from the hardcoded recurring schedule."""
    now = datetime.now(timezone.utc)
    events: List[Dict] = []

    for tpl in _HARDCODED_EVENTS:
        recurring = tpl.get("recurring", "monthly")

        if recurring == "weekly":
            days_to_thursday = (3 - now.weekday()) % 7
            if days_to_thursday == 0:
                days_to_thursday = 7
            event_dt = now.replace(hour=13, minute=30, second=0, microsecond=0) \
                + timedelta(days=days_to_thursday)
        elif recurring == "monthly":
            this_month_dt = now.replace(day=10, hour=13, minute=30, second=0, microsecond=0)
            if now < this_month_dt:
                event_dt = this_month_dt
            else:
                next_month = (now.replace(day=1) + timedelta(days=32)).replace(day=1)
                event_dt = next_month.replace(day=10, hour=13, minute=30, second=0, microsecond=0)
        elif recurring == "quarterly":
            quarter_months = [3, 6, 9, 12]
            next_quarter_month = next((m for m in quarter_months if m > now.month), 3)
            event_dt = now.replace(
                month=next_quarter_month, day=28, hour=13, minute=30,
                second=0, microsecond=0,
            )
            if event_dt < now:
                event_dt = event_dt + timedelta(days=90)
        else:
            continue

        if event_dt > now + timedelta(days=days_ahead):
            continue

        events.append({
            "name": tpl["name"],
            "impact": tpl["impact"],
            "currency": tpl["currency"],
            "datetime_utc": event_dt.isoformat(),
            "source": "fallback",
            "is_indicative": True,
            "forecast": None,
            "previous": None,
        })

    events.sort(key=lambda e: e["datetime_utc"])
    return events


def _enrich_event(e: Dict) -> Dict:
    """Add `minutes_until`, `datetime_pkt`, `is_active_warning`, `warning_message`."""
    try:
        dt = datetime.fromisoformat(e["datetime_utc"])
    except (KeyError, ValueError, TypeError):
        return e

    now = datetime.now(timezone.utc)
    delta = dt - now
    minutes_until = int(delta.total_seconds() // 60)
    pkt_dt = dt.astimezone(PKT)
    win = _get_impact_minutes(e.get("impact", "LOW"))
    active = -win["after"] * 60 <= delta.total_seconds() <= win["before"] * 60

    return {
        **e,
        "minutes_until": minutes_until,
        "datetime_pkt": pkt_dt.strftime("%Y-%m-%d %I:%M %p PKT"),
        "is_active_warning": active,
        "warning_message": _get_warning_message(e["name"], e.get("impact", "LOW"), minutes_until)
        if active else None,
    }


def _get_warning_message(event_name: str, impact: str, minutes_until: int) -> str:
    if minutes_until > 0:
        direction = f"in {minutes_until} min"
    else:
        direction = f"{abs(minutes_until)} min ago"
    if impact == "HIGH":
        return f"⚠️ HIGH IMPACT EVENT ({event_name} {direction}) — Trade with caution, wider SL recommended (+50%)"
    if impact == "MEDIUM":
        return f"🟠 MEDIUM IMPACT EVENT ({event_name} {direction}) — Monitor closely"
    return f"{event_name} {direction}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_upcoming_events(days_ahead: int = 7) -> List[Dict]:
    """
    Return upcoming events for the next `days_ahead` days.

    Prefers the live calendar fetched by `services.calendar_provider`. Falls
    back to the synthesized hardcoded schedule when the cache is empty.
    """
    cached = get_cached_events()
    if cached.events:
        filtered = filter_events_by_window(cached.events, days_ahead=days_ahead)
        return [_enrich_event(e) for e in filtered]

    return [_enrich_event(e) for e in _generate_synthesized_events(days_ahead)]


def get_active_event_warnings() -> List[Dict]:
    """Get currently active event warnings (within warning window)."""
    return [e for e in get_upcoming_events() if e.get("is_active_warning")]


def get_signal_event_warning(signal_time: Optional[datetime] = None) -> Optional[str]:
    """Return highest-impact active warning message at signal time, or None."""
    warnings = get_active_event_warnings()
    if not warnings:
        return None
    high = [w for w in warnings if w.get("impact") == "HIGH"]
    medium = [w for w in warnings if w.get("impact") == "MEDIUM"]
    if high:
        return high[0]["warning_message"]
    if medium:
        return medium[0]["warning_message"]
    return None


def get_next_event() -> Optional[Dict]:
    events = get_upcoming_events()
    future = [e for e in events if (e.get("minutes_until") or 0) > 0]
    return future[0] if future else None


def get_calendar_status() -> Dict:
    """Diagnostic snapshot — useful for the frontend's status badge."""
    cached = get_cached_events()
    return {
        "source": cached.source,
        "events_cached": len(cached.events),
        "is_indicative": cached.is_indicative,
        "fetched_at": cached.fetched_at.isoformat() if cached.fetched_at else None,
    }


class NewsEngine:
    """Economic calendar and news filter engine."""

    def get_events(self, days_ahead: int = 7) -> List[Dict]:
        return get_upcoming_events(days_ahead)

    def get_warnings(self) -> List[Dict]:
        return get_active_event_warnings()

    def get_signal_warning(self) -> Optional[str]:
        return get_signal_event_warning()

    def get_next_event(self) -> Optional[Dict]:
        return get_next_event()

    def get_status(self) -> Dict:
        return get_calendar_status()


news_engine = NewsEngine()

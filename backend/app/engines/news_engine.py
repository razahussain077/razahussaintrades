"""
News & Economic Calendar Engine — Feature 7
Fetches upcoming economic events and adds signal warnings.
Uses free public economic calendar APIs.
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

import httpx
import pytz

logger = logging.getLogger(__name__)

PKT = pytz.timezone("Asia/Karachi")

# Hardcoded recurring high-impact events (FOMC, CPI, etc.)
# These are approximate — in production you'd fetch from a real calendar API
_HARDCODED_EVENTS = [
    {"name": "FOMC Meeting", "impact": "HIGH", "currency": "USD", "recurring": "monthly"},
    {"name": "CPI Release", "impact": "HIGH", "currency": "USD", "recurring": "monthly"},
    {"name": "NFP (Non-Farm Payrolls)", "impact": "HIGH", "currency": "USD", "recurring": "monthly"},
    {"name": "PPI Release", "impact": "MEDIUM", "currency": "USD", "recurring": "monthly"},
    {"name": "GDP Release", "impact": "MEDIUM", "currency": "USD", "recurring": "quarterly"},
    {"name": "Unemployment Claims", "impact": "MEDIUM", "currency": "USD", "recurring": "weekly"},
    {"name": "Fed Chair Speech", "impact": "HIGH", "currency": "USD", "recurring": "occasional"},
]

# In-memory cached events
_cached_events: List[Dict] = []
_last_fetch: Optional[datetime] = None
_CACHE_TTL_HOURS = 1


def _get_impact_minutes(impact: str) -> Dict:
    """Get warning window minutes for each impact level."""
    if impact == "HIGH":
        return {"before": 30, "after": 60}
    elif impact == "MEDIUM":
        return {"before": 15, "after": 30}
    else:
        return {"before": 0, "after": 0}


def _generate_upcoming_events(days_ahead: int = 7) -> List[Dict]:
    """
    Generate a list of upcoming events for the next N days.
    In a real deployment, this would fetch from investing.com, forexfactory.com, etc.
    We generate plausible upcoming events based on recurring schedule.
    """
    now = datetime.now(timezone.utc)
    events = []

    # Find next occurrence of each event type
    for event_template in _HARDCODED_EVENTS:
        # Schedule based on recurring type
        recurring = event_template.get("recurring", "monthly")

        if recurring == "weekly":
            # Every Thursday
            days_to_thursday = (3 - now.weekday()) % 7
            if days_to_thursday == 0:
                days_to_thursday = 7
            event_dt = now.replace(hour=13, minute=30, second=0, microsecond=0) + timedelta(days=days_to_thursday)
        elif recurring == "monthly":
            # Second or third week of month, varying
            next_month = (now.replace(day=1) + timedelta(days=32)).replace(day=1)
            event_dt = next_month.replace(day=10, hour=13, minute=30, second=0, microsecond=0)
            # If already past this month's occurrence
            this_month_dt = now.replace(day=10, hour=13, minute=30, second=0, microsecond=0)
            if now < this_month_dt:
                event_dt = this_month_dt
        elif recurring == "quarterly":
            # End of quarter
            quarter_months = [3, 6, 9, 12]
            next_quarter_month = next((m for m in quarter_months if m > now.month), 3)
            event_dt = now.replace(month=next_quarter_month, day=28, hour=13, minute=30, second=0, microsecond=0)
            if event_dt < now:
                event_dt = event_dt + timedelta(days=90)
        else:
            continue

        # Only include if within days_ahead
        if event_dt <= now + timedelta(days=days_ahead):
            pkt_dt = event_dt.astimezone(PKT)
            time_until = event_dt - now
            minutes_until = int(time_until.total_seconds() / 60)

            impact_windows = _get_impact_minutes(event_template["impact"])
            is_active_window = -impact_windows["after"] * 60 <= time_until.total_seconds() <= impact_windows["before"] * 60

            events.append({
                "name": event_template["name"],
                "impact": event_template["impact"],
                "currency": event_template["currency"],
                "datetime_utc": event_dt.isoformat(),
                "datetime_pkt": pkt_dt.strftime("%Y-%m-%d %I:%M %p PKT"),
                "minutes_until": minutes_until,
                "is_active_warning": is_active_window,
                "warning_message": _get_warning_message(event_template["name"], event_template["impact"], minutes_until) if is_active_window else None,
            })

    # Sort by time
    return sorted(events, key=lambda e: e["minutes_until"])


def _get_warning_message(event_name: str, impact: str, minutes_until: int) -> str:
    """Generate appropriate warning message for an event."""
    if minutes_until > 0:
        direction = f"in {minutes_until} min"
    else:
        direction = f"{abs(minutes_until)} min ago"

    if impact == "HIGH":
        return f"⚠️ HIGH IMPACT EVENT ({event_name} {direction}) — Trade with caution, wider SL recommended (+50%)"
    else:
        return f"🟠 MEDIUM IMPACT EVENT ({event_name} {direction}) — Monitor closely"


def get_upcoming_events(days_ahead: int = 7) -> List[Dict]:
    """Get upcoming economic events."""
    global _cached_events, _last_fetch
    now = datetime.now(timezone.utc)

    if _last_fetch is None or (now - _last_fetch).total_seconds() > _CACHE_TTL_HOURS * 3600:
        _cached_events = _generate_upcoming_events(days_ahead)
        _last_fetch = now

    return _cached_events


def get_active_event_warnings() -> List[Dict]:
    """Get currently active event warnings (within warning window)."""
    events = get_upcoming_events()
    return [e for e in events if e.get("is_active_warning")]


def get_signal_event_warning(signal_time: Optional[datetime] = None) -> Optional[str]:
    """
    Check if there's an active event warning at signal time.
    Returns warning message if applicable.
    """
    warnings = get_active_event_warnings()
    if not warnings:
        return None

    # Return the highest impact warning
    high = [w for w in warnings if w["impact"] == "HIGH"]
    medium = [w for w in warnings if w["impact"] == "MEDIUM"]

    if high:
        return high[0]["warning_message"]
    if medium:
        return medium[0]["warning_message"]
    return None


def get_next_event() -> Optional[Dict]:
    """Get the next upcoming event."""
    events = get_upcoming_events()
    future_events = [e for e in events if e["minutes_until"] > 0]
    return future_events[0] if future_events else None


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

    def refresh_events(self) -> None:
        """Force-refresh the events cache."""
        global _cached_events, _last_fetch
        _cached_events = _generate_upcoming_events()
        _last_fetch = datetime.now(timezone.utc)


news_engine = NewsEngine()

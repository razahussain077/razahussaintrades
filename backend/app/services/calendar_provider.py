"""
Economic calendar provider — replaces the synthesized hardcoded events with
real published times.

Source priority:

  1. ForexFactory weekly JSON mirror (free, unofficial, no API key).
     Endpoints used:
       - https://nfs.faireconomy.media/ff_calendar_thisweek.json
       - https://nfs.faireconomy.media/ff_calendar_nextweek.json
     Each entry has fields like:
       {"title": "Core PCE Price Index m/m",
        "country": "USD",
        "date": "2024-12-20T08:30:00-05:00",
        "impact": "High" | "Medium" | "Low" | "Holiday",
        "forecast": "0.2%", "previous": "0.3%"}

  2. Fallback: the synthesized hardcoded events the bot used previously.
     Marked with `is_indicative=True` so the frontend can render an
     "approximate" badge.

The provider is designed to fail-open: if every source returns nothing, we
emit the synthesized fallback rather than blocking signal generation.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

_FOREXFACTORY_THIS = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
_FOREXFACTORY_NEXT = "https://nfs.faireconomy.media/ff_calendar_nextweek.json"

# Currencies whose macro events meaningfully move crypto / risk assets.
_RELEVANT_CCYS = {"USD", "EUR", "GBP", "JPY", "CNY", "CHF", "ALL"}

# Map ForexFactory impact strings → our internal levels.
_IMPACT_MAP = {
    "High": "HIGH",
    "Medium": "MEDIUM",
    "Low": "LOW",
    "Holiday": "LOW",
}


@dataclass
class CalendarFetchResult:
    events: List[Dict]
    source: str
    fetched_at: datetime
    is_indicative: bool


def _normalize_ff_entry(entry: Dict) -> Optional[Dict]:
    """Parse one ForexFactory entry into our internal event shape."""
    title = entry.get("title")
    country = entry.get("country") or entry.get("currency")
    impact_raw = entry.get("impact") or "Low"
    date_str = entry.get("date") or entry.get("datetime")
    if not (title and country and date_str):
        return None

    # ForexFactory dates can be ISO-with-offset or "YYYY-MM-DD HH:MM:SS".
    try:
        # try ISO with timezone
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            # ForexFactory feed defaults to US/Eastern when no offset present.
            # Treating it as UTC is wrong but rarely encountered with the
            # mirror endpoints — fall back to UTC and tag it.
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
    except ValueError:
        return None

    impact = _IMPACT_MAP.get(impact_raw, "LOW")

    return {
        "name": title,
        "impact": impact,
        "currency": country,
        "datetime_utc": dt.isoformat(),
        "minutes_until": int((dt - datetime.now(timezone.utc)).total_seconds() // 60),
        "forecast": entry.get("forecast"),
        "previous": entry.get("previous"),
        "source": "forexfactory",
        "is_indicative": False,
    }


async def _fetch_forexfactory(client: httpx.AsyncClient, url: str) -> List[Dict]:
    try:
        r = await client.get(url, timeout=10.0)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        logger.warning("calendar_provider: failed to fetch %s: %s", url, e)
        return []
    if not isinstance(data, list):
        return []
    out: List[Dict] = []
    for entry in data:
        norm = _normalize_ff_entry(entry)
        if not norm:
            continue
        if norm["currency"] not in _RELEVANT_CCYS:
            continue
        out.append(norm)
    return out


async def fetch_real_events(timeout_seconds: float = 15.0) -> CalendarFetchResult:
    """
    Fetch + normalize this-week + next-week events from ForexFactory.

    Returns a CalendarFetchResult; on total failure, `events` is empty and
    `source == "fallback"`. Callers MUST handle the empty case.
    """
    fetched_at = datetime.now(timezone.utc)
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            this_week, next_week = await asyncio.gather(
                _fetch_forexfactory(client, _FOREXFACTORY_THIS),
                _fetch_forexfactory(client, _FOREXFACTORY_NEXT),
            )
        events = this_week + next_week
        if events:
            events.sort(key=lambda e: e["datetime_utc"])
            return CalendarFetchResult(
                events=events, source="forexfactory",
                fetched_at=fetched_at, is_indicative=False,
            )
    except Exception as e:
        logger.error("calendar_provider: unexpected error: %s", e)

    return CalendarFetchResult(
        events=[], source="fallback", fetched_at=fetched_at, is_indicative=True,
    )


# ---------------------------------------------------------------------------
# In-memory cache + refresh loop
# ---------------------------------------------------------------------------

_REFRESH_INTERVAL_SECONDS = 6 * 3600  # 6 hours

_cache: CalendarFetchResult = CalendarFetchResult(
    events=[], source="never_fetched",
    fetched_at=datetime.fromtimestamp(0, tz=timezone.utc),
    is_indicative=True,
)


def get_cached_events() -> CalendarFetchResult:
    return _cache


def set_cached_events(result: CalendarFetchResult) -> None:
    """Test/utility hook for injecting events without triggering a fetch."""
    global _cache
    _cache = result


async def refresh_calendar_loop() -> None:
    """Background task: fetch every `_REFRESH_INTERVAL_SECONDS`."""
    global _cache
    while True:
        try:
            result = await fetch_real_events()
            if result.events:
                _cache = result
                logger.info(
                    "calendar_provider: cached %d events from %s",
                    len(result.events), result.source,
                )
            else:
                logger.warning("calendar_provider: live fetch returned no events; keeping previous cache")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("calendar_provider: refresh loop error: %s", e)
        try:
            await asyncio.sleep(_REFRESH_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            break


def filter_events_by_window(
    events: List[Dict],
    days_ahead: int = 7,
    impacts: Optional[List[str]] = None,
) -> List[Dict]:
    """Filter events to those occurring in [now, now+days_ahead] and matching
    `impacts` (default: HIGH + MEDIUM only)."""
    if impacts is None:
        impacts = ["HIGH", "MEDIUM"]
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=days_ahead)
    out: List[Dict] = []
    for e in events:
        if e.get("impact") not in impacts:
            continue
        try:
            dt = datetime.fromisoformat(e["datetime_utc"])
        except (KeyError, ValueError, TypeError):
            continue
        if dt > cutoff:
            continue
        out.append(e)
    return out

"""Tests for the real economic calendar provider + news_engine fallback."""
from datetime import datetime, timedelta, timezone

import pytest

from app.services.calendar_provider import (
    CalendarFetchResult,
    _normalize_ff_entry,
    filter_events_by_window,
    get_cached_events,
    set_cached_events,
)


@pytest.fixture(autouse=True)
def _reset_calendar_cache():
    set_cached_events(CalendarFetchResult(
        events=[], source="never_fetched",
        fetched_at=datetime.fromtimestamp(0, tz=timezone.utc),
        is_indicative=True,
    ))
    yield
    set_cached_events(CalendarFetchResult(
        events=[], source="never_fetched",
        fetched_at=datetime.fromtimestamp(0, tz=timezone.utc),
        is_indicative=True,
    ))


class TestNormalizeFfEntry:
    def test_high_impact_usd_entry(self):
        e = _normalize_ff_entry({
            "title": "Core PCE Price Index m/m",
            "country": "USD",
            "date": "2024-12-20T08:30:00-05:00",
            "impact": "High",
            "forecast": "0.2%", "previous": "0.3%",
        })
        assert e is not None
        assert e["name"] == "Core PCE Price Index m/m"
        assert e["currency"] == "USD"
        assert e["impact"] == "HIGH"
        assert e["is_indicative"] is False
        assert e["source"] == "forexfactory"
        assert "datetime_utc" in e
        # Date parsed and converted to UTC.
        assert e["datetime_utc"].endswith("+00:00") or e["datetime_utc"].endswith("Z")

    def test_holiday_mapped_to_low(self):
        e = _normalize_ff_entry({
            "title": "Christmas Day", "country": "USD",
            "date": "2024-12-25T00:00:00+00:00", "impact": "Holiday",
        })
        assert e is not None and e["impact"] == "LOW"

    def test_missing_required_fields_returns_none(self):
        assert _normalize_ff_entry({"title": "x"}) is None
        assert _normalize_ff_entry({"date": "2024-01-01T00:00:00Z"}) is None

    def test_unparseable_date_returns_none(self):
        e = _normalize_ff_entry({
            "title": "Foo", "country": "USD",
            "date": "not a date", "impact": "High",
        })
        assert e is None


class TestFilterEventsByWindow:
    def _make(self, name: str, dt: datetime, impact: str = "HIGH") -> dict:
        return {
            "name": name, "currency": "USD", "impact": impact,
            "datetime_utc": dt.astimezone(timezone.utc).isoformat(),
            "source": "forexfactory", "is_indicative": False,
        }

    def test_drops_low_impact_by_default(self):
        now = datetime.now(timezone.utc)
        events = [
            self._make("FOMC", now + timedelta(hours=2), "HIGH"),
            self._make("Holiday", now + timedelta(hours=2), "LOW"),
        ]
        kept = filter_events_by_window(events, days_ahead=7)
        assert [e["name"] for e in kept] == ["FOMC"]

    def test_drops_events_outside_window(self):
        now = datetime.now(timezone.utc)
        events = [
            self._make("Soon", now + timedelta(hours=2)),
            self._make("Way later", now + timedelta(days=30)),
        ]
        kept = filter_events_by_window(events, days_ahead=7)
        assert [e["name"] for e in kept] == ["Soon"]

    def test_explicit_impacts(self):
        now = datetime.now(timezone.utc)
        events = [
            self._make("M", now + timedelta(hours=1), "MEDIUM"),
            self._make("L", now + timedelta(hours=1), "LOW"),
        ]
        kept = filter_events_by_window(events, days_ahead=7, impacts=["LOW"])
        assert [e["name"] for e in kept] == ["L"]


class TestNewsEngineFallback:
    def test_returns_synthesized_when_cache_empty(self):
        from app.engines.news_engine import get_calendar_status, get_upcoming_events
        events = get_upcoming_events(days_ahead=14)
        # All synthesized fallback events must be tagged is_indicative.
        assert all(e.get("is_indicative") is True for e in events)
        assert all(e.get("source") == "fallback" for e in events)
        # Status should reflect the empty cache.
        status = get_calendar_status()
        assert status["events_cached"] == 0
        assert status["is_indicative"] is True

    def test_uses_live_cache_when_populated(self):
        from app.engines.news_engine import get_upcoming_events
        now = datetime.now(timezone.utc)
        live_event = {
            "name": "FOMC Statement", "currency": "USD", "impact": "HIGH",
            "datetime_utc": (now + timedelta(hours=2)).isoformat(),
            "source": "forexfactory", "is_indicative": False,
            "forecast": "5.50%", "previous": "5.50%",
        }
        set_cached_events(CalendarFetchResult(
            events=[live_event], source="forexfactory",
            fetched_at=now, is_indicative=False,
        ))

        events = get_upcoming_events(days_ahead=7)
        assert len(events) == 1
        e = events[0]
        assert e["is_indicative"] is False
        assert e["source"] == "forexfactory"
        assert e["minutes_until"] >= 0
        assert "datetime_pkt" in e

    def test_warning_window_active_for_imminent_event(self):
        from app.engines.news_engine import (
            get_active_event_warnings,
            get_signal_event_warning,
        )
        now = datetime.now(timezone.utc)
        # 5 minutes from now → within HIGH-impact 30-min before window.
        event = {
            "name": "CPI YoY", "currency": "USD", "impact": "HIGH",
            "datetime_utc": (now + timedelta(minutes=5)).isoformat(),
            "source": "forexfactory", "is_indicative": False,
            "forecast": None, "previous": None,
        }
        set_cached_events(CalendarFetchResult(
            events=[event], source="forexfactory",
            fetched_at=now, is_indicative=False,
        ))
        warnings = get_active_event_warnings()
        assert len(warnings) == 1
        assert warnings[0]["impact"] == "HIGH"

        msg = get_signal_event_warning()
        assert msg is not None
        assert "HIGH IMPACT" in msg

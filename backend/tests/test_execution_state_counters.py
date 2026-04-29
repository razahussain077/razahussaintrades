"""Tests for the live position / PnL counters used by the guardian's caps.

These were added to address Devin Review's finding that the auto-execution
scan loop and `/place` endpoint were passing hardcoded zeros for
`open_positions_count` and `today_pnl_usd`, silently disabling the
concurrent-position cap and the daily-loss circuit breaker.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

from app.database.db import init_db
from app.database.models import save_signal, save_signal_history
from app.execution import state as exec_state


@pytest.fixture(autouse=True)
def _isolated_state(monkeypatch, tmp_path):
    monkeypatch.setenv("EXECUTION_ARMED_PATH", str(tmp_path / "armed.json"))
    monkeypatch.setenv("EXECUTION_ORDERS_PATH", str(tmp_path / "orders.json"))
    monkeypatch.setenv("KILL_SWITCH_PATH", str(tmp_path / "kill.json"))
    # Isolate the SQLite DB so tests don't see pollution from prior runs.
    db_file = tmp_path / "test.db"
    from app.database import db as _db_mod
    monkeypatch.setattr(_db_mod, "DB_PATH", str(db_file))
    yield


def _seed_signal(sid: str, is_active: bool = True) -> dict:
    return {
        "id": sid,
        "coin": "BTCUSDT",
        "exchange": "binance",
        "signal_type": "LONG",
        "timeframe": "1h",
        "entry_low": 100.0,
        "entry_high": 102.0,
        "stop_loss": 98.0,
        "stop_loss_pct": 2.0,
        "take_profit_1": 105.0,
        "take_profit_1_pct": 5.0,
        "take_profit_2": 108.0,
        "take_profit_2_pct": 8.0,
        "take_profit_3": 112.0,
        "take_profit_3_pct": 12.0,
        "recommended_leverage": 5.0,
        "liquidation_price": 80.0,
        "risk_reward": 2.0,
        "confidence_score": 85.0,
        "setup_type": "OB",
        "reasoning": ["test"],
        "invalidation": "below 98",
        "kill_zone": "London",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "is_active": 1 if is_active else 0,
    }


# ---------------------------------------------------------------------------
# count_open_executed_positions
# ---------------------------------------------------------------------------
class TestCountOpenPositions:
    @pytest.mark.asyncio
    async def test_no_orders_returns_zero(self):
        assert await exec_state.count_open_executed_positions() == 0

    @pytest.mark.asyncio
    async def test_dry_run_records_excluded(self):
        # Dry-run records cost no margin and must not count.
        exec_state.record_order("sig-dry-1", "dry-1", dry_run=True)
        exec_state.record_order("sig-dry-2", "dry-2", dry_run=True)
        assert await exec_state.count_open_executed_positions() == 0

    @pytest.mark.asyncio
    async def test_live_active_signal_counted(self):
        await init_db()
        await save_signal(_seed_signal("sig-live-active", is_active=True))
        exec_state.record_order("sig-live-active", "ord-1", dry_run=False)
        assert await exec_state.count_open_executed_positions() == 1

    @pytest.mark.asyncio
    async def test_live_inactive_signal_not_counted(self):
        await init_db()
        await save_signal(_seed_signal("sig-live-closed", is_active=True))
        exec_state.record_order("sig-live-closed", "ord-2", dry_run=False)
        # Mark closed via signal_history (sets is_active=0).
        await save_signal_history({
            "signal_id": "sig-live-closed",
            "result": "WIN",
            "pnl": 100.0,
        })
        assert await exec_state.count_open_executed_positions() == 0


# ---------------------------------------------------------------------------
# today_realised_pnl_usd
# ---------------------------------------------------------------------------
class TestTodayRealisedPnL:
    @pytest.mark.asyncio
    async def test_empty_history_returns_zero(self):
        await init_db()
        assert await exec_state.today_realised_pnl_usd() == 0.0

    @pytest.mark.asyncio
    async def test_today_pnl_summed(self):
        await init_db()
        await save_signal(_seed_signal("sig-pnl-1"))
        await save_signal(_seed_signal("sig-pnl-2"))
        await save_signal_history({
            "signal_id": "sig-pnl-1", "result": "WIN", "pnl": 50.0,
        })
        await save_signal_history({
            "signal_id": "sig-pnl-2", "result": "LOSS", "pnl": -20.0,
        })
        total = await exec_state.today_realised_pnl_usd()
        assert total == pytest.approx(30.0)

    @pytest.mark.asyncio
    async def test_yesterday_pnl_excluded(self):
        await init_db()
        await save_signal(_seed_signal("sig-pnl-old"))
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        await save_signal_history({
            "signal_id": "sig-pnl-old", "result": "LOSS", "pnl": -500.0,
            "closed_at": yesterday,
        })
        assert await exec_state.today_realised_pnl_usd() == 0.0

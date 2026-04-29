"""End-to-end tests for app/execution/ccxt_executor.py.

We never hit a real exchange — the dry-run path covers everything we want to
assert (sizing, idempotency, gating). For the live path, `_place_real_bracket`
is patched with a deterministic stub.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.config import settings
from app.execution import state as exec_state
from app.execution.ccxt_executor import CCXTExecutor


def _signal(**overrides):
    base = {
        "id": "sig-exec-1",
        "coin": "BTCUSDT",
        "signal_type": "LONG",
        "confidence_score": 88.0,
        "entry_low": 100.0,
        "entry_high": 102.0,
        "stop_loss": 98.0,
        "take_profit_1": 105.0,
        "take_profit_2": 108.0,
        "take_profit_3": 112.0,
        "recommended_leverage": 7.0,
        "risk_reward_net": 2.0,
    }
    base.update(overrides)
    return base


@pytest.fixture(autouse=True)
def _isolated_state(monkeypatch, tmp_path):
    monkeypatch.setenv("EXECUTION_ARMED_PATH", str(tmp_path / "armed.json"))
    monkeypatch.setenv("EXECUTION_ORDERS_PATH", str(tmp_path / "orders.json"))
    monkeypatch.setenv("KILL_SWITCH_PATH", str(tmp_path / "kill.json"))
    yield


@pytest.fixture
def armed():
    """Arm execution before the test, disarm after."""
    until = datetime.now(timezone.utc) + timedelta(minutes=10)
    exec_state.set_armed(True, armed_until=until)
    yield
    exec_state.set_armed(False)


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(settings, "AUTO_EXECUTION_ENABLED", True)
    monkeypatch.setattr(settings, "AUTO_EXECUTION_DRY_RUN", True)
    yield


# ---------------------------------------------------------------------------
# Master gates
# ---------------------------------------------------------------------------
class TestGates:
    def test_disabled_at_master_switch(self, monkeypatch):
        monkeypatch.setattr(settings, "AUTO_EXECUTION_ENABLED", False)
        ex = CCXTExecutor()
        r = ex.place_for_signal(_signal(), 10000, 0, 0.0)
        assert r["ok"] is False and r["reason"] == "auto_execution_disabled"

    def test_not_armed_blocks(self, enabled):
        # Don't arm.
        ex = CCXTExecutor()
        r = ex.place_for_signal(_signal(), 10000, 0, 0.0)
        assert r["ok"] is False and r["reason"] == "not_armed"

    def test_kill_switch_blocks(self, enabled, armed):
        from app.notifications.kill_switch import set_kill_switch
        try:
            set_kill_switch(True, reason="test")
            ex = CCXTExecutor()
            r = ex.place_for_signal(_signal(), 10000, 0, 0.0)
            assert r["ok"] is False
            assert r["reason"] == "kill_switch_active"
        finally:
            set_kill_switch(False)

    def test_idempotency_blocks_double_placement(self, enabled, armed):
        ex = CCXTExecutor()
        r1 = ex.place_for_signal(_signal(), 10000, 0, 0.0)
        assert r1["ok"] is True
        r2 = ex.place_for_signal(_signal(), 10000, 0, 0.0)
        assert r2["ok"] is False
        assert r2["reason"] == "duplicate_signal"
        assert "existing" in r2

    def test_low_confidence_blocked_by_guardian(self, enabled, armed):
        ex = CCXTExecutor()
        r = ex.place_for_signal(_signal(confidence_score=50.0), 10000, 0, 0.0)
        assert r["ok"] is False
        assert r["reason"] == "below_min_confidence"


# ---------------------------------------------------------------------------
# Dry-run output shape
# ---------------------------------------------------------------------------
class TestDryRun:
    def test_dry_run_returns_deterministic_id(self, enabled, armed):
        ex = CCXTExecutor()
        r = ex.place_for_signal(_signal(id="sig-42"), 10000, 0, 0.0)
        assert r["ok"] is True
        assert r["dry_run"] is True
        assert r["order_id"] == "dry-sig-42"

    def test_dry_run_emits_5_orders(self, enabled, armed):
        ex = CCXTExecutor()
        r = ex.place_for_signal(_signal(), 10000, 0, 0.0)
        assert r["ok"] is True
        purposes = [o["purpose"] for o in r["orders"]]
        assert purposes == ["ENTRY", "STOP_LOSS",
                            "TAKE_PROFIT_1", "TAKE_PROFIT_2", "TAKE_PROFIT_3"]

    def test_dry_run_order_shape_matches_live_path(self, enabled, armed):
        """The dry-run idempotency payload claims byte-identical shape with
        live; this regression test pins the SL type to stop_market and asserts
        all exit legs include reduceOnly=True."""
        ex = CCXTExecutor()
        r = ex.place_for_signal(_signal(), 10000, 0, 0.0)
        orders = {o["purpose"]: o for o in r["orders"]}
        assert orders["STOP_LOSS"]["type"] == "stop_market"
        assert orders["STOP_LOSS"]["reduceOnly"] is True
        for leg in ("TAKE_PROFIT_1", "TAKE_PROFIT_2", "TAKE_PROFIT_3"):
            assert orders[leg]["reduceOnly"] is True
        # Entry has no reduceOnly — it's opening, not closing.
        assert "reduceOnly" not in orders["ENTRY"] or orders["ENTRY"].get("reduceOnly") is not True

    def test_dry_run_tp_split_quantities(self, enabled, armed):
        ex = CCXTExecutor()
        r = ex.place_for_signal(_signal(), 10000, 0, 0.0)
        orders = {o["purpose"]: o for o in r["orders"]}
        entry_qty = orders["ENTRY"]["amount"]
        tp1, tp2, tp3 = (
            orders["TAKE_PROFIT_1"]["amount"],
            orders["TAKE_PROFIT_2"]["amount"],
            orders["TAKE_PROFIT_3"]["amount"],
        )
        assert tp1 == pytest.approx(entry_qty * 0.4)
        assert tp2 == pytest.approx(entry_qty * 0.4)
        assert tp3 == pytest.approx(entry_qty - tp1 - tp2)
        # Reduce-side direction = sell for LONG.
        assert orders["TAKE_PROFIT_1"]["side"] == "sell"
        assert orders["ENTRY"]["side"] == "buy"

    def test_short_signal_inverts_sides(self, enabled, armed):
        ex = CCXTExecutor()
        sig = _signal(
            signal_type="SHORT", id="sig-short",
            entry_low=200.0, entry_high=204.0, stop_loss=210.0,
            take_profit_1=190.0, take_profit_2=180.0, take_profit_3=170.0,
        )
        r = ex.place_for_signal(sig, 10000, 0, 0.0)
        assert r["ok"] is True
        orders = {o["purpose"]: o for o in r["orders"]}
        assert orders["ENTRY"]["side"] == "sell"
        assert orders["TAKE_PROFIT_1"]["side"] == "buy"

    def test_dry_run_recorded_in_idempotency_map(self, enabled, armed):
        ex = CCXTExecutor()
        ex.place_for_signal(_signal(id="sig-record"), 10000, 0, 0.0)
        rec = exec_state.get_recorded_order("sig-record")
        assert rec is not None
        assert rec["order_id"] == "dry-sig-record"
        assert rec["dry_run"] is True


# ---------------------------------------------------------------------------
# Live path (mocked ccxt)
# ---------------------------------------------------------------------------
class TestLivePath:
    def test_live_path_calls_create_order_for_each_leg(self, monkeypatch, armed):
        monkeypatch.setattr(settings, "AUTO_EXECUTION_ENABLED", True)
        monkeypatch.setattr(settings, "AUTO_EXECUTION_DRY_RUN", False)

        calls = []

        class FakeExchange:
            def set_leverage(self, lev, sym):
                calls.append(("leverage", lev, sym))

            def create_order(self, symbol, type_, side, amount, price=None,
                             params=None):
                calls.append(("order", symbol, type_, side, amount, price, params))
                return {"id": f"ord-{len(calls)}"}

        fake = FakeExchange()
        ex = CCXTExecutor()
        ex._exchange = fake  # bypass _make_exchange (which requires creds)

        r = ex.place_for_signal(_signal(id="sig-live"), 10000, 0, 0.0,
                                force_dry_run=False)
        assert r["ok"] is True, r
        assert r["dry_run"] is False
        # 1 leverage call + 1 entry + 1 SL + 3 TPs = 5 create_order + 1 leverage
        assert sum(1 for c in calls if c[0] == "order") == 5

    def test_live_path_records_and_blocks_replay(self, monkeypatch, armed):
        monkeypatch.setattr(settings, "AUTO_EXECUTION_ENABLED", True)
        monkeypatch.setattr(settings, "AUTO_EXECUTION_DRY_RUN", False)

        class FakeExchange:
            def set_leverage(self, *a, **k): pass
            def create_order(self, *a, **k):
                return {"id": "live-1"}

        ex = CCXTExecutor()
        ex._exchange = FakeExchange()
        r1 = ex.place_for_signal(_signal(id="sig-live-2"), 10000, 0, 0.0,
                                 force_dry_run=False)
        assert r1["ok"] is True
        r2 = ex.place_for_signal(_signal(id="sig-live-2"), 10000, 0, 0.0,
                                 force_dry_run=False)
        assert r2["ok"] is False and r2["reason"] == "duplicate_signal"

    def test_live_path_exchange_error_returns_rejection(self, monkeypatch, armed):
        monkeypatch.setattr(settings, "AUTO_EXECUTION_ENABLED", True)
        monkeypatch.setattr(settings, "AUTO_EXECUTION_DRY_RUN", False)

        class BoomExchange:
            def set_leverage(self, *a, **k): pass
            def create_order(self, *a, **k):
                raise RuntimeError("network down")

        ex = CCXTExecutor()
        ex._exchange = BoomExchange()
        r = ex.place_for_signal(_signal(id="sig-boom"), 10000, 0, 0.0,
                                force_dry_run=False)
        assert r["ok"] is False
        # Entry never placed → safe-to-retry rejection.
        assert r["reason"] == "exchange_error"
        assert "network down" in r["detail"]
        # And the idempotency map is empty — retries are allowed.
        assert exec_state.get_recorded_order("sig-boom") is None

    def test_partial_bracket_records_entry_and_blocks_retry(
        self, monkeypatch, armed,
    ):
        """Entry filled, SL submission errored. Caller must record the entry
        in the idempotency map so a retry can't double the position."""
        monkeypatch.setattr(settings, "AUTO_EXECUTION_ENABLED", True)
        monkeypatch.setattr(settings, "AUTO_EXECUTION_DRY_RUN", False)

        call_count = {"n": 0}

        class PartialExchange:
            def set_leverage(self, *a, **k): pass

            def create_order(self, *a, **k):
                call_count["n"] += 1
                # First call = entry (success). All subsequent = boom.
                if call_count["n"] == 1:
                    return {"id": "entry-99"}
                raise RuntimeError("rate limited")

        ex = CCXTExecutor()
        ex._exchange = PartialExchange()
        r1 = ex.place_for_signal(_signal(id="sig-partial"), 10000, 0, 0.0,
                                 force_dry_run=False)
        assert r1["ok"] is False
        assert r1["reason"] == "bracket_partial"
        assert r1["order_id"] == "entry-99"
        # Critically: entry IS recorded.
        rec = exec_state.get_recorded_order("sig-partial")
        assert rec is not None
        assert rec["order_id"] == "entry-99"
        assert rec["dry_run"] is False
        assert rec["payload"]["partial"] is True

        # Now the retry: must short-circuit on the idempotency map, NOT
        # re-place a second entry.
        ex._exchange = PartialExchange()  # fresh counter
        r2 = ex.place_for_signal(_signal(id="sig-partial"), 10000, 0, 0.0,
                                 force_dry_run=False)
        assert r2["ok"] is False
        assert r2["reason"] == "duplicate_signal"

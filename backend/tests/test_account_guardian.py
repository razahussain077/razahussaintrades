"""Tests for app/execution/account_guardian.py — pure-Python policy + sizing."""
from __future__ import annotations

import math

import pytest

from app.execution.account_guardian import (
    AccountGuardian,
    GuardianConfig,
    OrderPlan,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _signal(**overrides):
    base = {
        "id": "sig-1",
        "coin": "BTCUSDT",
        "signal_type": "LONG",
        "confidence_score": 85.0,
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


def _ok_kwargs(**overrides):
    base = {
        "equity_usd": 10000.0,
        "open_positions_count": 0,
        "today_pnl_usd": 0.0,
        "kill_switch_active": False,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Sizing math
# ---------------------------------------------------------------------------
class TestSizing:
    def test_long_position_size_matches_risk_pct(self):
        # equity 10_000 * 0.005 = $50 risk; entry 101, sl 98 → $3 / unit;
        # quantity = 50/3 ≈ 16.667; notional ≈ 16.667 * 101 ≈ 1683.33;
        # leverage clamped from 7 to max 5.
        g = AccountGuardian(GuardianConfig(max_risk_pct=0.005, max_leverage=5.0))
        plan, reason = g.compute_plan(_signal(), 10000.0)
        assert reason is None
        assert plan is not None
        assert plan.side == "LONG"
        assert plan.entry_mid == pytest.approx(101.0)
        assert plan.risk_usd == pytest.approx(50.0)
        assert plan.quantity == pytest.approx(50.0 / 3.0)
        assert plan.notional_usd == pytest.approx(plan.quantity * 101.0)
        assert plan.leverage == 5.0   # clamped

    def test_short_position_uses_correct_distance(self):
        sig = _signal(signal_type="SHORT", entry_low=200.0, entry_high=204.0,
                      stop_loss=210.0, take_profit_1=190.0,
                      take_profit_2=180.0, take_profit_3=170.0)
        g = AccountGuardian(GuardianConfig(max_risk_pct=0.005, max_leverage=5.0))
        plan, reason = g.compute_plan(sig, 10000.0)
        assert reason is None and plan is not None
        # entry mid = 202, sl = 210 → 8 / unit. risk = 50.
        assert plan.entry_mid == pytest.approx(202.0)
        assert plan.quantity == pytest.approx(50.0 / 8.0)

    def test_leverage_clamped_to_cap(self):
        # signal asks 50x, cap is 5x.
        g = AccountGuardian(GuardianConfig(max_leverage=5.0))
        plan, _ = g.compute_plan(_signal(recommended_leverage=50.0), 10000.0)
        assert plan.leverage == 5.0

    def test_leverage_minimum_one(self):
        g = AccountGuardian(GuardianConfig(max_leverage=5.0))
        plan, _ = g.compute_plan(_signal(recommended_leverage=0.0), 10000.0)
        assert plan.leverage >= 1.0

    def test_missing_entry_returns_reason(self):
        g = AccountGuardian()
        plan, reason = g.compute_plan(_signal(entry_low=None), 10000.0)
        assert plan is None and reason == "missing_entry"

    def test_zero_distance_sl_rejected(self):
        # SL on the wrong side of entry → zero risk per unit.
        g = AccountGuardian()
        plan, reason = g.compute_plan(_signal(stop_loss=110.0), 10000.0)
        assert plan is None and reason == "stop_loss_wrong_side"

    def test_invalid_side_rejected(self):
        g = AccountGuardian()
        plan, reason = g.compute_plan(_signal(signal_type="HODL"), 10000.0)
        assert plan is None and reason == "invalid_side"

    def test_short_aliases_accepted_for_tp(self):
        # Some test fixtures still use tp1/tp2/tp3 — must be honored.
        sig = _signal()
        sig.pop("take_profit_1")
        sig.pop("take_profit_2")
        sig.pop("take_profit_3")
        sig["tp1"], sig["tp2"], sig["tp3"] = 105.0, 108.0, 112.0
        g = AccountGuardian()
        plan, reason = g.compute_plan(sig, 10000.0)
        assert plan is not None and reason is None
        assert plan.take_profit_1 == 105.0

    def test_below_min_notional_rejected(self):
        g = AccountGuardian(GuardianConfig(min_notional_usd=100_000))
        plan, reason = g.compute_plan(_signal(), 10000.0)
        assert plan is None and reason == "below_min_notional"


# ---------------------------------------------------------------------------
# Policy evaluate()
# ---------------------------------------------------------------------------
class TestEvaluate:
    def test_happy_path_approves(self):
        g = AccountGuardian()
        d = g.evaluate(_signal(), **_ok_kwargs())
        assert d.approved is True
        assert d.plan is not None and d.plan.coin == "BTCUSDT"

    def test_kill_switch_blocks(self):
        g = AccountGuardian()
        d = g.evaluate(_signal(), **_ok_kwargs(kill_switch_active=True))
        assert d.approved is False
        assert d.reason == "kill_switch_active"
        assert d.plan is None

    def test_zero_equity_blocks(self):
        g = AccountGuardian()
        d = g.evaluate(_signal(), **_ok_kwargs(equity_usd=0.0))
        assert d.reason == "zero_equity"

    def test_max_positions_blocks(self):
        g = AccountGuardian(GuardianConfig(max_concurrent_positions=3))
        d = g.evaluate(_signal(), **_ok_kwargs(open_positions_count=3))
        assert d.reason == "max_positions_reached"

    def test_daily_loss_limit_trips(self):
        g = AccountGuardian(GuardianConfig(daily_loss_limit_pct=0.03))
        # 10_000 * 0.03 = 300 → -300 trips it.
        d = g.evaluate(_signal(), **_ok_kwargs(today_pnl_usd=-300.0))
        assert d.reason == "daily_loss_limit"

    def test_low_confidence_blocks(self):
        g = AccountGuardian(GuardianConfig(min_confidence_score=80.0))
        d = g.evaluate(_signal(confidence_score=70.0), **_ok_kwargs())
        assert d.reason == "below_min_confidence"

    def test_low_rr_net_blocks(self):
        g = AccountGuardian(GuardianConfig(min_risk_reward_net=1.5))
        d = g.evaluate(_signal(risk_reward_net=1.0), **_ok_kwargs())
        assert d.reason == "below_min_rr_net"

    def test_short_alias_rr_net_honored(self):
        # No `risk_reward_net` but legacy `rr_net` is set. Must read it.
        g = AccountGuardian()
        sig = _signal()
        sig.pop("risk_reward_net")
        sig["rr_net"] = 2.0
        d = g.evaluate(sig, **_ok_kwargs())
        assert d.approved is True

    def test_clamp_note_emitted(self):
        # Recommended 7x → clamped to 5x → note must be emitted.
        g = AccountGuardian(GuardianConfig(max_leverage=5.0))
        d = g.evaluate(_signal(recommended_leverage=7.0), **_ok_kwargs())
        assert d.approved is True
        assert any("clamped" in n for n in d.notes)

    def test_insufficient_margin_blocks(self):
        # Force tiny equity so notional > equity at 1x leverage.
        # equity = 1; risk = 0.005; per-unit risk = 3 → qty 0.00167; notional 0.168
        # Margin required at 1x = 0.168 > 1.0? No.
        # We need a case where margin > equity. Set max_leverage=1 and big risk_pct.
        g = AccountGuardian(GuardianConfig(
            max_risk_pct=0.5,   # 50% per trade — pathological
            max_leverage=1.0,
            min_confidence_score=0.0,
            min_risk_reward_net=0.0,
            min_notional_usd=0.0,
        ))
        # equity 100 * 0.5 = $50 risk; per-unit 3 → qty 16.667; notional 1683
        # Margin at 1x = 1683 > equity 100 → insufficient.
        d = g.evaluate(_signal(), **_ok_kwargs(equity_usd=100.0))
        assert d.reason == "insufficient_margin"


class TestOrderPlan:
    def test_as_dict_roundtrip(self):
        plan = OrderPlan(
            coin="X", side="LONG", entry_low=1.0, entry_high=2.0, entry_mid=1.5,
            stop_loss=0.5, take_profit_1=2.0, take_profit_2=3.0, take_profit_3=4.0,
            leverage=5.0, quantity=1.0, notional_usd=1.5, risk_usd=1.0,
            margin_required_usd=0.3,
        )
        d = plan.as_dict()
        assert d["coin"] == "X"
        assert math.isclose(d["entry_mid"], 1.5)
        assert d["tp_split"] == [0.4, 0.4, 0.2]

"""Unit tests for the fees & funding cost engine."""
import math

import pytest

from app.engines.fees_engine import (
    TradeCostInputs,
    adjust_rr_for_costs,
    bars_to_funding_periods,
    compute_trade_costs,
    funding_drag_pct,
    r_multiple,
    round_trip_fee_pct,
)


class TestRoundTripFeePct:
    def test_two_takers_equals_double_per_side(self):
        # 4 bps per side, both sides taker → 0.08% round-trip
        assert round_trip_fee_pct(4.0, taker_count=2) == pytest.approx(0.08)

    def test_zero_takers_uses_half_fee_per_side(self):
        # both maker fills, maker = half of taker fee → 4*0.5*2 = 4 bps total = 0.04%
        assert round_trip_fee_pct(4.0, taker_count=0) == pytest.approx(0.04)

    def test_one_taker_one_maker(self):
        # 1 taker @ 4bps + 1 maker @ 2bps = 6 bps round-trip = 0.06%
        assert round_trip_fee_pct(4.0, taker_count=1) == pytest.approx(0.06)

    def test_negative_fee_treated_as_zero(self):
        assert round_trip_fee_pct(-1.0, taker_count=2) == 0.0

    def test_taker_count_clamped(self):
        # taker_count > 2 should clamp to 2
        assert round_trip_fee_pct(4.0, taker_count=5) == round_trip_fee_pct(4.0, taker_count=2)


class TestFundingDrag:
    def test_long_pays_positive_funding(self):
        # 0.01% per period × 3 periods = 0.03% notional cost for LONG
        assert funding_drag_pct(0.0001, 3, "LONG") == pytest.approx(0.03)

    def test_short_earns_positive_funding(self):
        assert funding_drag_pct(0.0001, 3, "SHORT") == pytest.approx(-0.03)

    def test_zero_periods_no_drag(self):
        assert funding_drag_pct(0.0001, 0, "LONG") == 0.0

    def test_negative_funding_long_earns(self):
        # funding rate negative → shorts pay longs → LONG earns
        assert funding_drag_pct(-0.0002, 2, "LONG") == pytest.approx(-0.04)


class TestBarsToFundingPeriods:
    def test_eight_hours_is_one_period(self):
        # 8 × 1h bars = 1 funding period
        assert bars_to_funding_periods(8, 60) == pytest.approx(1.0)

    def test_partial_period(self):
        # 4h held = 0.5 periods
        assert bars_to_funding_periods(4, 60) == pytest.approx(0.5)

    def test_zero_bars(self):
        assert bars_to_funding_periods(0, 60) == 0.0


class TestRMultiple:
    def test_one_R_winner(self):
        # +2% with 2% SL = 1R win
        assert r_multiple(2.0, 2.0) == pytest.approx(1.0)

    def test_minus_one_R_loser(self):
        assert r_multiple(-2.0, 2.0) == pytest.approx(-1.0)

    def test_three_R_winner(self):
        assert r_multiple(6.0, 2.0) == pytest.approx(3.0)

    def test_zero_sl_protected(self):
        assert r_multiple(5.0, 0) == 0.0


class TestComputeTradeCosts:
    """End-to-end fee + funding accounting on realistic trades."""

    def test_long_winner_net_account_pct_after_fees(self):
        # Entry 100, exit 106, SL 98 → +6% gross, 2% SL → 3R
        # 1% per-trade risk → 3% account return gross
        # Round-trip fee 0.08% / sl_pct 2 * 1 = 0.04% drag
        # Held 8 bars × 1h = 1 funding period × 0.01% / 2 * 1 = 0.005% drag
        # Net = 3 - 0.04 - 0.005 = 2.955%
        b = compute_trade_costs(TradeCostInputs(
            entry_price=100, exit_price=106, stop_loss_price=98,
            side="LONG", bars_held=8, bar_minutes=60,
            risk_per_trade_pct=1.0, fee_bps_per_side=4.0,
            funding_rate_per_period=0.0001,
        ))
        assert b.gross_pnl_pct == pytest.approx(6.0)
        assert b.sl_pct == pytest.approx(2.0)
        assert b.R_multiple == pytest.approx(3.0)
        assert b.gross_account_pct == pytest.approx(3.0)
        assert b.fee_drag_account_pct == pytest.approx(0.04)
        assert b.funding_drag_account_pct == pytest.approx(0.005)
        assert b.net_account_pct == pytest.approx(3.0 - 0.04 - 0.005)

    def test_long_sl_loser_is_minus_1R_minus_costs(self):
        # SL hit on LONG: gross = -2%, R = -1, gross_acct = -1%
        # Fees still apply on loss → net is more negative
        b = compute_trade_costs(TradeCostInputs(
            entry_price=100, exit_price=98, stop_loss_price=98,
            side="LONG", bars_held=4, bar_minutes=60,
            risk_per_trade_pct=1.0, fee_bps_per_side=4.0,
        ))
        assert b.R_multiple == pytest.approx(-1.0)
        assert b.gross_account_pct == pytest.approx(-1.0)
        assert b.net_account_pct < -1.0  # losing trade pays fees too
        assert b.fee_drag_account_pct > 0

    def test_short_winner_pnl_is_positive(self):
        # SHORT 100, exit 96, SL 102 → +4% gross, SL 2% → 2R, +2% account
        b = compute_trade_costs(TradeCostInputs(
            entry_price=100, exit_price=96, stop_loss_price=102,
            side="SHORT", bars_held=8, bar_minutes=60,
            risk_per_trade_pct=1.0, fee_bps_per_side=4.0,
            funding_rate_per_period=0.0,
        ))
        assert b.gross_pnl_pct == pytest.approx(4.0)
        assert b.R_multiple == pytest.approx(2.0)
        assert b.gross_account_pct == pytest.approx(2.0)
        # Funding 0 → only fee drag
        assert b.net_account_pct == pytest.approx(2.0 - 0.04)

    def test_short_sl_loser_is_negative_not_double_negated(self):
        # The pre-fix bug double-negated this. Verify it's plain -1R.
        b = compute_trade_costs(TradeCostInputs(
            entry_price=100, exit_price=102, stop_loss_price=102,
            side="SHORT", bars_held=2, bar_minutes=60,
            risk_per_trade_pct=1.0, fee_bps_per_side=4.0,
            funding_rate_per_period=0.0,
        ))
        assert b.gross_pnl_pct == pytest.approx(-2.0)
        assert b.R_multiple == pytest.approx(-1.0)
        assert b.gross_account_pct == pytest.approx(-1.0)
        # Net is more negative due to fees, not less.
        assert b.net_account_pct < b.gross_account_pct

    def test_short_earns_funding_when_rate_positive(self):
        # Positive funding rate ⇒ shorts get paid; net acct should INCREASE.
        long_b = compute_trade_costs(TradeCostInputs(
            entry_price=100, exit_price=100, stop_loss_price=98,
            side="LONG", bars_held=8, bar_minutes=60,
            risk_per_trade_pct=1.0, fee_bps_per_side=0.0,
            funding_rate_per_period=0.0001,
        ))
        short_b = compute_trade_costs(TradeCostInputs(
            entry_price=100, exit_price=100, stop_loss_price=102,
            side="SHORT", bars_held=8, bar_minutes=60,
            risk_per_trade_pct=1.0, fee_bps_per_side=0.0,
            funding_rate_per_period=0.0001,
        ))
        # Both flat-price trades. LONG pays funding, SHORT earns.
        assert long_b.net_account_pct < 0
        assert short_b.net_account_pct > 0
        # Symmetric magnitude.
        assert long_b.net_account_pct == pytest.approx(-short_b.net_account_pct)

    def test_zero_entry_returns_zero(self):
        b = compute_trade_costs(TradeCostInputs(
            entry_price=0, exit_price=100, stop_loss_price=98,
            side="LONG", bars_held=1, bar_minutes=60,
        ))
        assert b.net_account_pct == 0


class TestAdjustRRForCosts:
    def test_2R_setup_with_fees_drops_below_2(self):
        # 1:2 setup, 2% SL, 0.04% taker × 2 + 0.01% funding = ~0.09% drag
        gross = 2.0
        adj = adjust_rr_for_costs(
            gross_rr=gross, sl_pct=2.0, fee_bps_per_side=4.0,
            taker_count=2, funding_rate_per_period=0.0001,
            expected_funding_periods=1.0,
        )
        assert 0 < adj < gross

    def test_zero_inputs(self):
        assert adjust_rr_for_costs(0, 2.0) == 0
        assert adjust_rr_for_costs(2.0, 0) == 0

    def test_drag_eliminates_thin_setup(self):
        # 1:0.5 setup with 0.1% SL — fees alone should consume reward.
        adj = adjust_rr_for_costs(
            gross_rr=0.5, sl_pct=0.1, fee_bps_per_side=4.0,
            taker_count=2, funding_rate_per_period=0.0,
            expected_funding_periods=0.0,
        )
        # 0.5 × 0.1 = 0.05% reward, 0.08% drag → net negative → clamped to 0
        assert adj == 0.0

"""
Regression tests for backtest math fixes (PR 1 — foundation fixes).

These tests deliberately do NOT touch Binance — they call the pure helpers
inside `backtest_engine` with synthetic candles to verify:

  1. The equity curve compounds *account-percent* returns, not the
     1/10,000-scaled garbage the old code produced.
  2. SHORT-side stop-out outcomes have plain negative pnl (no double-negation).
  3. Fee + funding deductions show up in `net_account_pct`.
"""
import pytest

from app.engines.backtest_engine import (
    _build_trade_record,
    _calculate_backtest_stats,
    _simulate_trade_outcome,
)


def _candle(ts: int, o: float, h: float, l: float, c: float, v: float = 1000) -> dict:
    return {"timestamp": ts, "open": o, "high": h, "low": l, "close": c, "volume": v}


class TestSimulateTradeOutcome:
    def test_long_hits_tp1_first(self):
        future = [_candle(i, 100, 102, 99.5, 101) for i in range(5)]
        out = _simulate_trade_outcome("LONG", 100, 98, 102, 104, 106, future)
        assert out["result"] == "TP1"
        assert out["exit_price"] == 102
        assert out["pnl_pct"] == pytest.approx(2.0)
        assert out["bars_held"] == 1

    def test_long_hits_sl(self):
        future = [_candle(i, 100, 100.5, 97, 97.5) for i in range(5)]
        out = _simulate_trade_outcome("LONG", 100, 98, 102, 104, 106, future)
        assert out["result"] == "SL"
        assert out["exit_price"] == 98
        assert out["pnl_pct"] == pytest.approx(-2.0)

    def test_short_hits_tp1(self):
        # Price drops, SHORT wins.
        future = [_candle(i, 100, 100.5, 97.5, 98) for i in range(5)]
        out = _simulate_trade_outcome("SHORT", 100, 102, 98, 96, 94, future)
        assert out["result"] == "TP1"
        assert out["pnl_pct"] == pytest.approx(2.0)  # positive — winning short

    def test_short_hits_sl_pnl_is_plain_negative(self):
        # Pre-fix bug: SHORT SL was double-negated. Verify it's a plain negative.
        future = [_candle(i, 100, 102.5, 99.5, 102) for i in range(5)]
        out = _simulate_trade_outcome("SHORT", 100, 102, 98, 96, 94, future)
        assert out["result"] == "SL"
        assert out["exit_price"] == 102
        assert out["pnl_pct"] == pytest.approx(-2.0)  # NOT +2 (double-neg bug)

    def test_expired_returns_last_close(self):
        # No TP/SL hit in any candle.
        future = [_candle(i, 100, 100.5, 99.5, 100.2) for i in range(5)]
        out = _simulate_trade_outcome("LONG", 100, 98, 102, 104, 106, future)
        assert out["result"] == "EXPIRED"
        assert out["bars_held"] == 5


class TestBuildTradeRecord:
    def _common_kwargs(self):
        return dict(
            symbol="BTCUSDT", signal_type="LONG", entry_price=100, stop_loss=98,
            tp1=102, tp2=104, tp3=106, rr=2.0, candle_index=10, timestamp=0,
            timeframe="1h", risk_per_trade_pct=1.0,
            include_costs=True, fee_bps_per_side=4.0, taker_count=2,
            funding_rate_per_period=0.0001,
        )

    def test_winner_has_positive_net_account_pct(self):
        outcome = {"result": "TP2", "exit_price": 104, "pnl_pct": 4.0, "bars_held": 8}
        rec = _build_trade_record(outcome=outcome, **self._common_kwargs())
        # 1R win → 1% gross account; minus tiny fee/funding drag.
        assert rec["R_multiple"] == pytest.approx(2.0)
        assert rec["gross_account_pct"] == pytest.approx(2.0)
        assert rec["net_account_pct"] < rec["gross_account_pct"]
        assert rec["net_account_pct"] > 1.9  # drag is small

    def test_loser_net_is_more_negative(self):
        outcome = {"result": "SL", "exit_price": 98, "pnl_pct": -2.0, "bars_held": 4}
        rec = _build_trade_record(outcome=outcome, **self._common_kwargs())
        assert rec["R_multiple"] == pytest.approx(-1.0)
        assert rec["gross_account_pct"] == pytest.approx(-1.0)
        # Fees are paid on losers too → net < -1
        assert rec["net_account_pct"] < -1.0

    def test_include_costs_false_means_no_drag(self):
        kwargs = self._common_kwargs()
        kwargs["include_costs"] = False
        outcome = {"result": "TP2", "exit_price": 104, "pnl_pct": 4.0, "bars_held": 8}
        rec = _build_trade_record(outcome=outcome, **kwargs)
        assert rec["fee_drag_account_pct"] == pytest.approx(0.0)
        assert rec["funding_drag_account_pct"] == pytest.approx(0.0)
        assert rec["net_account_pct"] == pytest.approx(rec["gross_account_pct"])


class TestCalculateBacktestStats:
    def test_empty_trades_returns_starting_balance(self):
        stats = _calculate_backtest_stats([], starting_balance=1000.0,
                                          risk_per_trade_pct=1.0)
        assert stats["total_signals"] == 0
        assert stats["ending_balance"] == 1000.0

    def test_equity_curve_compounds_correctly(self):
        # 3 trades: +2%, +2%, -1% → 1000 × 1.02 × 1.02 × 0.99 = 1029.796
        trades = [
            {"net_account_pct": 2.0, "gross_account_pct": 2.0,
             "fee_drag_account_pct": 0.0, "funding_drag_account_pct": 0.0,
             "rr": 2.0, "R_multiple": 2.0, "result": "TP2"},
            {"net_account_pct": 2.0, "gross_account_pct": 2.0,
             "fee_drag_account_pct": 0.0, "funding_drag_account_pct": 0.0,
             "rr": 2.0, "R_multiple": 2.0, "result": "TP2"},
            {"net_account_pct": -1.0, "gross_account_pct": -1.0,
             "fee_drag_account_pct": 0.0, "funding_drag_account_pct": 0.0,
             "rr": 2.0, "R_multiple": -1.0, "result": "SL"},
        ]
        stats = _calculate_backtest_stats(trades, starting_balance=1000.0,
                                          risk_per_trade_pct=1.0)
        # 1000 × 1.02 × 1.02 × 0.99 = 1030.0
        assert stats["ending_balance"] == pytest.approx(1030.0, abs=0.01)
        assert stats["win_count"] == 2
        assert stats["loss_count"] == 1
        assert stats["win_rate"] == pytest.approx(66.7, abs=0.1)
        # Pre-fix bug: ending balance would have been ~1000.0003
        # because compounding scaled by 1/10,000.

    def test_old_bug_would_have_produced_flat_equity(self):
        """
        Sanity check: the pre-fix formula `balance * (1 + pnl_pct/100 * 0.01)`
        on a +6% winner produced balance change of 0.0006%, not 6%.
        Demonstrate that our new code does NOT do this.
        """
        trades = [
            {"net_account_pct": 6.0, "gross_account_pct": 6.0,
             "fee_drag_account_pct": 0.0, "funding_drag_account_pct": 0.0,
             "rr": 3.0, "R_multiple": 3.0, "result": "TP3"},
        ]
        stats = _calculate_backtest_stats(trades, starting_balance=1000.0,
                                          risk_per_trade_pct=1.0)
        # Should be 1060.0, not 1000.0006 (which is what the old bug produced).
        assert stats["ending_balance"] == pytest.approx(1060.0, abs=0.01)
        assert stats["ending_balance"] > 1010  # rules out the 1/10000 bug

    def test_max_drawdown_calculated(self):
        trades = [
            {"net_account_pct": 5.0, "gross_account_pct": 5, "fee_drag_account_pct": 0,
             "funding_drag_account_pct": 0, "rr": 2.0, "R_multiple": 5, "result": "TP3"},
            {"net_account_pct": -3.0, "gross_account_pct": -3, "fee_drag_account_pct": 0,
             "funding_drag_account_pct": 0, "rr": 2.0, "R_multiple": -1, "result": "SL"},
            {"net_account_pct": -2.0, "gross_account_pct": -2, "fee_drag_account_pct": 0,
             "funding_drag_account_pct": 0, "rr": 2.0, "R_multiple": -1, "result": "SL"},
        ]
        stats = _calculate_backtest_stats(trades, starting_balance=1000.0,
                                          risk_per_trade_pct=1.0)
        # Peak = 1050, trough = 1050 × 0.97 × 0.98 = ~998.1
        # DD = (1050 - 998.1) / 1050 * 100 ≈ 4.94%
        assert 4.5 < stats["max_drawdown_pct"] < 5.5

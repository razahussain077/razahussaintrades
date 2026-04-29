"""Unit tests for walk-forward harness aggregation logic."""
import pytest

from app.engines.walkforward_engine import _aggregate, _slice_windows


def _make_window(total_pnl_pct: float, total_signals: int = 5,
                 max_dd: float = 5.0, profit_factor: float = 1.5,
                 avg_R: float = 0.5, win_count: int = 3) -> dict:
    return {
        "start_ts": 0, "end_ts": 1, "trade_count": total_signals,
        "stats": {
            "total_signals": total_signals,
            "win_count": win_count,
            "total_pnl_pct": total_pnl_pct,
            "max_drawdown_pct": max_dd,
            "profit_factor": profit_factor,
            "avg_R_multiple": avg_R,
        },
    }


class TestSliceWindows:
    def test_empty_when_too_short(self):
        assert _slice_windows([{"timestamp": 0}], bars_per_window=10) == []

    def test_exact_fit(self):
        candles = [{"timestamp": i} for i in range(30)]
        windows = _slice_windows(candles, bars_per_window=10)
        assert len(windows) == 3
        assert all(len(w) == 10 for w in windows)
        # Non-overlapping
        assert windows[0][-1]["timestamp"] == 9
        assert windows[1][0]["timestamp"] == 10

    def test_remainder_dropped(self):
        candles = [{"timestamp": i} for i in range(35)]
        windows = _slice_windows(candles, bars_per_window=10)
        assert len(windows) == 3  # last 5 dropped
        assert windows[-1][-1]["timestamp"] == 29


class TestAggregate:
    def test_empty_returns_starting_balance(self):
        agg = _aggregate([], starting_balance=1000)
        assert agg["window_count"] == 0
        assert agg["ending_balance"] == 1000
        assert agg["consistency_score"] == 0.0

    def test_consistency_score_counts_profitable_windows(self):
        windows = [
            _make_window(total_pnl_pct=2.0),   # profitable
            _make_window(total_pnl_pct=1.0),   # profitable
            _make_window(total_pnl_pct=-1.5),  # losing
            _make_window(total_pnl_pct=-0.5),  # losing
        ]
        agg = _aggregate(windows, starting_balance=1000)
        # 2 / 4 windows profitable
        assert agg["consistency_score"] == pytest.approx(0.5)
        assert agg["window_count"] == 4

    def test_balance_compounds_across_windows(self):
        windows = [
            _make_window(total_pnl_pct=10.0),  # +10%
            _make_window(total_pnl_pct=10.0),  # +10%
        ]
        agg = _aggregate(windows, starting_balance=1000)
        # 1000 × 1.10 × 1.10 = 1210
        assert agg["ending_balance"] == pytest.approx(1210, abs=0.5)
        assert agg["total_return_pct"] == pytest.approx(21.0, abs=0.1)

    def test_max_drawdown_is_max_across_windows(self):
        windows = [
            _make_window(total_pnl_pct=2.0, max_dd=3.0),
            _make_window(total_pnl_pct=-1.0, max_dd=12.5),
            _make_window(total_pnl_pct=0.5, max_dd=5.0),
        ]
        agg = _aggregate(windows, starting_balance=1000)
        assert agg["max_drawdown_pct"] == pytest.approx(12.5)

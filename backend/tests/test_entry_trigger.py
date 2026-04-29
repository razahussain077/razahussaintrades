"""Tests for the lower-timeframe entry trigger (PR5)."""
from app.analysis.entry_trigger import (
    detect_sweep_reclaim,
    htf_bias,
    htf_bias_aligned,
    evaluate_entry_refinement,
)


def _candle(low: float, high: float, close: float, open_: float | None = None, ts: int = 0):
    return {
        "low": low, "high": high, "close": close,
        "open": open_ if open_ is not None else close, "timestamp": ts,
    }


# ---------------------------------------------------------------------------
# detect_sweep_reclaim
# ---------------------------------------------------------------------------

class TestSweepReclaim:
    def test_long_trigger_fires_on_sweep_then_reclaim(self):
        # 24 bars of consolidation around 100 with low ~99, then 3-bar tail:
        #   bar -3: wick to 98 (sweep below pivot 99), close 99.5
        #   bar -2: close 100
        #   bar -1: close 100.5  ← strictly above pivot_low → reclaim
        candles = [_candle(99.5, 100.5, 100, ts=i) for i in range(24)]
        candles += [
            _candle(98.0, 100.0, 99.5, ts=24),
            _candle(99.4, 100.5, 100.0, ts=25),
            _candle(99.7, 101.0, 100.5, ts=26),
        ]
        out = detect_sweep_reclaim(candles, "LONG", lookback=24, reclaim_bars=3)
        assert out["triggered"] is True
        assert out["pivot_low"] == 99.5
        assert out["sweep_low"] == 98.0
        assert out["reclaim_close"] == 100.5

    def test_long_no_trigger_when_close_stays_below(self):
        candles = [_candle(99.5, 100.5, 100, ts=i) for i in range(24)]
        candles += [
            _candle(98.0, 99.0, 98.5, ts=24),
            _candle(97.5, 99.0, 98.7, ts=25),
            _candle(98.0, 99.4, 99.0, ts=26),  # still < pivot_low (99.5)
        ]
        out = detect_sweep_reclaim(candles, "LONG", lookback=24, reclaim_bars=3)
        assert out["triggered"] is False
        assert out["reason"] == "no_reclaim"

    def test_long_no_trigger_when_no_sweep(self):
        candles = [_candle(99.5, 100.5, 100, ts=i) for i in range(24)]
        candles += [
            _candle(99.6, 100.5, 100.2, ts=24),
            _candle(99.7, 100.5, 100.3, ts=25),
            _candle(99.8, 100.5, 100.1, ts=26),
        ]
        out = detect_sweep_reclaim(candles, "LONG", lookback=24, reclaim_bars=3)
        assert out["triggered"] is False
        assert out["reason"] == "no_sweep"

    def test_short_trigger_fires(self):
        candles = [_candle(99.5, 100.5, 100, ts=i) for i in range(24)]
        candles += [
            _candle(100.0, 102.0, 101.5, ts=24),  # wick above pivot_high 100.5
            _candle(99.5, 100.4, 100.0, ts=25),
            _candle(99.0, 100.4, 99.7, ts=26),    # close below pivot_high
        ]
        out = detect_sweep_reclaim(candles, "SHORT", lookback=24, reclaim_bars=3)
        assert out["triggered"] is True
        assert out["pivot_high"] == 100.5
        assert out["sweep_high"] == 102.0

    def test_insufficient_candles(self):
        candles = [_candle(99.5, 100.5, 100, ts=i) for i in range(5)]
        out = detect_sweep_reclaim(candles, "LONG")
        assert out["triggered"] is False
        assert out["have_data"] is False


# ---------------------------------------------------------------------------
# htf_bias
# ---------------------------------------------------------------------------

class TestHtfBias:
    def test_uptrend_returns_bull(self):
        candles = [_candle(p - 0.5, p + 0.5, p, ts=i) for i, p in enumerate(range(100, 140))]
        out = htf_bias(candles)
        assert out["have_data"] is True
        assert out["bias"] == "BULL"
        assert out["strength"] > 0

    def test_downtrend_returns_bear(self):
        candles = [_candle(p - 0.5, p + 0.5, p, ts=i) for i, p in enumerate(range(140, 100, -1))]
        out = htf_bias(candles)
        assert out["bias"] == "BEAR"

    def test_short_series_returns_neutral_no_data(self):
        candles = [_candle(99.5, 100.5, 100, ts=i) for i in range(10)]
        out = htf_bias(candles)
        assert out["have_data"] is False
        assert out["bias"] == "NEUTRAL"


class TestHtfAlignment:
    def test_long_aligned_when_all_bull(self):
        biases = [{"bias": "BULL"}, {"bias": "BULL"}]
        aligned, n = htf_bias_aligned("LONG", biases)
        assert aligned and n == 2

    def test_long_not_aligned_when_one_bear(self):
        biases = [{"bias": "BULL"}, {"bias": "BEAR"}]
        aligned, _ = htf_bias_aligned("LONG", biases)
        assert aligned is False

    def test_long_not_aligned_when_all_neutral(self):
        biases = [{"bias": "NEUTRAL"}, {"bias": "NEUTRAL"}]
        aligned, _ = htf_bias_aligned("LONG", biases)
        assert aligned is False


# ---------------------------------------------------------------------------
# evaluate_entry_refinement
# ---------------------------------------------------------------------------

class TestEvaluateEntryRefinement:
    def _bull_setup(self):
        trigger = [_candle(99.5, 100.5, 100, ts=i) for i in range(24)]
        trigger += [
            _candle(98.0, 100.0, 99.5, ts=24),
            _candle(99.4, 100.5, 100.0, ts=25),
            _candle(99.7, 101.0, 100.5, ts=26),
        ]
        htf = [_candle(p - 0.5, p + 0.5, p, ts=i) for i, p in enumerate(range(100, 140))]
        return trigger, htf

    def test_full_alignment_yields_positive_bonus(self):
        trigger, htf = self._bull_setup()
        out = evaluate_entry_refinement("LONG", trigger, [htf, htf])
        assert out["triggered"] is True
        assert out["htf_aligned"] is True
        assert out["bonus"] == 5

    def test_trigger_without_htf_alignment_zero(self):
        trigger, _ = self._bull_setup()
        bear = [_candle(p - 0.5, p + 0.5, p, ts=i) for i, p in enumerate(range(140, 100, -1))]
        out = evaluate_entry_refinement("LONG", trigger, [bear, bear])
        assert out["triggered"] is True
        assert out["htf_aligned"] is False
        assert out["bonus"] == 0

    def test_neither_aligned_yields_negative_bonus(self):
        flat_trigger = [_candle(99.5, 100.5, 100, ts=i) for i in range(30)]
        flat_htf = [_candle(99.5, 100.5, 100, ts=i) for i in range(40)]
        out = evaluate_entry_refinement("LONG", flat_trigger, [flat_htf, flat_htf])
        assert out["triggered"] is False
        assert out["htf_aligned"] is False
        assert out["bonus"] == -5

"""Unit tests for the order-flow engine (CVD, large prints, divergence)."""
import pytest

from app.engines.orderflow_engine import (
    detect_cvd_divergence,
    detect_large_prints,
    get_cvd_snapshot,
    record_trade,
    reset_for_tests,
)


@pytest.fixture(autouse=True)
def _clear_buffers():
    reset_for_tests()
    yield
    reset_for_tests()


class TestRecordTradeAndCVD:
    def test_aggressive_buy_increments_cvd(self):
        # is_buyer_maker=False ⇒ buyer was taker ⇒ aggressive buy ⇒ +delta
        record_trade("BTCUSDT", 1_000, 100.0, 1.0, is_buyer_maker=False)
        snap = get_cvd_snapshot("BTCUSDT", now_ms=1_000)
        assert snap["have_data"] is True
        assert snap["cvd_1m"] == pytest.approx(100.0)
        assert snap["delta_1m_normalized"] == pytest.approx(1.0)

    def test_aggressive_sell_decrements_cvd(self):
        record_trade("BTCUSDT", 1_000, 100.0, 1.0, is_buyer_maker=True)
        snap = get_cvd_snapshot("BTCUSDT", now_ms=1_000)
        assert snap["cvd_1m"] == pytest.approx(-100.0)
        assert snap["delta_1m_normalized"] == pytest.approx(-1.0)

    def test_balanced_flow_normalized_zero(self):
        record_trade("BTCUSDT", 1_000, 100.0, 1.0, is_buyer_maker=False)
        record_trade("BTCUSDT", 1_001, 100.0, 1.0, is_buyer_maker=True)
        snap = get_cvd_snapshot("BTCUSDT", now_ms=1_001)
        assert snap["cvd_1m"] == pytest.approx(0.0)
        assert snap["delta_1m_normalized"] == pytest.approx(0.0)

    def test_zero_qty_or_price_ignored(self):
        record_trade("BTCUSDT", 1_000, 0.0, 1.0, is_buyer_maker=False)
        record_trade("BTCUSDT", 1_000, 100.0, 0.0, is_buyer_maker=False)
        snap = get_cvd_snapshot("BTCUSDT", now_ms=1_000)
        assert snap["have_data"] is False

    def test_window_separation(self):
        # Trades 30s ago belong to 1m window but not to a hypothetical 10s window
        # (we don't expose 10s, but use the API). Verify 1m vs 5m vs 15m.
        # Trade 1: 6 minutes ago. Trade 2: 30s ago.
        record_trade("BTCUSDT", 0, 100.0, 1.0, is_buyer_maker=False)        # +100
        record_trade("BTCUSDT", 6 * 60_000 + 30_000, 100.0, 1.0,
                     is_buyer_maker=True)                                    # -100
        # now_ms = 6.5min after first trade. 1m window contains only the
        # second trade. 15m window contains both → net 0.
        now = 6 * 60_000 + 30_000
        snap = get_cvd_snapshot("BTCUSDT", now_ms=now)
        assert snap["cvd_1m"] == pytest.approx(-100.0)
        assert snap["cvd_5m"] == pytest.approx(-100.0)
        assert snap["cvd_15m"] == pytest.approx(0.0)


class TestLargePrints:
    def test_below_min_trades_returns_no_data(self):
        for i in range(20):
            record_trade("BTCUSDT", 1000 + i, 100.0, 0.1, is_buyer_maker=False)
        # Need >= 50 trades for stats to be meaningful.
        bursts = detect_large_prints("BTCUSDT")
        assert bursts["have_data"] is False

    def test_detects_large_aggressive_buy(self):
        # 60 small buys + 1 huge buy.
        for i in range(60):
            record_trade("BTCUSDT", 1000 + i, 100.0, 0.1, is_buyer_maker=False)  # $10 each
        record_trade("BTCUSDT", 1100, 100.0, 100.0, is_buyer_maker=False)        # $10,000
        bursts = detect_large_prints("BTCUSDT", multiplier=4.0, now_ms=2000)
        assert bursts["have_data"] is True
        assert bursts["large_buy_count"] >= 1
        assert bursts["large_buy_volume"] > 1000


class TestCVDDivergence:
    def _sweep_and_reclaim_candles(self, lookback=20):
        # Construct 20 1m candles where price makes a LL late but CVD HL.
        # First 10 bars: down to 95.
        # Bars 10-15: bounce.
        # Bars 15-19: dip below the prior low to 94.
        # Bars 0-9: lots of selling (CVD very negative at the prior low).
        # Bars 15-19: small selling (CVD higher at the new low).
        candles = []
        for i in range(lookback):
            ts_ms = i * 60_000
            if i < 10:
                low = 95 + (10 - i) * 0.2
                high = low + 0.5
            elif i < 15:
                low = 95 + (i - 10) * 0.4
                high = low + 0.5
            else:
                low = 94 + (i - 15) * 0.05
                high = low + 0.5
            candles.append({"timestamp": ts_ms, "low": low, "high": high,
                            "open": low + 0.1, "close": low + 0.2, "volume": 1000})
        return candles

    def test_bullish_divergence_detected(self):
        # Heavy selling at the FIRST low, light selling at the SECOND (lower) low.
        for i in range(10):
            ts = i * 60_000 + 30_000
            record_trade("BTCUSDT", ts, 95.0, 100.0, is_buyer_maker=True)  # big sell

        for i in range(15, 20):
            ts = i * 60_000 + 30_000
            record_trade("BTCUSDT", ts, 94.0, 1.0, is_buyer_maker=True)  # tiny sell

        candles = self._sweep_and_reclaim_candles(20)
        result = detect_cvd_divergence("BTCUSDT", candles, lookback_bars=20)
        assert result["have_data"] is True
        assert result["bullish_divergence"] is True
        assert result["bearish_divergence"] is False

    def test_no_divergence_with_uniform_flow(self):
        for i in range(20):
            ts = i * 60_000 + 30_000
            record_trade("BTCUSDT", ts, 100.0, 1.0, is_buyer_maker=False)
        candles = self._sweep_and_reclaim_candles(20)
        result = detect_cvd_divergence("BTCUSDT", candles, lookback_bars=20)
        # Either have_data False (all-zero) or no divergence. Both acceptable.
        assert not result.get("bullish_divergence")
        assert not result.get("bearish_divergence")

    def test_too_few_candles(self):
        candles = self._sweep_and_reclaim_candles(5)
        result = detect_cvd_divergence("BTCUSDT", candles, lookback_bars=20)
        assert result["have_data"] is False

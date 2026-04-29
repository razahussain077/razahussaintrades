"""
Order Flow Engine — Cumulative Volume Delta (CVD) tracking and divergences.

The engine maintains a rolling list of (timestamp, signed-quote-volume) tuples
per symbol where a positive number is aggressive buying (the buyer was the
TAKER) and a negative number is aggressive selling (the buyer was the MAKER).

CVD is the running sum: it's a non-stationary order-flow proxy that, when it
diverges from price, indicates absorption — the highest-EV order-flow signal
in this codebase, especially on liquidity sweeps.

Key features detected:
  * `cvd_1m`, `cvd_5m`, `cvd_15m`, `cvd_1h` — sums over the trailing window.
  * `bullish_divergence` — price made a lower low but CVD made a higher low
    (sellers exhausted; absorption).
  * `bearish_divergence` — price made a higher high but CVD made a lower high
    (buyers exhausted).
  * `large_print_burst` — abnormally large aggressive prints (≥ X * median)
    in the last minute, with directional bias.

This module is pure-state: the WebSocket consumer in `streams/aggtrade_stream.py`
calls `record_trade()` on every tick. Stats methods are O(N) over the window.
"""
from __future__ import annotations

import logging
import statistics
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Deque, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Trades older than this are pruned. 1h gives us up to "1h CVD" with margin.
_MAX_TRADE_AGE_MS = 90 * 60 * 1000  # 90 minutes
_MAX_TRADES_PER_SYMBOL = 50_000     # hard cap to bound memory


@dataclass
class _TradeBuffer:
    """Per-symbol rolling window of trades and per-bucket aggregates."""
    # (timestamp_ms, signed_quote_volume) tuples, oldest first.
    trades: Deque[Tuple[int, float]] = field(default_factory=deque)
    # Highest aggressive-buy print and lowest aggressive-sell print in last 1m,
    # tracked for "absorption" detection.
    last_close_price: float = 0.0
    last_trade_ms: int = 0


_buffers: Dict[str, _TradeBuffer] = defaultdict(_TradeBuffer)


def _prune(buf: _TradeBuffer, now_ms: int) -> None:
    """Drop trades older than `_MAX_TRADE_AGE_MS`."""
    cutoff = now_ms - _MAX_TRADE_AGE_MS
    while buf.trades and buf.trades[0][0] < cutoff:
        buf.trades.popleft()
    # Hard cap as well.
    while len(buf.trades) > _MAX_TRADES_PER_SYMBOL:
        buf.trades.popleft()


def record_trade(
    symbol: str,
    timestamp_ms: int,
    price: float,
    quantity: float,
    is_buyer_maker: bool,
) -> None:
    """
    Record a single aggregate trade tick.

    Binance aggTrade semantics: `m` (= isBuyerMaker) tells us which side was
    passive. If `m` is True → buyer was the maker → seller was aggressive →
    delta is NEGATIVE. If `m` is False → buyer was the taker → buyer was
    aggressive → delta is POSITIVE.
    """
    if price <= 0 or quantity <= 0:
        return
    quote_volume = price * quantity
    delta = -quote_volume if is_buyer_maker else +quote_volume
    buf = _buffers[symbol]
    buf.trades.append((timestamp_ms, delta))
    buf.last_close_price = price
    buf.last_trade_ms = timestamp_ms
    _prune(buf, timestamp_ms)


def _sum_window(buf: _TradeBuffer, window_ms: int, now_ms: int) -> float:
    cutoff = now_ms - window_ms
    return sum(d for ts, d in buf.trades if ts >= cutoff)


def _abs_volume_window(buf: _TradeBuffer, window_ms: int, now_ms: int) -> float:
    cutoff = now_ms - window_ms
    return sum(abs(d) for ts, d in buf.trades if ts >= cutoff)


def get_cvd_snapshot(symbol: str, now_ms: Optional[int] = None) -> Dict:
    """
    Return cumulative-volume-delta over standard windows for one symbol.

    All values are in USD-quote terms. Sign convention: positive = aggressive
    buying dominant; negative = aggressive selling dominant.
    """
    buf = _buffers.get(symbol)
    if not buf or not buf.trades:
        return {
            "symbol": symbol,
            "have_data": False,
            "cvd_1m": 0.0, "cvd_5m": 0.0, "cvd_15m": 0.0, "cvd_1h": 0.0,
            "delta_1m_normalized": 0.0,
            "trades_recorded": 0,
            "last_price": 0.0,
            "last_trade_at": None,
        }

    if now_ms is None:
        now_ms = max(buf.last_trade_ms, int(datetime.now(timezone.utc).timestamp() * 1000))

    cvd_1m = _sum_window(buf, 60_000, now_ms)
    cvd_5m = _sum_window(buf, 5 * 60_000, now_ms)
    cvd_15m = _sum_window(buf, 15 * 60_000, now_ms)
    cvd_1h = _sum_window(buf, 60 * 60_000, now_ms)
    abs_1m = _abs_volume_window(buf, 60_000, now_ms)
    delta_1m_normalized = cvd_1m / abs_1m if abs_1m > 0 else 0.0

    return {
        "symbol": symbol,
        "have_data": True,
        "cvd_1m": round(cvd_1m, 2),
        "cvd_5m": round(cvd_5m, 2),
        "cvd_15m": round(cvd_15m, 2),
        "cvd_1h": round(cvd_1h, 2),
        # In [-1, +1]: -1 = pure selling, +1 = pure buying in last minute.
        "delta_1m_normalized": round(delta_1m_normalized, 4),
        "trades_recorded": len(buf.trades),
        "last_price": buf.last_close_price,
        "last_trade_at": datetime.fromtimestamp(
            buf.last_trade_ms / 1000, tz=timezone.utc
        ).isoformat() if buf.last_trade_ms else None,
    }


def detect_large_prints(
    symbol: str,
    multiplier: float = 4.0,
    window_ms: int = 60_000,
    now_ms: Optional[int] = None,
) -> Dict:
    """
    Detect abnormally large aggressive prints in the last `window_ms`.

    Returns a count + dollar-volume tuple per side. A "large print" is one
    where |delta| ≥ multiplier × median(|delta| in the window).
    """
    buf = _buffers.get(symbol)
    if not buf or len(buf.trades) < 50:
        return {
            "symbol": symbol,
            "have_data": False,
            "large_buy_count": 0, "large_buy_volume": 0.0,
            "large_sell_count": 0, "large_sell_volume": 0.0,
            "threshold": 0.0,
        }
    if now_ms is None:
        now_ms = max(buf.last_trade_ms, int(datetime.now(timezone.utc).timestamp() * 1000))

    cutoff = now_ms - window_ms
    window_trades = [(ts, d) for ts, d in buf.trades if ts >= cutoff]
    if not window_trades:
        return {
            "symbol": symbol,
            "have_data": False,
            "large_buy_count": 0, "large_buy_volume": 0.0,
            "large_sell_count": 0, "large_sell_volume": 0.0,
            "threshold": 0.0,
        }

    abs_deltas = [abs(d) for _, d in window_trades]
    median = statistics.median(abs_deltas) if abs_deltas else 0
    threshold = max(median * multiplier, 1.0)

    lbc, lbv, lsc, lsv = 0, 0.0, 0, 0.0
    for _, d in window_trades:
        if abs(d) < threshold:
            continue
        if d > 0:
            lbc += 1
            lbv += d
        else:
            lsc += 1
            lsv += -d

    return {
        "symbol": symbol,
        "have_data": True,
        "large_buy_count": lbc,
        "large_buy_volume": round(lbv, 2),
        "large_sell_count": lsc,
        "large_sell_volume": round(lsv, 2),
        "threshold": round(threshold, 2),
    }


def detect_cvd_divergence(
    symbol: str,
    candles: List[Dict],
    lookback_bars: int = 20,
) -> Dict:
    """
    Detect bullish / bearish CVD divergence over the last `lookback_bars`
    1m candles. The candle list MUST be 1m bars in chronological order.

    Bullish divergence:  price LL but CVD HL → potential bottom.
    Bearish divergence:  price HH but CVD LH → potential top.

    The CVD per bar is reconstructed from the in-memory trade buffer using
    the bar's [open_time, close_time] range.
    """
    buf = _buffers.get(symbol)
    if not buf or len(candles) < lookback_bars:
        return {"symbol": symbol, "have_data": False,
                "bullish_divergence": False, "bearish_divergence": False}

    recent = candles[-lookback_bars:]
    cvd_per_bar: List[float] = []
    for c in recent:
        bar_start = int(c.get("timestamp", 0))
        bar_end = bar_start + 60_000
        delta = sum(d for ts, d in buf.trades if bar_start <= ts < bar_end)
        cvd_per_bar.append(delta)

    if not cvd_per_bar or all(v == 0 for v in cvd_per_bar):
        return {"symbol": symbol, "have_data": False,
                "bullish_divergence": False, "bearish_divergence": False}

    # Find the index of the local low / high in the recent window.
    low_idx = min(range(len(recent)), key=lambda i: recent[i]["low"])
    high_idx = max(range(len(recent)), key=lambda i: recent[i]["high"])

    # Compare with the prior swing low/high (first half of window vs second).
    half = len(recent) // 2
    prev_low_idx = min(range(half), key=lambda i: recent[i]["low"])
    prev_high_idx = max(range(half), key=lambda i: recent[i]["high"])

    bullish = (
        recent[low_idx]["low"] < recent[prev_low_idx]["low"]
        and cvd_per_bar[low_idx] > cvd_per_bar[prev_low_idx]
        and low_idx >= half
    )
    bearish = (
        recent[high_idx]["high"] > recent[prev_high_idx]["high"]
        and cvd_per_bar[high_idx] < cvd_per_bar[prev_high_idx]
        and high_idx >= half
    )

    return {
        "symbol": symbol,
        "have_data": True,
        "bullish_divergence": bullish,
        "bearish_divergence": bearish,
        "current_low": recent[low_idx]["low"],
        "prev_low": recent[prev_low_idx]["low"],
        "current_high": recent[high_idx]["high"],
        "prev_high": recent[prev_high_idx]["high"],
    }


def get_all_symbols_with_data() -> List[str]:
    return [s for s, b in _buffers.items() if b.trades]


def reset_for_tests(symbol: Optional[str] = None) -> None:
    """Clear in-memory buffers — used by tests only."""
    if symbol is None:
        _buffers.clear()
    else:
        _buffers.pop(symbol, None)


class OrderFlowEngine:
    """OO wrapper for callers that prefer DI-style imports."""

    def record_trade(self, *args, **kwargs) -> None:
        record_trade(*args, **kwargs)

    def get_cvd_snapshot(self, symbol: str) -> Dict:
        return get_cvd_snapshot(symbol)

    def detect_large_prints(self, symbol: str, **kwargs) -> Dict:
        return detect_large_prints(symbol, **kwargs)

    def detect_cvd_divergence(self, symbol: str, candles: List[Dict], **kwargs) -> Dict:
        return detect_cvd_divergence(symbol, candles, **kwargs)


orderflow_engine = OrderFlowEngine()

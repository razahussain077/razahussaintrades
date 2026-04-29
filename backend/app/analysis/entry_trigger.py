"""
Lower-timeframe entry trigger (PR5).

Detects "sweep + reclaim" patterns on a fast timeframe (5m / 15m) — a key
ICT-style trigger where price *fakes a breakout* below recent support
(or above resistance) and then closes back inside the prior range,
consuming the resting stop liquidity in the process.

For LONG entries:
    1. Find the lowest low of the prior `lookback` bars (excluding the most
       recent `reclaim_bars` candles).
    2. Within the most recent `reclaim_bars` candles, at least one bar must
       have wicked BELOW that low (the sweep).
    3. The most recent closed bar must close ABOVE that low (the reclaim).

For SHORT entries the same logic mirrors against the swing high.

Also exposes a simple HTF-bias check from 1h/4h candle slope and EMA20
relation, used as a confirmation gate.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def _ema(values: List[float], period: int) -> List[float]:
    if not values:
        return []
    k = 2 / (period + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(out[-1] + k * (v - out[-1]))
    return out


def detect_sweep_reclaim(
    candles: List[Dict],
    direction: str,
    lookback: int = 24,
    reclaim_bars: int = 3,
) -> Dict:
    """
    Detect a sweep + reclaim pattern on the supplied candle series.

    Args:
        candles: chronological list of dicts with keys
                 `low`, `high`, `close`, `open`, `timestamp`.
        direction: "LONG" or "SHORT".
        lookback: bars to scan for the swing pivot (excluding the reclaim window).
        reclaim_bars: tail window in which the sweep + reclaim must happen.
    """
    if direction not in ("LONG", "SHORT"):
        return {"have_data": False, "triggered": False, "reason": "invalid_direction"}
    if not candles or len(candles) < (lookback + reclaim_bars):
        return {"have_data": False, "triggered": False, "reason": "insufficient_candles"}

    pivot_window = candles[-(lookback + reclaim_bars):-reclaim_bars]
    tail = candles[-reclaim_bars:]
    last = tail[-1]

    if direction == "LONG":
        pivot_low = min(c["low"] for c in pivot_window)
        wicked_below = any(c["low"] < pivot_low for c in tail)
        last_close = float(last["close"])
        reclaimed = last_close > pivot_low
        triggered = bool(wicked_below and reclaimed)
        sweep_bar = next(
            (c for c in tail if c["low"] < pivot_low),
            None,
        )
        return {
            "have_data": True,
            "triggered": triggered,
            "direction": "LONG",
            "pivot_low": float(pivot_low),
            "sweep_low": float(sweep_bar["low"]) if sweep_bar else None,
            "reclaim_close": last_close,
            "bars_since_sweep": (
                len(tail) - tail.index(sweep_bar) - 1 if sweep_bar else None
            ),
            "reason": (
                "sweep_and_reclaim_long" if triggered
                else "no_sweep" if not wicked_below
                else "no_reclaim"
            ),
        }

    pivot_high = max(c["high"] for c in pivot_window)
    wicked_above = any(c["high"] > pivot_high for c in tail)
    last_close = float(last["close"])
    reclaimed = last_close < pivot_high
    triggered = bool(wicked_above and reclaimed)
    sweep_bar = next(
        (c for c in tail if c["high"] > pivot_high),
        None,
    )
    return {
        "have_data": True,
        "triggered": triggered,
        "direction": "SHORT",
        "pivot_high": float(pivot_high),
        "sweep_high": float(sweep_bar["high"]) if sweep_bar else None,
        "reclaim_close": last_close,
        "bars_since_sweep": (
            len(tail) - tail.index(sweep_bar) - 1 if sweep_bar else None
        ),
        "reason": (
            "sweep_and_reclaim_short" if triggered
            else "no_sweep" if not wicked_above
            else "no_reclaim"
        ),
    }


def htf_bias(candles: List[Dict], ema_period: int = 20) -> Dict:
    """
    Quick HTF-bias read from a single candle series.

    Bias is BULL if last close > EMA20 AND EMA20 slope is non-decreasing,
    BEAR if last close < EMA20 AND EMA20 slope is non-increasing,
    otherwise NEUTRAL. Returns a numeric strength in [0, 1] for use in
    weighting / aggregation.
    """
    if len(candles) < ema_period + 5:
        return {"have_data": False, "bias": "NEUTRAL", "strength": 0.0}
    closes = [float(c["close"]) for c in candles]
    ema = _ema(closes, ema_period)
    last_close = closes[-1]
    last_ema = ema[-1]
    slope = ema[-1] - ema[-5]

    if last_close > last_ema and slope >= 0:
        bias = "BULL"
    elif last_close < last_ema and slope <= 0:
        bias = "BEAR"
    else:
        bias = "NEUTRAL"

    distance = abs(last_close - last_ema) / max(last_ema, 1e-12)
    slope_strength = abs(slope) / max(last_ema, 1e-12)
    strength = float(min(1.0, distance * 50 + slope_strength * 50))

    return {
        "have_data": True,
        "bias": bias,
        "strength": round(strength, 3),
        "last_close": last_close,
        "last_ema": last_ema,
        "ema_slope": slope,
    }


def htf_bias_aligned(direction: str, biases: List[Dict]) -> Tuple[bool, int]:
    """Returns (aligned, agreeing_count) — alignment requires no disagreeing bias."""
    if direction not in ("LONG", "SHORT") or not biases:
        return False, 0
    target = "BULL" if direction == "LONG" else "BEAR"
    opposite = "BEAR" if direction == "LONG" else "BULL"

    has_opposite = any(b.get("bias") == opposite for b in biases)
    agreeing = sum(1 for b in biases if b.get("bias") == target)
    aligned = agreeing >= 1 and not has_opposite
    return aligned, agreeing


def evaluate_entry_refinement(
    direction: str,
    trigger_candles: List[Dict],
    htf_candle_sets: List[List[Dict]],
    lookback: int = 24,
    reclaim_bars: int = 3,
) -> Dict:
    """
    Top-level orchestrator used by signal_generator.

    Returns a dict with `triggered`, `htf_aligned`, `bonus`, `reason`,
    and the underlying `trigger` / `htf` payloads for diagnostics.
    """
    trigger = detect_sweep_reclaim(
        trigger_candles, direction,
        lookback=lookback, reclaim_bars=reclaim_bars,
    )
    biases = [htf_bias(c) for c in htf_candle_sets if c]
    aligned, agreeing = htf_bias_aligned(direction, biases)

    triggered = bool(trigger.get("triggered"))
    bonus = 0
    if triggered and aligned:
        bonus = 5
    elif (not triggered) and (not aligned):
        bonus = -5
    # mixed → 0

    if triggered and aligned:
        reason = "ltf_trigger + htf_bias aligned"
    elif triggered and not aligned:
        reason = "ltf_trigger fired but htf bias disagrees"
    elif aligned and not triggered:
        reason = f"htf bias aligned ({agreeing} TFs) but no ltf trigger yet"
    else:
        reason = "no ltf trigger and htf bias not aligned"

    return {
        "have_data": trigger.get("have_data") or any(b.get("have_data") for b in biases),
        "triggered": triggered,
        "htf_aligned": aligned,
        "htf_agreeing_count": agreeing,
        "bonus": bonus,
        "reason": reason,
        "trigger": trigger,
        "htf_biases": biases,
    }

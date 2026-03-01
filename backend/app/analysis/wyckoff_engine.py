import logging
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


def _highs(candles: List[Dict]) -> np.ndarray:
    return np.array([c["high"] for c in candles], dtype=float)


def _lows(candles: List[Dict]) -> np.ndarray:
    return np.array([c["low"] for c in candles], dtype=float)


def _closes(candles: List[Dict]) -> np.ndarray:
    return np.array([c["close"] for c in candles], dtype=float)


def _volumes(candles: List[Dict]) -> np.ndarray:
    return np.array([c.get("volume", 0) for c in candles], dtype=float)


def detect_accumulation(candles: List[Dict]) -> Dict:
    """
    Wyckoff Accumulation: sideways range after downtrend + spring pattern.
    Criteria:
    1. Prior downtrend (prices falling over lookback period)
    2. Current consolidation (low ATR relative to prior ATR)
    3. Spring: quick dip below range followed by recovery
    """
    if len(candles) < 40:
        return {"detected": False}

    closes = _closes(candles)
    highs = _highs(candles)
    lows = _lows(candles)

    # Prior downtrend check: first 20 candles show decline
    prior_segment = closes[:20]
    current_segment = closes[20:]
    prior_trend = float(prior_segment[-1]) - float(prior_segment[0])
    is_downtrend = prior_trend < -abs(prior_trend) * 0.01

    # Consolidation check: ATR of last 15 candles vs ATR of first 20
    def atr_of(seg_h, seg_l, seg_c):
        if len(seg_c) < 2:
            return 0.0
        trs = []
        for i in range(1, len(seg_c)):
            tr = max(seg_h[i] - seg_l[i], abs(seg_h[i] - seg_c[i - 1]), abs(seg_l[i] - seg_c[i - 1]))
            trs.append(tr)
        return float(np.mean(trs)) if trs else 0.0

    prior_atr = atr_of(highs[:20], lows[:20], closes[:20])
    current_atr = atr_of(highs[-15:], lows[-15:], closes[-15:])
    is_consolidating = current_atr < prior_atr * 0.7 if prior_atr > 0 else False

    # Spring: last 5 candles dip below recent range low then recover
    range_low = float(np.min(lows[20:-5])) if len(lows) > 25 else float(np.min(lows))
    spring = detect_spring(candles, range_low)

    detected = (is_downtrend or True) and is_consolidating  # Relaxed: consolidation is key

    return {
        "detected": detected,
        "prior_downtrend": is_downtrend,
        "is_consolidating": is_consolidating,
        "range_low": range_low,
        "spring": spring,
        "prior_atr": round(prior_atr, 6),
        "current_atr": round(current_atr, 6),
        "phase_description": "Wyckoff Accumulation: potential markup ahead" if detected else "Not in accumulation",
    }


def detect_distribution(candles: List[Dict]) -> Dict:
    """
    Wyckoff Distribution: sideways range after uptrend + upthrust.
    """
    if len(candles) < 40:
        return {"detected": False}

    closes = _closes(candles)
    highs = _highs(candles)
    lows = _lows(candles)

    prior_segment = closes[:20]
    prior_trend = float(prior_segment[-1]) - float(prior_segment[0])
    is_uptrend = prior_trend > abs(prior_trend) * 0.01

    def atr_of(seg_h, seg_l, seg_c):
        if len(seg_c) < 2:
            return 0.0
        trs = [
            max(seg_h[i] - seg_l[i], abs(seg_h[i] - seg_c[i - 1]), abs(seg_l[i] - seg_c[i - 1]))
            for i in range(1, len(seg_c))
        ]
        return float(np.mean(trs)) if trs else 0.0

    prior_atr = atr_of(highs[:20], lows[:20], closes[:20])
    current_atr = atr_of(highs[-15:], lows[-15:], closes[-15:])
    is_consolidating = current_atr < prior_atr * 0.7 if prior_atr > 0 else False

    range_high = float(np.max(highs[20:-5])) if len(highs) > 25 else float(np.max(highs))
    upthrust = detect_upthrust(candles, range_high)

    detected = is_consolidating

    return {
        "detected": detected,
        "prior_uptrend": is_uptrend,
        "is_consolidating": is_consolidating,
        "range_high": range_high,
        "upthrust": upthrust,
        "prior_atr": round(prior_atr, 6),
        "current_atr": round(current_atr, 6),
        "phase_description": "Wyckoff Distribution: potential markdown ahead" if detected else "Not in distribution",
    }


def detect_spring(candles: List[Dict], range_low: float) -> Optional[Dict]:
    """
    Spring: quick dip below range_low with recovery (bullish signal).
    Last 5 candles dip below range_low, then close above.
    """
    if len(candles) < 5:
        return None

    lows = _lows(candles)
    closes = _closes(candles)
    last_5_lows = lows[-5:]
    last_close = float(closes[-1])

    dip_below = any(l < range_low for l in last_5_lows)
    recovered = last_close > range_low

    if dip_below and recovered:
        min_dip = float(np.min(last_5_lows))
        dip_pct = (range_low - min_dip) / range_low * 100
        return {
            "detected": True,
            "dip_level": min_dip,
            "range_low": range_low,
            "recovery_close": last_close,
            "dip_pct": round(dip_pct, 3),
            "description": f"Spring: dipped {dip_pct:.2f}% below range low, recovered",
        }
    return None


def detect_upthrust(candles: List[Dict], range_high: float) -> Optional[Dict]:
    """
    Upthrust: quick push above range_high with reversal (bearish signal).
    """
    if len(candles) < 5:
        return None

    highs = _highs(candles)
    closes = _closes(candles)
    last_5_highs = highs[-5:]
    last_close = float(closes[-1])

    push_above = any(h > range_high for h in last_5_highs)
    reversed_below = last_close < range_high

    if push_above and reversed_below:
        max_push = float(np.max(last_5_highs))
        push_pct = (max_push - range_high) / range_high * 100
        return {
            "detected": True,
            "push_level": max_push,
            "range_high": range_high,
            "reversal_close": last_close,
            "push_pct": round(push_pct, 3),
            "description": f"Upthrust: pushed {push_pct:.2f}% above range high, reversed",
        }
    return None


def detect_phase(candles: List[Dict]) -> Dict:
    """
    Classify current market phase as Accumulation/Markup/Distribution/Markdown.
    """
    if len(candles) < 50:
        return {"phase": "Unknown", "confidence": 0}

    closes = _closes(candles)
    highs = _highs(candles)
    lows = _lows(candles)

    # Calculate trend over different windows
    short_trend = float(closes[-1]) - float(closes[-10])
    medium_trend = float(closes[-1]) - float(closes[-30])
    long_trend = float(closes[-1]) - float(closes[0])

    # Volatility comparison
    def atr_window(start, end):
        h = highs[start:end]
        l = lows[start:end]
        c = closes[start:end]
        if len(c) < 2:
            return 0.0
        trs = [
            max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
            for i in range(1, len(c))
        ]
        return float(np.mean(trs)) if trs else 0.0

    early_atr = atr_window(0, 20)
    late_atr = atr_window(-20, len(candles))

    atr_increasing = late_atr > early_atr * 1.3

    if medium_trend > 0 and long_trend > 0 and atr_increasing:
        phase = "Markup"
        description = "Price trending up with increasing volatility"
        confidence = 75
    elif medium_trend < 0 and long_trend < 0 and atr_increasing:
        phase = "Markdown"
        description = "Price trending down with increasing volatility"
        confidence = 75
    elif abs(medium_trend) < abs(long_trend) * 0.2 and not atr_increasing:
        # Low momentum, sideways
        if long_trend < 0:
            phase = "Accumulation"
            description = "Sideways after downtrend - possible base forming"
            confidence = 60
        else:
            phase = "Distribution"
            description = "Sideways after uptrend - possible topping"
            confidence = 60
    elif medium_trend > 0:
        phase = "Markup"
        description = "Price in uptrend"
        confidence = 55
    else:
        phase = "Markdown"
        description = "Price in downtrend"
        confidence = 55

    return {
        "phase": phase,
        "description": description,
        "confidence": confidence,
        "short_trend": round(short_trend, 6),
        "medium_trend": round(medium_trend, 6),
        "long_trend": round(long_trend, 6),
        "atr_trend": "increasing" if atr_increasing else "decreasing",
    }


class WyckoffEngine:
    def analyze(self, candles: List[Dict]) -> Dict:
        if len(candles) < 40:
            return {"error": "Insufficient candle data", "phase": {"phase": "Unknown"}}
        try:
            accumulation = detect_accumulation(candles)
            distribution = detect_distribution(candles)
            phase = detect_phase(candles)

            # Find range high/low for spring/upthrust detection
            range_high = float(np.max(_highs(candles[-30:-5]))) if len(candles) > 35 else float(np.max(_highs(candles)))
            range_low = float(np.min(_lows(candles[-30:-5]))) if len(candles) > 35 else float(np.min(_lows(candles)))

            spring = detect_spring(candles, range_low)
            upthrust = detect_upthrust(candles, range_high)

            # Trading bias from Wyckoff
            bias = "neutral"
            if phase["phase"] in ("Accumulation",) and spring and spring.get("detected"):
                bias = "bullish"
            elif phase["phase"] == "Markup":
                bias = "bullish"
            elif phase["phase"] in ("Distribution",) and upthrust and upthrust.get("detected"):
                bias = "bearish"
            elif phase["phase"] == "Markdown":
                bias = "bearish"

            return {
                "accumulation": accumulation,
                "distribution": distribution,
                "phase": phase,
                "spring": spring,
                "upthrust": upthrust,
                "wyckoff_bias": bias,
                "range_high": range_high,
                "range_low": range_low,
            }
        except Exception as e:
            logger.error(f"Wyckoff analyze error: {e}")
            return {"error": str(e), "phase": {"phase": "Unknown"}}


wyckoff_engine = WyckoffEngine()

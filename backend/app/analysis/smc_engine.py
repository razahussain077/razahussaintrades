import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


def _highs(candles: List[Dict]) -> np.ndarray:
    return np.array([c["high"] for c in candles], dtype=float)


def _lows(candles: List[Dict]) -> np.ndarray:
    return np.array([c["low"] for c in candles], dtype=float)


def _closes(candles: List[Dict]) -> np.ndarray:
    return np.array([c["close"] for c in candles], dtype=float)


def _opens(candles: List[Dict]) -> np.ndarray:
    return np.array([c["open"] for c in candles], dtype=float)


def detect_order_blocks(candles: List[Dict]) -> List[Dict]:
    """
    Find bullish/bearish order blocks.
    Bullish OB: last bearish candle before a strong bullish impulse move.
    Bearish OB: last bullish candle before a strong bearish impulse move.
    """
    if len(candles) < 5:
        return []

    opens = _opens(candles)
    closes = _closes(candles)
    highs = _highs(candles)
    lows = _lows(candles)
    order_blocks = []

    for i in range(2, len(candles) - 2):
        body = abs(closes[i + 2] - opens[i + 2])
        candle_range = highs[i + 2] - lows[i + 2]
        if candle_range == 0:
            continue
        impulse_strength = body / candle_range

        # Bullish OB: bearish candle before upward impulse
        if closes[i] < opens[i] and impulse_strength > 0.6:
            price_move = (closes[i + 2] - closes[i]) / closes[i]
            if price_move > 0.005:
                order_blocks.append(
                    {
                        "type": "bullish",
                        "index": i,
                        "top": max(opens[i], closes[i]),
                        "bottom": min(opens[i], closes[i]),
                        "high": highs[i],
                        "low": lows[i],
                        "timestamp": candles[i].get("timestamp"),
                        "strength": round(impulse_strength * 100, 1),
                    }
                )

        # Bearish OB: bullish candle before downward impulse
        if closes[i] > opens[i] and impulse_strength > 0.6:
            price_move = (closes[i + 2] - closes[i]) / closes[i]
            if price_move < -0.005:
                order_blocks.append(
                    {
                        "type": "bearish",
                        "index": i,
                        "top": max(opens[i], closes[i]),
                        "bottom": min(opens[i], closes[i]),
                        "high": highs[i],
                        "low": lows[i],
                        "timestamp": candles[i].get("timestamp"),
                        "strength": round(impulse_strength * 100, 1),
                    }
                )

    return order_blocks[-10:]  # Return last 10 order blocks


def detect_fair_value_gaps(candles: List[Dict]) -> List[Dict]:
    """
    Find Fair Value Gaps (FVGs).
    Bullish FVG: candle[0].high < candle[2].low  (gap between candle 0 high and candle 2 low)
    Bearish FVG: candle[0].low > candle[2].high  (gap between candle 0 low and candle 2 high)
    """
    if len(candles) < 3:
        return []

    highs = _highs(candles)
    lows = _lows(candles)
    fvgs = []

    for i in range(len(candles) - 2):
        gap_top = 0.0
        gap_bottom = 0.0
        fvg_type = None

        # Bullish FVG
        if highs[i] < lows[i + 2]:
            gap_bottom = highs[i]
            gap_top = lows[i + 2]
            fvg_type = "bullish"

        # Bearish FVG
        elif lows[i] > highs[i + 2]:
            gap_top = lows[i]
            gap_bottom = highs[i + 2]
            fvg_type = "bearish"

        if fvg_type and (gap_top - gap_bottom) > 0:
            gap_size_pct = (gap_top - gap_bottom) / gap_bottom * 100
            if gap_size_pct >= 0.05:  # minimum 0.05% gap
                fvgs.append(
                    {
                        "type": fvg_type,
                        "index": i + 1,
                        "top": gap_top,
                        "bottom": gap_bottom,
                        "midpoint": (gap_top + gap_bottom) / 2,
                        "gap_pct": round(gap_size_pct, 3),
                        "timestamp": candles[i + 1].get("timestamp"),
                        "filled": False,
                    }
                )

    return fvgs[-15:]


def detect_bos(candles: List[Dict]) -> List[Dict]:
    """
    Break of Structure.
    Bullish BOS: price breaks above a previous significant high.
    Bearish BOS: price breaks below a previous significant low.
    """
    if len(candles) < 10:
        return []

    highs = _highs(candles)
    lows = _lows(candles)
    closes = _closes(candles)
    bos_events = []
    lookback = 10

    for i in range(lookback, len(candles)):
        window_high = np.max(highs[i - lookback: i - 1])
        window_low = np.min(lows[i - lookback: i - 1])

        # Bullish BOS: close breaks above recent high
        if closes[i] > window_high and closes[i - 1] <= window_high:
            bos_events.append(
                {
                    "type": "bullish",
                    "index": i,
                    "level": window_high,
                    "close": closes[i],
                    "timestamp": candles[i].get("timestamp"),
                }
            )

        # Bearish BOS: close breaks below recent low
        elif closes[i] < window_low and closes[i - 1] >= window_low:
            bos_events.append(
                {
                    "type": "bearish",
                    "index": i,
                    "level": window_low,
                    "close": closes[i],
                    "timestamp": candles[i].get("timestamp"),
                }
            )

    return bos_events[-5:]


def detect_choch(candles: List[Dict]) -> List[Dict]:
    """
    Change of Character (CHoCH): first break against the established trend.
    After a series of higher highs -> first lower low = bearish CHoCH
    After a series of lower lows  -> first higher high = bullish CHoCH
    """
    if len(candles) < 20:
        return []

    highs = _highs(candles)
    lows = _lows(candles)
    choch_events = []
    lookback = 15

    for i in range(lookback, len(candles)):
        segment_highs = highs[i - lookback: i]
        segment_lows = lows[i - lookback: i]

        # Count higher highs in segment (bullish trend)
        hh_count = sum(
            1 for j in range(1, len(segment_highs))
            if segment_highs[j] > segment_highs[j - 1]
        )
        ll_count = sum(
            1 for j in range(1, len(segment_lows))
            if segment_lows[j] < segment_lows[j - 1]
        )

        # Bullish trend -> price makes lower low = bearish CHoCH
        if hh_count > lookback * 0.6 and lows[i] < np.min(segment_lows):
            choch_events.append(
                {
                    "type": "bearish",
                    "index": i,
                    "level": lows[i],
                    "timestamp": candles[i].get("timestamp"),
                    "prior_trend": "bullish",
                }
            )

        # Bearish trend -> price makes higher high = bullish CHoCH
        elif ll_count > lookback * 0.6 and highs[i] > np.max(segment_highs):
            choch_events.append(
                {
                    "type": "bullish",
                    "index": i,
                    "level": highs[i],
                    "timestamp": candles[i].get("timestamp"),
                    "prior_trend": "bearish",
                }
            )

    return choch_events[-5:]


def get_premium_discount_zones(candles: List[Dict]) -> Dict:
    """
    Split the entire range 50/50.
    Above midpoint = premium zone (institutional selling area).
    Below midpoint = discount zone (institutional buying area).
    """
    if not candles:
        return {}

    highs = _highs(candles)
    lows = _lows(candles)
    range_high = float(np.max(highs))
    range_low = float(np.min(lows))
    midpoint = (range_high + range_low) / 2
    current_price = candles[-1]["close"]

    zone = "premium" if current_price > midpoint else "discount"
    zone_pct = (current_price - midpoint) / midpoint * 100

    return {
        "range_high": range_high,
        "range_low": range_low,
        "midpoint": midpoint,
        "current_price": current_price,
        "zone": zone,
        "deviation_pct": round(zone_pct, 2),
        "premium_zone": {"high": range_high, "low": midpoint},
        "discount_zone": {"high": midpoint, "low": range_low},
        "equilibrium": midpoint,
    }


def detect_liquidity_zones(candles: List[Dict]) -> List[Dict]:
    """
    Equal highs/lows where stop-loss clusters form.
    Criteria: touched 2+ times within 0.1% of each other.
    """
    if len(candles) < 10:
        return []

    highs = _highs(candles)
    lows = _lows(candles)
    tolerance = 0.001  # 0.1%
    zones = []

    # Check highs for equal highs
    for i in range(len(candles)):
        level = highs[i]
        touches = [
            j for j in range(len(candles))
            if abs(highs[j] - level) / level <= tolerance
        ]
        if len(touches) >= 2 and i == touches[0]:
            zones.append(
                {
                    "type": "equal_high",
                    "level": float(level),
                    "touches": len(touches),
                    "indices": touches,
                    "timestamp": candles[i].get("timestamp"),
                }
            )

    # Check lows for equal lows
    for i in range(len(candles)):
        level = lows[i]
        touches = [
            j for j in range(len(candles))
            if abs(lows[j] - level) / level <= tolerance
        ]
        if len(touches) >= 2 and i == touches[0]:
            zones.append(
                {
                    "type": "equal_low",
                    "level": float(level),
                    "touches": len(touches),
                    "indices": touches,
                    "timestamp": candles[i].get("timestamp"),
                }
            )

    # Deduplicate overlapping levels
    unique_zones = []
    for z in zones:
        duplicate = False
        for u in unique_zones:
            if abs(z["level"] - u["level"]) / u["level"] < tolerance:
                duplicate = True
                break
        if not duplicate:
            unique_zones.append(z)

    return unique_zones[-10:]


class SMCEngine:
    def analyze(self, candles: List[Dict]) -> Dict:
        if len(candles) < 20:
            return {"error": "Insufficient candle data"}
        try:
            order_blocks = detect_order_blocks(candles)
            fvgs = detect_fair_value_gaps(candles)
            bos = detect_bos(candles)
            choch = detect_choch(candles)
            pd_zones = get_premium_discount_zones(candles)
            liquidity_zones = detect_liquidity_zones(candles)

            current_price = candles[-1]["close"]

            # Find nearest bullish/bearish OB
            nearby_bull_ob = [ob for ob in order_blocks if ob["type"] == "bullish" and ob["top"] < current_price]
            nearby_bear_ob = [ob for ob in order_blocks if ob["type"] == "bearish" and ob["bottom"] > current_price]

            nearest_bull_ob = max(nearby_bull_ob, key=lambda x: x["top"]) if nearby_bull_ob else None
            nearest_bear_ob = min(nearby_bear_ob, key=lambda x: x["bottom"]) if nearby_bear_ob else None

            # Bullish unfilled FVGs below price
            bull_fvgs_below = [f for f in fvgs if f["type"] == "bullish" and f["top"] < current_price]
            bear_fvgs_above = [f for f in fvgs if f["type"] == "bearish" and f["bottom"] > current_price]

            latest_bos = bos[-1] if bos else None
            latest_choch = choch[-1] if choch else None

            # Bias
            bias = "neutral"
            if latest_bos and latest_bos["type"] == "bullish":
                bias = "bullish"
            elif latest_bos and latest_bos["type"] == "bearish":
                bias = "bearish"
            if latest_choch:
                bias = latest_choch["type"]

            return {
                "order_blocks": order_blocks,
                "fair_value_gaps": fvgs,
                "break_of_structure": bos,
                "change_of_character": choch,
                "premium_discount_zones": pd_zones,
                "liquidity_zones": liquidity_zones,
                "nearest_bullish_ob": nearest_bull_ob,
                "nearest_bearish_ob": nearest_bear_ob,
                "bullish_fvgs_below": bull_fvgs_below[-3:],
                "bearish_fvgs_above": bear_fvgs_above[-3:],
                "latest_bos": latest_bos,
                "latest_choch": latest_choch,
                "market_bias": bias,
                "in_premium": pd_zones.get("zone") == "premium",
                "in_discount": pd_zones.get("zone") == "discount",
            }
        except Exception as e:
            logger.error(f"SMC analyze error: {e}")
            return {"error": str(e)}


smc_engine = SMCEngine()

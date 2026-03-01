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


def _opens(candles: List[Dict]) -> np.ndarray:
    return np.array([c["open"] for c in candles], dtype=float)


def find_equal_highs_lows(candles: List[Dict], tolerance: float = 0.001) -> Dict:
    """
    Find equal highs and lows where SL clusters form.
    Same level touched 2+ times within tolerance (default 0.1%).
    """
    if len(candles) < 5:
        return {"equal_highs": [], "equal_lows": []}

    highs = _highs(candles)
    lows = _lows(candles)
    equal_highs = []
    equal_lows = []
    seen_highs = set()
    seen_lows = set()

    for i in range(len(candles)):
        level_h = highs[i]
        key_h = round(level_h, 6)
        if key_h in seen_highs:
            continue
        matches_h = [j for j in range(len(candles)) if abs(highs[j] - level_h) / level_h <= tolerance]
        if len(matches_h) >= 2:
            seen_highs.add(key_h)
            equal_highs.append({
                "level": float(level_h),
                "touches": len(matches_h),
                "indices": matches_h,
                "timestamp": candles[i].get("timestamp"),
            })

    for i in range(len(candles)):
        level_l = lows[i]
        key_l = round(level_l, 6)
        if key_l in seen_lows:
            continue
        matches_l = [j for j in range(len(candles)) if abs(lows[j] - level_l) / level_l <= tolerance]
        if len(matches_l) >= 2:
            seen_lows.add(key_l)
            equal_lows.append({
                "level": float(level_l),
                "touches": len(matches_l),
                "indices": matches_l,
                "timestamp": candles[i].get("timestamp"),
            })

    return {
        "equal_highs": equal_highs[-5:],
        "equal_lows": equal_lows[-5:],
    }


def detect_stop_hunt(candles: List[Dict]) -> Optional[Dict]:
    """
    Stop hunt: Price wicks beyond structure then closes back inside.
    Criteria: wick > 2x body size, wick extends beyond equal high/low.
    """
    if len(candles) < 10:
        return None

    highs = _highs(candles)
    lows = _lows(candles)
    closes = _closes(candles)
    opens = _opens(candles)

    # Equal levels from prior candles
    eq = find_equal_highs_lows(candles[:-1])
    eq_high_levels = [z["level"] for z in eq["equal_highs"]]
    eq_low_levels = [z["level"] for z in eq["equal_lows"]]

    last = candles[-1]
    body = abs(float(closes[-1]) - float(opens[-1]))
    upper_wick = float(highs[-1]) - max(float(closes[-1]), float(opens[-1]))
    lower_wick = min(float(closes[-1]), float(opens[-1])) - float(lows[-1])

    # Bearish stop hunt: upper wick > 2x body + wick beyond equal high
    for eq_h in eq_high_levels:
        if highs[-1] > eq_h and closes[-1] < eq_h:
            if upper_wick > 0 and body >= 0 and (body == 0 or upper_wick >= 2 * body):
                return {
                    "detected": True,
                    "type": "bearish",
                    "swept_level": eq_h,
                    "wick_high": float(highs[-1]),
                    "close": float(closes[-1]),
                    "description": f"Bearish stop hunt above equal high {eq_h:.4f}",
                }

    # Bullish stop hunt: lower wick > 2x body + wick beyond equal low
    for eq_l in eq_low_levels:
        if lows[-1] < eq_l and closes[-1] > eq_l:
            if lower_wick > 0 and body >= 0 and (body == 0 or lower_wick >= 2 * body):
                return {
                    "detected": True,
                    "type": "bullish",
                    "swept_level": eq_l,
                    "wick_low": float(lows[-1]),
                    "close": float(closes[-1]),
                    "description": f"Bullish stop hunt below equal low {eq_l:.4f}",
                }

    return None


def detect_liquidity_sweep_reclaim(candles: List[Dict]) -> Optional[Dict]:
    """
    Liquidity sweep and reclaim: price breaks level, grabs liquidity (wick), returns inside.
    This is a high-probability entry signal.
    """
    if len(candles) < 15:
        return None

    highs = _highs(candles)
    lows = _lows(candles)
    closes = _closes(candles)

    lookback = min(15, len(candles) - 2)
    prior_high = float(np.max(highs[-lookback:-1]))
    prior_low = float(np.min(lows[-lookback:-1]))
    current_close = float(closes[-1])
    current_high = float(highs[-1])
    current_low = float(lows[-1])

    # Bearish sweep and reclaim: wicked above prior high, closed back below
    if current_high > prior_high and current_close < prior_high:
        return {
            "detected": True,
            "type": "bearish",
            "swept_level": prior_high,
            "wick_extreme": current_high,
            "close": current_close,
            "description": f"Bearish sweep of {prior_high:.4f} - close back inside: SELL signal",
        }

    # Bullish sweep and reclaim: wicked below prior low, closed back above
    if current_low < prior_low and current_close > prior_low:
        return {
            "detected": True,
            "type": "bullish",
            "swept_level": prior_low,
            "wick_extreme": current_low,
            "close": current_close,
            "description": f"Bullish sweep of {prior_low:.4f} - close back inside: BUY signal",
        }

    return None


def find_liquidity_voids(candles: List[Dict]) -> List[Dict]:
    """
    Areas with thin volume or price imbalance between candles.
    Identified as gaps where price moved rapidly with little consolidation.
    """
    if len(candles) < 5:
        return []

    highs = _highs(candles)
    lows = _lows(candles)
    closes = _closes(candles)
    volumes = np.array([c.get("volume", 1) for c in candles], dtype=float)
    avg_volume = float(np.mean(volumes)) if len(volumes) > 0 else 1.0
    voids = []

    for i in range(1, len(candles) - 1):
        # Price moved significantly on below-average volume = liquidity void
        price_move_pct = abs(closes[i] - closes[i - 1]) / closes[i - 1] * 100
        vol_ratio = volumes[i] / avg_volume if avg_volume > 0 else 1.0

        if price_move_pct > 0.5 and vol_ratio < 0.5:
            direction = "bullish" if closes[i] > closes[i - 1] else "bearish"
            voids.append({
                "type": direction,
                "top": float(max(closes[i], closes[i - 1])),
                "bottom": float(min(closes[i], closes[i - 1])),
                "price_move_pct": round(price_move_pct, 3),
                "volume_ratio": round(vol_ratio, 3),
                "index": i,
                "timestamp": candles[i].get("timestamp"),
            })

    return voids[-10:]


class LiquidityEngine:
    def analyze(self, candles: List[Dict]) -> Dict:
        if len(candles) < 15:
            return {"error": "Insufficient candle data"}
        try:
            eq_levels = find_equal_highs_lows(candles)
            stop_hunt = detect_stop_hunt(candles)
            sweep_reclaim = detect_liquidity_sweep_reclaim(candles)
            voids = find_liquidity_voids(candles)

            current_price = candles[-1]["close"]

            # Nearest liquidity levels
            all_levels = (
                [z["level"] for z in eq_levels["equal_highs"]]
                + [z["level"] for z in eq_levels["equal_lows"]]
            )
            levels_above = sorted([l for l in all_levels if l > current_price])
            levels_below = sorted([l for l in all_levels if l < current_price], reverse=True)

            return {
                "equal_highs": eq_levels["equal_highs"],
                "equal_lows": eq_levels["equal_lows"],
                "stop_hunt": stop_hunt,
                "sweep_reclaim": sweep_reclaim,
                "liquidity_voids": voids,
                "nearest_liquidity_above": levels_above[0] if levels_above else None,
                "nearest_liquidity_below": levels_below[0] if levels_below else None,
                "has_stop_hunt": stop_hunt is not None,
                "has_sweep_reclaim": sweep_reclaim is not None,
            }
        except Exception as e:
            logger.error(f"Liquidity analyze error: {e}")
            return {"error": str(e)}


liquidity_engine = LiquidityEngine()

"""
Market Regime Auto-Adaptation Engine — Feature 8
Detects market regime using ADX, Bollinger Bands, and ATR.
Adapts signal parameters based on detected regime.
"""
import logging
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# In-memory regime history per symbol
_regime_history: Dict[str, List[Dict]] = {}
_MAX_HISTORY = 100


def _calculate_adx(candles: List[Dict], period: int = 14) -> float:
    """Calculate ADX (Average Directional Index)."""
    if len(candles) < period + 1:
        return 0.0

    highs = np.array([c["high"] for c in candles])
    lows = np.array([c["low"] for c in candles])
    closes = np.array([c["close"] for c in candles])

    # True Range
    tr_list = []
    for i in range(1, len(candles)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        tr_list.append(tr)

    # Directional Movement
    plus_dm = []
    minus_dm = []
    for i in range(1, len(candles)):
        h_diff = highs[i] - highs[i - 1]
        l_diff = lows[i - 1] - lows[i]
        plus_dm.append(max(h_diff, 0) if h_diff > l_diff else 0)
        minus_dm.append(max(l_diff, 0) if l_diff > h_diff else 0)

    tr_arr = np.array(tr_list[-period:])
    plus_dm_arr = np.array(plus_dm[-period:])
    minus_dm_arr = np.array(minus_dm[-period:])

    tr_sum = np.sum(tr_arr)
    if tr_sum == 0:
        return 0.0

    plus_di = 100 * np.sum(plus_dm_arr) / tr_sum
    minus_di = 100 * np.sum(minus_dm_arr) / tr_sum

    dx_denom = plus_di + minus_di
    if dx_denom == 0:
        return 0.0

    dx = 100 * abs(plus_di - minus_di) / dx_denom

    return round(float(dx), 2)


def _calculate_bb_width(candles: List[Dict], period: int = 20) -> float:
    """Calculate Bollinger Band width as % of price (squeeze detection)."""
    if len(candles) < period:
        return 0.0

    closes = np.array([c["close"] for c in candles[-period:]])
    sma = np.mean(closes)
    std = np.std(closes)

    if sma == 0:
        return 0.0

    upper = sma + 2 * std
    lower = sma - 2 * std
    width_pct = (upper - lower) / sma * 100

    return round(float(width_pct), 2)


def _calculate_atr_ratio(candles: List[Dict], period: int = 14) -> float:
    """Calculate current ATR as ratio to its 20-period average."""
    if len(candles) < period + 20:
        return 1.0

    tr_list = []
    for i in range(1, len(candles)):
        c = candles[i]
        prev_c = candles[i - 1]
        tr = max(
            c["high"] - c["low"],
            abs(c["high"] - prev_c["close"]),
            abs(c["low"] - prev_c["close"]),
        )
        tr_list.append(tr)

    tr_arr = np.array(tr_list)
    current_atr = np.mean(tr_arr[-period:])
    historical_atr = np.mean(tr_arr[-period - 20:-period])

    if historical_atr == 0:
        return 1.0

    return round(float(current_atr / historical_atr), 3)


def detect_regime(candles: List[Dict]) -> Dict:
    """
    Detect market regime using ADX, BB width, and ATR ratio.

    Regimes:
      TRENDING: ADX > 25
      RANGING: ADX < 20
      VOLATILE: ATR ratio > 1.5
      SQUEEZE: BB width < 3% (low vol, about to explode)
    """
    if len(candles) < 35:
        return {
            "regime": "ranging",
            "label": "RANGING",
            "emoji": "↔️",
            "adx": 0,
            "bb_width": 0,
            "atr_ratio": 1.0,
            "description": "Insufficient data",
        }

    adx = _calculate_adx(candles)
    bb_width = _calculate_bb_width(candles)
    atr_ratio = _calculate_atr_ratio(candles)

    # Determine regime
    if bb_width < 3.0 and atr_ratio < 0.8:
        regime = "squeeze"
        label = "SQUEEZE"
        emoji = "💤"
        description = "Low volatility squeeze — breakout imminent, watch for BOS/CHoCH direction"
    elif atr_ratio > 1.5:
        regime = "volatile"
        label = "VOLATILE"
        emoji = "🌊"
        description = "High volatility — wider SL, smaller positions, only 5+ engine signals"
    elif adx > 25:
        regime = "trending"
        label = "TRENDING"
        emoji = "📈"
        description = "Strong trend — follow momentum, trailing SL, tighter entries"
    else:
        regime = "ranging"
        label = "RANGING"
        emoji = "↔️"
        description = "Ranging market — trade at premium/discount extremes, mean reversion"

    return {
        "regime": regime,
        "label": label,
        "emoji": emoji,
        "adx": adx,
        "bb_width": bb_width,
        "atr_ratio": atr_ratio,
        "description": description,
    }


def get_regime_signal_adaptation(regime: str, signal_type: str) -> Dict:
    """
    Get signal adaptation recommendations based on regime.
    Returns SL multiplier, position size multiplier, and notes.
    """
    adaptations = {
        "trending": {
            "sl_multiplier": 1.0,
            "position_size_multiplier": 1.0,
            "min_engine_count": 3,
            "preferred_direction": None,  # Set based on trend direction
            "note": "TRENDING regime — follow momentum, trailing SL recommended",
            "skip_counter_trend": True,
        },
        "ranging": {
            "sl_multiplier": 1.2,
            "position_size_multiplier": 0.8,
            "min_engine_count": 3,
            "preferred_direction": None,
            "note": "RANGING regime — trade at zone extremes only, smaller TP targets",
            "skip_counter_trend": False,
        },
        "volatile": {
            "sl_multiplier": 1.3,
            "position_size_multiplier": 0.6,
            "min_engine_count": 5,
            "preferred_direction": None,
            "note": "VOLATILE regime — wider SL (+30%), smaller position (60%), only highest confidence signals",
            "skip_counter_trend": False,
        },
        "squeeze": {
            "sl_multiplier": 1.0,
            "position_size_multiplier": 0.7,
            "min_engine_count": 4,
            "preferred_direction": None,
            "note": "💤 SQUEEZE — Breakout imminent! Wait for BOS/CHoCH to confirm direction before entry",
            "skip_counter_trend": False,
        },
    }

    adaptation = adaptations.get(regime, adaptations["ranging"])
    return {
        "signal_type": signal_type,
        "regime": regime,
        **adaptation,
    }


class RegimeEngine:
    """Market regime auto-adaptation engine."""

    def detect(self, symbol: str, candles: List[Dict]) -> Dict:
        """Detect regime and store in history."""
        try:
            result = detect_regime(candles)

            # Store in history
            if symbol not in _regime_history:
                _regime_history[symbol] = []
            history = _regime_history[symbol]
            history.append({**result, "symbol": symbol})
            if len(history) > _MAX_HISTORY:
                _regime_history[symbol] = history[-_MAX_HISTORY:]

            return result
        except Exception as e:
            logger.error(f"RegimeEngine.detect error for {symbol}: {e}")
            return {"regime": "ranging", "label": "RANGING", "emoji": "↔️", "error": str(e)}

    def get_adaptation(self, regime: str, signal_type: str) -> Dict:
        return get_regime_signal_adaptation(regime, signal_type)

    def get_history(self, symbol: str) -> List[Dict]:
        return _regime_history.get(symbol, [])[-20:]


regime_engine = RegimeEngine()

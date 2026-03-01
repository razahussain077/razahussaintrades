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


def calculate_atr(candles: List[Dict], period: int = 14) -> float:
    """
    Calculate Average True Range (ATR) using Wilder's smoothing.
    True Range = max(High-Low, |High-PrevClose|, |Low-PrevClose|)
    """
    if len(candles) < period + 1:
        return 0.0

    highs = _highs(candles)
    lows = _lows(candles)
    closes = _closes(candles)

    trs = []
    for i in range(1, len(candles)):
        tr = float(max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        ))
        trs.append(tr)

    if not trs:
        return 0.0

    # Wilder's smoothing
    atr = float(np.mean(trs[:period]))
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period

    return round(atr, 8)


def calculate_atr_percentage(candles: List[Dict], period: int = 14) -> float:
    """ATR as percentage of current price."""
    atr = calculate_atr(candles, period)
    current_price = candles[-1]["close"] if candles else 1
    if current_price <= 0:
        return 0.0
    return round(atr / current_price * 100, 4)


def calculate_volatility_score(candles: List[Dict], period: int = 14) -> Dict:
    """
    0-100 volatility score based on ATR, Bollinger Band width, and recent price range.
    Higher score = more volatile.
    """
    if len(candles) < period + 1:
        return {"score": 0, "level": "Unknown", "atr": 0, "atr_pct": 0}

    atr = calculate_atr(candles, period)
    atr_pct = calculate_atr_percentage(candles, period)
    closes = _closes(candles)

    # Bollinger Band width as volatility proxy
    rolling_mean = float(np.mean(closes[-period:]))
    rolling_std = float(np.std(closes[-period:]))
    bb_width = (rolling_std / rolling_mean * 100) if rolling_mean > 0 else 0

    # Historical volatility (annualised daily returns std)
    if len(closes) >= 2:
        returns = np.diff(closes[-min(30, len(closes)):]) / closes[-min(30, len(closes)):-1]
        hist_vol = float(np.std(returns)) * 100  # as %
    else:
        hist_vol = 0.0

    # Composite score: weight ATR% heavily
    score = min(100, atr_pct * 15 + bb_width * 3 + hist_vol * 5)

    if score >= 70:
        level = "Extreme"
    elif score >= 50:
        level = "High"
    elif score >= 30:
        level = "Medium"
    elif score >= 10:
        level = "Low"
    else:
        level = "Very Low"

    return {
        "score": round(score, 1),
        "level": level,
        "atr": atr,
        "atr_pct": atr_pct,
        "bb_width": round(bb_width, 4),
        "hist_vol_pct": round(hist_vol, 4),
    }


def get_volume_market_cap_ratio(volume: float, market_cap: float) -> Dict:
    """
    Volume/Market Cap ratio. Higher = more liquid relative to size.
    > 0.1 = high liquidity, < 0.01 = low liquidity
    """
    if market_cap <= 0:
        return {"ratio": 0.0, "interpretation": "Unknown", "score": 50}

    ratio = volume / market_cap

    if ratio >= 0.2:
        interpretation = "Extremely high liquidity"
        score = 95
    elif ratio >= 0.1:
        interpretation = "High liquidity"
        score = 80
    elif ratio >= 0.05:
        interpretation = "Moderate liquidity"
        score = 60
    elif ratio >= 0.01:
        interpretation = "Low liquidity"
        score = 30
    else:
        interpretation = "Very low liquidity"
        score = 10

    return {
        "ratio": round(ratio, 6),
        "ratio_pct": round(ratio * 100, 3),
        "interpretation": interpretation,
        "score": score,
        "volume": volume,
        "market_cap": market_cap,
    }


def calculate_rsi(candles: List[Dict], period: int = 14) -> float:
    """Calculate RSI."""
    if len(candles) < period + 1:
        return 50.0

    closes = _closes(candles)
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    avg_gain = float(np.mean(gains[:period]))
    avg_loss = float(np.mean(losses[:period]))

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1 + rs))
    return round(float(rsi), 2)


class VolatilityEngine:
    def analyze(self, candles: List[Dict]) -> Dict:
        if len(candles) < 15:
            return {"score": 0, "error": "Insufficient data"}
        try:
            vol_score = calculate_volatility_score(candles)
            atr = calculate_atr(candles)
            atr_pct = calculate_atr_percentage(candles)
            rsi = calculate_rsi(candles)

            return {
                "volatility_score": vol_score,
                "atr": atr,
                "atr_pct": atr_pct,
                "rsi": rsi,
                "is_oversold": rsi < 30,
                "is_overbought": rsi > 70,
                "is_high_volatility": vol_score.get("score", 0) >= 50,
            }
        except Exception as e:
            logger.error(f"VolatilityEngine analyze error: {e}")
            return {"score": 0, "error": str(e)}


volatility_engine = VolatilityEngine()

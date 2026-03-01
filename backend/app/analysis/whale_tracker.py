import logging
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


def _closes(candles: List[Dict]) -> np.ndarray:
    return np.array([c["close"] for c in candles], dtype=float)


def _highs(candles: List[Dict]) -> np.ndarray:
    return np.array([c["high"] for c in candles], dtype=float)


def _lows(candles: List[Dict]) -> np.ndarray:
    return np.array([c["low"] for c in candles], dtype=float)


def _volumes(candles: List[Dict]) -> np.ndarray:
    return np.array([c.get("volume", 0) for c in candles], dtype=float)


def detect_abnormal_volume(candles: List[Dict], lookback: int = 20, threshold: float = 3.0) -> Optional[Dict]:
    """
    Detect abnormal volume: current volume > threshold * average of last lookback candles.
    """
    if len(candles) < lookback + 1:
        return None

    volumes = _volumes(candles)
    avg_vol = float(np.mean(volumes[-(lookback + 1):-1]))
    current_vol = float(volumes[-1])

    if avg_vol == 0:
        return None

    ratio = current_vol / avg_vol
    if ratio >= threshold:
        direction = "bullish" if candles[-1]["close"] > candles[-1]["open"] else "bearish"
        return {
            "detected": True,
            "current_volume": current_vol,
            "average_volume": avg_vol,
            "volume_ratio": round(ratio, 2),
            "direction": direction,
            "description": f"Abnormal volume: {ratio:.1f}x average ({direction} candle)",
        }
    return None


def detect_volume_divergence(candles: List[Dict], lookback: int = 10) -> Optional[Dict]:
    """
    Detect volume divergence: price going up but volume going down (weak move).
    Or price going down but volume going down (potential reversal).
    """
    if len(candles) < lookback + 1:
        return None

    closes = _closes(candles)
    volumes = _volumes(candles)

    # Linear regression slope of price and volume over lookback
    x = np.arange(lookback, dtype=float)
    price_segment = closes[-lookback:]
    vol_segment = volumes[-lookback:]

    if len(price_segment) < 2:
        return None

    def slope(arr: np.ndarray) -> float:
        if np.std(arr) == 0:
            return 0.0
        return float(np.polyfit(x, arr, 1)[0])

    price_slope = slope(price_segment)
    vol_slope = slope(vol_segment)

    # Bullish price divergence: price up, volume down
    if price_slope > 0 and vol_slope < 0:
        return {
            "detected": True,
            "type": "bearish_divergence",
            "description": "Price rising but volume falling - weak bullish move, potential reversal",
            "price_slope": round(price_slope, 6),
            "volume_slope": round(vol_slope, 4),
        }

    # Bearish price divergence: price down, volume down
    if price_slope < 0 and vol_slope < 0:
        return {
            "detected": True,
            "type": "bullish_divergence",
            "description": "Price falling but volume falling - weak bearish move, potential reversal",
            "price_slope": round(price_slope, 6),
            "volume_slope": round(vol_slope, 4),
        }

    return None


def analyze_order_book_imbalance(order_book: Dict) -> Dict:
    """
    Analyze order book for large bid/ask imbalance.
    Returns imbalance score and dominant side.
    """
    bids = order_book.get("bids", [])
    asks = order_book.get("asks", [])

    if not bids or not asks:
        return {
            "bid_volume": 0,
            "ask_volume": 0,
            "imbalance_ratio": 1.0,
            "dominant_side": "neutral",
            "score": 50,
        }

    bid_volume = sum(price * qty for price, qty in bids)
    ask_volume = sum(price * qty for price, qty in asks)

    total = bid_volume + ask_volume
    if total == 0:
        return {
            "bid_volume": 0,
            "ask_volume": 0,
            "imbalance_ratio": 1.0,
            "dominant_side": "neutral",
            "score": 50,
        }

    bid_pct = bid_volume / total * 100
    ask_pct = ask_volume / total * 100

    if bid_volume > ask_volume:
        dominant_side = "bullish"
        imbalance_ratio = bid_volume / ask_volume if ask_volume > 0 else 999
        score = min(100, 50 + (bid_pct - 50) * 2)
    else:
        dominant_side = "bearish"
        imbalance_ratio = ask_volume / bid_volume if bid_volume > 0 else 999
        score = max(0, 50 - (ask_pct - 50) * 2)

    return {
        "bid_volume": round(bid_volume, 2),
        "ask_volume": round(ask_volume, 2),
        "bid_pct": round(bid_pct, 1),
        "ask_pct": round(ask_pct, 1),
        "imbalance_ratio": round(imbalance_ratio, 2),
        "dominant_side": dominant_side,
        "score": round(score, 1),
    }


def get_whale_score(candles: List[Dict], order_book: Optional[Dict] = None) -> Dict:
    """
    Composite 0-100 score of whale activity.
    Components: abnormal volume, volume divergence, order book imbalance.
    """
    score = 0
    signals = []

    abnormal_vol = detect_abnormal_volume(candles)
    if abnormal_vol and abnormal_vol.get("detected"):
        ratio = abnormal_vol.get("volume_ratio", 1)
        vol_contribution = min(40, (ratio - 3) * 10 + 20)
        score += vol_contribution
        signals.append(abnormal_vol.get("description", "Abnormal volume detected"))

    vol_div = detect_volume_divergence(candles)
    if vol_div and vol_div.get("detected"):
        score += 20
        signals.append(vol_div.get("description", "Volume divergence detected"))

    ob_imbalance = {"score": 50, "dominant_side": "neutral"}
    if order_book:
        ob_imbalance = analyze_order_book_imbalance(order_book)
        ob_contribution = abs(ob_imbalance["score"] - 50) * 0.8
        score += ob_contribution
        if ob_imbalance["imbalance_ratio"] > 1.5:
            signals.append(
                f"Order book imbalance: {ob_imbalance['dominant_side']} dominant "
                f"({ob_imbalance['imbalance_ratio']:.1f}x)"
            )

    score = min(100, score)

    return {
        "whale_score": round(score, 1),
        "level": "High" if score >= 70 else "Medium" if score >= 40 else "Low",
        "signals": signals,
        "abnormal_volume": abnormal_vol,
        "volume_divergence": vol_div,
        "order_book_imbalance": ob_imbalance,
        "is_whale_active": score >= 50,
    }


class WhaleTracker:
    def analyze(self, candles: List[Dict], order_book: Optional[Dict] = None) -> Dict:
        if len(candles) < 20:
            return {"whale_score": 0, "error": "Insufficient data"}
        try:
            return get_whale_score(candles, order_book)
        except Exception as e:
            logger.error(f"WhaleTracker analyze error: {e}")
            return {"whale_score": 0, "error": str(e)}


whale_tracker = WhaleTracker()

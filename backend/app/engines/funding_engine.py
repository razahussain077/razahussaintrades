"""
Funding Rate Strategy Engine — Feature 2
Tracks funding rates and generates signal confidence modifiers.
"""
import logging
from collections import deque
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.exchanges.binance_client import binance_client

logger = logging.getLogger(__name__)

# In-memory store: last 100 readings per symbol
_funding_history: Dict[str, deque] = {}
_MAX_HISTORY = 100


def _get_history(symbol: str) -> deque:
    if symbol not in _funding_history:
        _funding_history[symbol] = deque(maxlen=_MAX_HISTORY)
    return _funding_history[symbol]


def interpret_funding_rate(rate: float) -> Dict:
    """
    Interpret funding rate and return signal confidence modifier.
    Positive funding = longs paying shorts = market over-leveraged long.
    Negative funding = shorts paying longs = market over-leveraged short.
    """
    rate_pct = rate * 100  # Convert to percentage

    if rate_pct > 0.1:
        direction = "EXTREMELY_OVERBOUGHT_LONG"
        short_boost = 25
        long_boost = 0
        description = f"Extremely over-leveraged LONG ({rate_pct:.4f}%) → short squeeze risk"
        sentiment = "bearish"
    elif rate_pct > 0.05:
        direction = "OVERBOUGHT_LONG"
        short_boost = 15
        long_boost = 0
        description = f"Over-leveraged LONG ({rate_pct:.4f}%) → shorts favored"
        sentiment = "bearish"
    elif rate_pct < -0.1:
        direction = "EXTREMELY_OVERBOUGHT_SHORT"
        short_boost = 0
        long_boost = 25
        description = f"Extremely over-leveraged SHORT ({rate_pct:.4f}%) → long squeeze risk"
        sentiment = "bullish"
    elif rate_pct < -0.05:
        direction = "OVERBOUGHT_SHORT"
        short_boost = 0
        long_boost = 15
        description = f"Over-leveraged SHORT ({rate_pct:.4f}%) → longs favored"
        sentiment = "bullish"
    else:
        direction = "NEUTRAL"
        short_boost = 0
        long_boost = 0
        description = f"Funding rate near zero ({rate_pct:.4f}%) → neutral"
        sentiment = "neutral"

    return {
        "rate": rate,
        "rate_pct": round(rate_pct, 6),
        "direction": direction,
        "description": description,
        "sentiment": sentiment,
        "long_confidence_boost": long_boost,
        "short_confidence_boost": short_boost,
    }


def detect_reversal(history: deque) -> Optional[Dict]:
    """
    Detect funding rate reversal pattern:
    3+ consecutive positive readings followed by drop → bearish reversal signal.
    3+ consecutive negative readings followed by rise → bullish reversal signal.
    """
    if len(history) < 4:
        return None

    recent = list(history)[-4:]
    prev_3 = recent[:3]
    last = recent[3]

    prev_rates = [r["rate"] for r in prev_3]
    last_rate = last["rate"]

    if all(r > 0.0001 for r in prev_rates) and last_rate < prev_3[-1]["rate"] * 0.5:
        return {
            "detected": True,
            "type": "bearish_reversal",
            "description": "Funding rate was consistently positive (longs paying) and just dropped — bearish reversal signal",
        }
    elif all(r < -0.0001 for r in prev_rates) and last_rate > prev_3[-1]["rate"] * 0.5:
        return {
            "detected": True,
            "type": "bullish_reversal",
            "description": "Funding rate was consistently negative (shorts paying) and just rose — bullish reversal signal",
        }

    return {"detected": False}


class FundingEngine:
    """Funding rate strategy engine."""

    async def get_funding_data(self, symbol: str) -> Dict:
        """
        Fetch current funding rate, store in history, return analysis.
        """
        try:
            data = await binance_client.get_funding_rate(symbol)
            rate = data.get("funding_rate", 0.0)
            mark_price = data.get("mark_price", 0.0)
            next_funding_time = data.get("next_funding_time")

            # Store in history
            history = _get_history(symbol)
            entry = {
                "rate": rate,
                "mark_price": mark_price,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            history.append(entry)

            interpretation = interpret_funding_rate(rate)
            reversal = detect_reversal(history)

            history_list = list(history)[-20:]  # Return last 20 readings

            return {
                "symbol": symbol,
                "current_rate": rate,
                "current_rate_pct": round(rate * 100, 6),
                "mark_price": mark_price,
                "next_funding_time": next_funding_time,
                "interpretation": interpretation,
                "reversal_signal": reversal,
                "history": history_list,
                "history_count": len(history),
            }
        except Exception as e:
            logger.error(f"FundingEngine.get_funding_data error for {symbol}: {e}")
            return {
                "symbol": symbol,
                "current_rate": 0.0,
                "current_rate_pct": 0.0,
                "interpretation": interpret_funding_rate(0.0),
                "reversal_signal": {"detected": False},
                "history": [],
                "error": str(e),
            }

    def get_signal_modifier(self, symbol: str, signal_type: str) -> Dict:
        """
        Get funding rate signal modifier for a given signal direction.
        Returns confidence boost amount.
        """
        history = _get_history(symbol)
        if not history:
            return {"confidence_boost": 0, "reason": "No funding rate data available"}

        last = list(history)[-1]
        interpretation = interpret_funding_rate(last["rate"])

        if signal_type == "LONG":
            boost = interpretation["long_confidence_boost"]
        else:
            boost = interpretation["short_confidence_boost"]

        return {
            "confidence_boost": boost,
            "funding_rate": last["rate"],
            "reason": interpretation["description"],
            "sentiment": interpretation["sentiment"],
        }


funding_engine = FundingEngine()

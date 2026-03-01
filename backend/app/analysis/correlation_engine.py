import logging
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


def _closes(candles: List[Dict]) -> np.ndarray:
    return np.array([c["close"] for c in candles], dtype=float)


def _highs(candles: List[Dict]) -> np.ndarray:
    return np.array([c["high"] for c in candles], dtype=float)


def _lows(candles: List[Dict]) -> np.ndarray:
    return np.array([c["low"] for c in candles], dtype=float)


def calculate_btc_correlation(
    btc_candles: List[Dict],
    alt_candles: List[Dict],
    periods: int = 30,
) -> Dict:
    """
    Calculate Pearson correlation between BTC and an alt coin over given periods.
    Returns correlation coefficient (-1 to 1) and interpretation.
    """
    if len(btc_candles) < periods or len(alt_candles) < periods:
        return {"correlation": 0.0, "interpretation": "Insufficient data", "periods": periods}

    btc_closes = _closes(btc_candles[-periods:])
    alt_closes = _closes(alt_candles[-periods:])

    # Use returns instead of raw prices for better correlation
    btc_returns = np.diff(btc_closes) / btc_closes[:-1]
    alt_returns = np.diff(alt_closes) / alt_closes[:-1]

    if len(btc_returns) < 2 or np.std(btc_returns) == 0 or np.std(alt_returns) == 0:
        return {"correlation": 0.0, "interpretation": "Insufficient variance", "periods": periods}

    corr = float(np.corrcoef(btc_returns, alt_returns)[0, 1])

    if abs(corr) >= 0.8:
        interpretation = "Strongly correlated" if corr > 0 else "Strongly inverse"
    elif abs(corr) >= 0.5:
        interpretation = "Moderately correlated" if corr > 0 else "Moderately inverse"
    elif abs(corr) >= 0.2:
        interpretation = "Weakly correlated" if corr > 0 else "Weakly inverse"
    else:
        interpretation = "Uncorrelated"

    return {
        "correlation": round(corr, 4),
        "interpretation": interpretation,
        "periods": periods,
        "is_high_correlation": abs(corr) >= 0.7,
    }


def get_btc_dominance_signal(btc_dominance: float, prev_btc_dominance: float) -> Dict:
    """
    Analyze BTC dominance trend.
    Rising BTC dominance = alts likely underperforming.
    Falling BTC dominance = alt season potential.
    """
    change = btc_dominance - prev_btc_dominance
    change_pct = change / prev_btc_dominance * 100 if prev_btc_dominance > 0 else 0

    if change > 0.5:
        signal = "bearish_alts"
        description = "BTC dominance rising - alts likely to underperform (rotate to BTC)"
    elif change < -0.5:
        signal = "bullish_alts"
        description = "BTC dominance falling - alt season conditions forming"
    else:
        signal = "neutral"
        description = "BTC dominance stable - no clear alt rotation signal"

    return {
        "btc_dominance": btc_dominance,
        "prev_btc_dominance": prev_btc_dominance,
        "change": round(change, 3),
        "change_pct": round(change_pct, 3),
        "signal": signal,
        "description": description,
        "alt_season": btc_dominance < 40,
    }


def rank_by_volatility(coins_data: List[Dict]) -> List[Dict]:
    """
    Rank coins by ATR percentage (higher = more volatile).
    coins_data: list of dicts with 'symbol' and 'candles'.
    """
    ranked = []
    for coin in coins_data:
        symbol = coin.get("symbol", "")
        candles = coin.get("candles", [])
        if len(candles) < 15:
            continue

        highs = _highs(candles)
        lows = _lows(candles)
        closes = _closes(candles)

        # ATR calculation
        trs = []
        for i in range(1, len(candles)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            )
            trs.append(tr)
        atr = float(np.mean(trs[-14:])) if len(trs) >= 14 else float(np.mean(trs))
        current_price = float(closes[-1])
        atr_pct = atr / current_price * 100 if current_price > 0 else 0

        ranked.append({
            "symbol": symbol,
            "atr": round(atr, 6),
            "atr_pct": round(atr_pct, 3),
            "current_price": current_price,
        })

    ranked.sort(key=lambda x: x["atr_pct"], reverse=True)
    for i, item in enumerate(ranked):
        item["rank"] = i + 1

    return ranked


def get_market_cap_category(market_cap: float) -> str:
    """Categorize by market cap."""
    if market_cap >= 10_000_000_000:  # $10B+
        return "Large Cap"
    elif market_cap >= 1_000_000_000:  # $1B+
        return "Mid Cap"
    elif market_cap >= 100_000_000:   # $100M+
        return "Small Cap"
    else:
        return "Micro Cap"


def build_correlation_matrix(symbols_data: Dict[str, List[Dict]], periods: int = 30) -> Dict:
    """
    Build a correlation matrix for a set of symbols.
    symbols_data: {symbol: candles_list}
    """
    symbols = list(symbols_data.keys())
    n = len(symbols)
    matrix = {}

    for i, sym_a in enumerate(symbols):
        matrix[sym_a] = {}
        for j, sym_b in enumerate(symbols):
            if i == j:
                matrix[sym_a][sym_b] = 1.0
            elif sym_b in matrix and sym_a in matrix.get(sym_b, {}):
                matrix[sym_a][sym_b] = matrix[sym_b][sym_a]
            else:
                result = calculate_btc_correlation(
                    symbols_data[sym_a],
                    symbols_data[sym_b],
                    periods,
                )
                matrix[sym_a][sym_b] = result.get("correlation", 0.0)

    return {"matrix": matrix, "symbols": symbols, "periods": periods}


class CorrelationEngine:
    def analyze(
        self,
        target_candles: List[Dict],
        btc_candles: List[Dict],
        btc_dominance: float = 50.0,
        prev_btc_dominance: float = 50.0,
    ) -> Dict:
        try:
            btc_correlation = calculate_btc_correlation(btc_candles, target_candles)
            dominance_signal = get_btc_dominance_signal(btc_dominance, prev_btc_dominance)
            return {
                "btc_correlation": btc_correlation,
                "dominance_signal": dominance_signal,
                "high_btc_correlation": btc_correlation.get("is_high_correlation", False),
            }
        except Exception as e:
            logger.error(f"CorrelationEngine analyze error: {e}")
            return {"btc_correlation": {"correlation": 0.0}, "dominance_signal": {}}


correlation_engine = CorrelationEngine()

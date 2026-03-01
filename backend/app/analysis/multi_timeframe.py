import asyncio
import logging
from typing import Dict, List, Optional, Tuple

from app.exchanges.aggregator import aggregator
from app.analysis.smc_engine import smc_engine
from app.analysis.ict_engine import ict_engine, get_kill_zones
from app.analysis.liquidity_engine import liquidity_engine
from app.analysis.wyckoff_engine import wyckoff_engine
from app.analysis.whale_tracker import whale_tracker
from app.analysis.volatility_engine import volatility_engine, calculate_atr

logger = logging.getLogger(__name__)

TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"]
TF_WEIGHTS = {
    "1w": 10,
    "1d": 8,
    "4h": 6,
    "1h": 4,
    "30m": 3,
    "15m": 2,
    "5m": 1,
    "1m": 1,
}


def get_trend_bias(candles_1d: List[Dict], candles_4h: List[Dict]) -> Dict:
    """
    Determine higher timeframe trend direction from daily and 4h candles.
    """
    bias = "neutral"
    description = "No clear trend"

    if len(candles_1d) >= 20:
        closes_1d = [c["close"] for c in candles_1d]
        ma_20 = sum(closes_1d[-20:]) / 20
        current = closes_1d[-1]
        daily_trend = "bullish" if current > ma_20 else "bearish"
    else:
        daily_trend = "neutral"

    if len(candles_4h) >= 20:
        closes_4h = [c["close"] for c in candles_4h]
        ma_20_4h = sum(closes_4h[-20:]) / 20
        current_4h = closes_4h[-1]
        tf4h_trend = "bullish" if current_4h > ma_20_4h else "bearish"
    else:
        tf4h_trend = "neutral"

    if daily_trend == tf4h_trend == "bullish":
        bias = "bullish"
        description = "1D and 4H both bullish - strong uptrend"
    elif daily_trend == tf4h_trend == "bearish":
        bias = "bearish"
        description = "1D and 4H both bearish - strong downtrend"
    elif daily_trend == "bullish" and tf4h_trend == "bearish":
        bias = "bullish_pullback"
        description = "1D bullish but 4H bearish - potential pullback entry"
    elif daily_trend == "bearish" and tf4h_trend == "bullish":
        bias = "bearish_pullback"
        description = "1D bearish but 4H bullish - potential dead cat bounce"
    else:
        bias = "neutral"
        description = "Mixed signals across timeframes"

    return {
        "bias": bias,
        "daily_trend": daily_trend,
        "4h_trend": tf4h_trend,
        "description": description,
    }


def get_entry_timing(candles_15m: List[Dict], candles_5m: List[Dict]) -> Dict:
    """
    Use lower timeframe candles for precise entry timing.
    Looks for momentum confirmation on 5m and 15m.
    """
    timing = "wait"
    description = "No clear entry timing"

    from app.analysis.volatility_engine import calculate_rsi, calculate_atr_percentage
    from app.analysis.smc_engine import detect_bos, detect_fair_value_gaps

    rsi_15m = calculate_rsi(candles_15m) if len(candles_15m) >= 15 else 50.0
    rsi_5m = calculate_rsi(candles_5m) if len(candles_5m) >= 15 else 50.0

    bos_15m = detect_bos(candles_15m) if len(candles_15m) >= 10 else []
    bos_5m = detect_bos(candles_5m) if len(candles_5m) >= 10 else []

    fvg_15m = detect_fair_value_gaps(candles_15m) if len(candles_15m) >= 3 else []
    fvg_5m = detect_fair_value_gaps(candles_5m) if len(candles_5m) >= 3 else []

    long_signals = 0
    short_signals = 0

    if rsi_15m < 40:
        long_signals += 1
    if rsi_15m > 60:
        short_signals += 1
    if rsi_5m < 35:
        long_signals += 1
    if rsi_5m > 65:
        short_signals += 1

    if bos_15m and bos_15m[-1]["type"] == "bullish":
        long_signals += 1
    if bos_15m and bos_15m[-1]["type"] == "bearish":
        short_signals += 1
    if bos_5m and bos_5m[-1]["type"] == "bullish":
        long_signals += 1
    if bos_5m and bos_5m[-1]["type"] == "bearish":
        short_signals += 1

    bull_fvg = any(f["type"] == "bullish" for f in fvg_15m[-3:])
    bear_fvg = any(f["type"] == "bearish" for f in fvg_15m[-3:])
    if bull_fvg:
        long_signals += 1
    if bear_fvg:
        short_signals += 1

    if long_signals >= 3:
        timing = "long_entry"
        description = f"Long entry timing confirmed ({long_signals} signals)"
    elif short_signals >= 3:
        timing = "short_entry"
        description = f"Short entry timing confirmed ({short_signals} signals)"
    elif long_signals >= 2:
        timing = "watch_long"
        description = "Watch for long entry - partial confirmation"
    elif short_signals >= 2:
        timing = "watch_short"
        description = "Watch for short entry - partial confirmation"
    else:
        timing = "wait"
        description = "No clear entry timing - wait for more confirmation"

    return {
        "timing": timing,
        "description": description,
        "long_signals": long_signals,
        "short_signals": short_signals,
        "rsi_15m": rsi_15m,
        "rsi_5m": rsi_5m,
    }


def calculate_confluence_score(timeframe_analyses: Dict[str, Dict]) -> Dict:
    """
    Calculate how many timeframes agree on direction.
    More agreement = higher confluence score.
    """
    bullish_count = 0
    bearish_count = 0
    total_weight = 0
    bullish_weight = 0
    bearish_weight = 0

    for tf, analysis in timeframe_analyses.items():
        if not analysis or "error" in analysis:
            continue
        weight = TF_WEIGHTS.get(tf, 1)
        total_weight += weight

        bias = analysis.get("market_bias", "neutral")
        wyckoff_bias = analysis.get("wyckoff_bias", "neutral")

        # Combine biases
        tf_bullish = sum([
            1 if bias == "bullish" else 0,
            1 if wyckoff_bias == "bullish" else 0,
        ])
        tf_bearish = sum([
            1 if bias == "bearish" else 0,
            1 if wyckoff_bias == "bearish" else 0,
        ])

        if tf_bullish > tf_bearish:
            bullish_count += 1
            bullish_weight += weight
        elif tf_bearish > tf_bullish:
            bearish_count += 1
            bearish_weight += weight

    if total_weight == 0:
        return {"score": 0, "direction": "neutral", "bullish_tfs": 0, "bearish_tfs": 0}

    bull_score = bullish_weight / total_weight * 100
    bear_score = bearish_weight / total_weight * 100

    if bull_score > bear_score:
        direction = "bullish"
        score = bull_score
    elif bear_score > bull_score:
        direction = "bearish"
        score = bear_score
    else:
        direction = "neutral"
        score = 0.0

    return {
        "score": round(score, 1),
        "direction": direction,
        "bullish_tfs": bullish_count,
        "bearish_tfs": bearish_count,
        "bullish_weight": round(bullish_weight, 1),
        "bearish_weight": round(bearish_weight, 1),
        "total_timeframes_analyzed": len(timeframe_analyses),
    }


async def analyze_all_timeframes(symbol: str) -> Dict:
    """
    Fetch and analyze candles on all timeframes for a symbol.
    Returns per-timeframe analysis and overall confluence.
    """
    tf_analyses = {}
    candles_by_tf: Dict[str, List[Dict]] = {}

    async def fetch_and_analyze(tf: str):
        try:
            candles = await aggregator.get_best_candles(symbol, tf, 100)
            if not candles:
                return
            candles_by_tf[tf] = candles

            smc_result = smc_engine.analyze(candles)
            ict_result = ict_engine.analyze(candles)
            liq_result = liquidity_engine.analyze(candles)
            wyckoff_result = wyckoff_engine.analyze(candles)
            vol_result = volatility_engine.analyze(candles)

            tf_analyses[tf] = {
                "timeframe": tf,
                "candle_count": len(candles),
                "current_price": candles[-1]["close"] if candles else 0,
                "market_bias": smc_result.get("market_bias", "neutral"),
                "wyckoff_bias": wyckoff_result.get("wyckoff_bias", "neutral"),
                "smc": smc_result,
                "ict": ict_result,
                "liquidity": liq_result,
                "wyckoff": wyckoff_result,
                "volatility": vol_result,
            }
        except Exception as e:
            logger.warning(f"MTF analyze_all_timeframes {symbol}/{tf} error: {e}")

    await asyncio.gather(*[fetch_and_analyze(tf) for tf in TIMEFRAMES])

    # Higher timeframe trend
    trend_bias = get_trend_bias(
        candles_by_tf.get("1d", []),
        candles_by_tf.get("4h", []),
    )

    # Lower timeframe entry timing
    entry_timing = get_entry_timing(
        candles_by_tf.get("15m", []),
        candles_by_tf.get("5m", []),
    )

    # Confluence score
    confluence = calculate_confluence_score(tf_analyses)

    return {
        "symbol": symbol,
        "timeframe_analyses": tf_analyses,
        "trend_bias": trend_bias,
        "entry_timing": entry_timing,
        "confluence": confluence,
        "candles_by_tf": {tf: len(c) for tf, c in candles_by_tf.items()},
    }


class MultiTimeframeAnalyzer:
    async def analyze(self, symbol: str) -> Dict:
        try:
            return await analyze_all_timeframes(symbol)
        except Exception as e:
            logger.error(f"MultiTimeframeAnalyzer error for {symbol}: {e}")
            return {"symbol": symbol, "error": str(e)}


mtf_analyzer = MultiTimeframeAnalyzer()

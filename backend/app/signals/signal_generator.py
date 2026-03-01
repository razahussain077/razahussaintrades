import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

import pytz

from app.config import settings
from app.exchanges.aggregator import aggregator
from app.exchanges.binance_client import binance_client
from app.analysis.smc_engine import smc_engine
from app.analysis.ict_engine import ict_engine, get_kill_zones
from app.analysis.liquidity_engine import liquidity_engine
from app.analysis.wyckoff_engine import wyckoff_engine
from app.analysis.whale_tracker import whale_tracker
from app.analysis.volatility_engine import volatility_engine, calculate_atr, calculate_atr_percentage
from app.analysis.multi_timeframe import mtf_analyzer
from app.signals.confidence_scorer import confidence_scorer
from app.signals.models import Signal
from app.risk.position_sizer import calculate_position_size
from app.risk.leverage_calculator import calculate_safe_leverage
from app.risk.anti_liquidation import get_liquidation_price

logger = logging.getLogger(__name__)
PKT = pytz.timezone(settings.PKT_TIMEZONE)


def _determine_signal_type(
    smc_result: Dict,
    ict_result: Dict,
    liquidity_result: Dict,
    mtf_result: Dict,
) -> Optional[str]:
    """Determine if setup is LONG or SHORT based on analysis results."""
    long_votes = 0
    short_votes = 0

    # SMC bias
    smc_bias = smc_result.get("market_bias", "neutral")
    if smc_bias == "bullish":
        long_votes += 3
    elif smc_bias == "bearish":
        short_votes += 3

    # ICT OTE direction
    ote = ict_result.get("ote")
    if ote:
        if ote.get("direction") == "bullish" and ote.get("in_ote_zone"):
            long_votes += 2
        elif ote.get("direction") == "bearish" and ote.get("in_ote_zone"):
            short_votes += 2

    # Liquidity sweep direction
    sweep = liquidity_result.get("sweep_reclaim")
    if sweep and sweep.get("detected"):
        if sweep.get("type") == "bullish":
            long_votes += 3
        else:
            short_votes += 3

    stop_hunt = liquidity_result.get("stop_hunt")
    if stop_hunt and stop_hunt.get("detected"):
        if stop_hunt.get("type") == "bullish":
            long_votes += 2
        else:
            short_votes += 2

    # MTF trend
    trend_bias = mtf_result.get("trend_bias", {})
    htf_bias = trend_bias.get("bias", "neutral")
    if "bullish" in htf_bias:
        long_votes += 2
    elif "bearish" in htf_bias:
        short_votes += 2

    # Entry timing
    entry_timing = mtf_result.get("entry_timing", {}).get("timing", "wait")
    if "long" in entry_timing:
        long_votes += 2
    elif "short" in entry_timing:
        short_votes += 2

    if long_votes > short_votes and long_votes >= 4:
        return "LONG"
    elif short_votes > long_votes and short_votes >= 4:
        return "SHORT"
    return None


def _calculate_entry_zone(
    candles: List[Dict],
    signal_type: str,
    smc_result: Dict,
    ict_result: Dict,
) -> tuple:
    """Calculate optimal entry zone (low, high)."""
    current_price = candles[-1]["close"] if candles else 0
    atr = calculate_atr(candles) if candles else 0
    atr_pct = calculate_atr_percentage(candles)

    if signal_type == "LONG":
        # Prefer OTE zone or bullish OB
        ote = ict_result.get("ote")
        if ote and ote.get("in_ote_zone") and ote.get("direction") == "bullish":
            entry_low = ote["ote_zone_low"]
            entry_high = ote["ote_zone_high"]
        else:
            ob = smc_result.get("nearest_bullish_ob")
            if ob:
                entry_low = ob["bottom"]
                entry_high = ob["top"]
            else:
                # Entry around current price with small range
                entry_low = current_price * (1 - atr_pct / 100)
                entry_high = current_price * (1 + atr_pct / 200)
    else:
        # SHORT
        ote = ict_result.get("ote")
        if ote and ote.get("in_ote_zone") and ote.get("direction") == "bearish":
            entry_low = ote["ote_zone_low"]
            entry_high = ote["ote_zone_high"]
        else:
            ob = smc_result.get("nearest_bearish_ob")
            if ob:
                entry_low = ob["bottom"]
                entry_high = ob["top"]
            else:
                entry_low = current_price * (1 - atr_pct / 200)
                entry_high = current_price * (1 + atr_pct / 100)

    return (round(entry_low, 8), round(entry_high, 8))


def _calculate_stop_loss(
    candles: List[Dict],
    signal_type: str,
    entry_price: float,
    smc_result: Dict,
    liquidity_result: Dict,
) -> float:
    """Calculate stop loss based on structure and ATR."""
    atr = calculate_atr(candles) if candles else entry_price * 0.01

    if signal_type == "LONG":
        # SL below nearest support structure
        nearest_liquidity_below = liquidity_result.get("nearest_liquidity_below")
        if nearest_liquidity_below:
            sl = nearest_liquidity_below * 0.999  # just below liquidity
        else:
            ob = smc_result.get("nearest_bullish_ob")
            if ob:
                sl = ob["low"] - atr * 0.5
            else:
                sl = entry_price - atr * 2
    else:
        # SL above nearest resistance structure
        nearest_liquidity_above = liquidity_result.get("nearest_liquidity_above")
        if nearest_liquidity_above:
            sl = nearest_liquidity_above * 1.001
        else:
            ob = smc_result.get("nearest_bearish_ob")
            if ob:
                sl = ob["high"] + atr * 0.5
            else:
                sl = entry_price + atr * 2

    return round(sl, 8)


def _calculate_take_profits(
    entry_price: float,
    stop_loss: float,
    signal_type: str,
    liquidity_result: Dict,
    smc_result: Dict,
) -> tuple:
    """Calculate 3 take profit levels using RR ratios."""
    risk = abs(entry_price - stop_loss)

    if signal_type == "LONG":
        tp1 = entry_price + risk * 1.5
        tp2 = entry_price + risk * 2.5
        tp3 = entry_price + risk * 4.0

        # Use liquidity as target if available
        nearest_above = liquidity_result.get("nearest_liquidity_above")
        if nearest_above and nearest_above > entry_price + risk * 1.2:
            tp1 = nearest_above * 0.999

        # Use equal highs for TP2 if higher
        eq_highs = liquidity_result.get("equal_highs", [])
        if eq_highs:
            sorted_highs = sorted([z["level"] for z in eq_highs if z["level"] > tp1])
            if sorted_highs:
                tp2 = max(tp2, sorted_highs[0])
    else:
        tp1 = entry_price - risk * 1.5
        tp2 = entry_price - risk * 2.5
        tp3 = entry_price - risk * 4.0

        nearest_below = liquidity_result.get("nearest_liquidity_below")
        if nearest_below and nearest_below < entry_price - risk * 1.2:
            tp1 = nearest_below * 1.001

        eq_lows = liquidity_result.get("equal_lows", [])
        if eq_lows:
            sorted_lows = sorted([z["level"] for z in eq_lows if z["level"] < tp1], reverse=True)
            if sorted_lows:
                tp2 = min(tp2, sorted_lows[0])

    return (round(tp1, 8), round(tp2, 8), round(tp3, 8))


def _determine_setup_type(
    smc_result: Dict,
    ict_result: Dict,
    liquidity_result: Dict,
    wyckoff_result: Dict,
) -> str:
    """Determine the primary setup type for labeling."""
    if liquidity_result.get("sweep_reclaim", {}) and liquidity_result.get("sweep_reclaim", {}).get("detected"):
        return "Liquidity Sweep & Reclaim"

    ote = ict_result.get("ote", {})
    if ote and ote.get("in_ote_zone"):
        return "ICT OTE (Optimal Trade Entry)"

    if ict_result.get("silver_bullet", {}) and ict_result.get("silver_bullet", {}).get("detected"):
        return "ICT Silver Bullet"

    if ict_result.get("judas_swing", {}) and ict_result.get("judas_swing", {}).get("detected"):
        return "ICT Judas Swing Reversal"

    phase = wyckoff_result.get("phase", {}).get("phase", "")
    if wyckoff_result.get("spring", {}) and wyckoff_result.get("spring", {}).get("detected"):
        return "Wyckoff Spring (Accumulation)"
    if wyckoff_result.get("upthrust", {}) and wyckoff_result.get("upthrust", {}).get("detected"):
        return "Wyckoff Upthrust (Distribution)"

    if smc_result.get("nearest_bullish_ob") or smc_result.get("nearest_bearish_ob"):
        if smc_result.get("latest_choch"):
            return "SMC CHoCH + Order Block"
        return "SMC Order Block"

    if smc_result.get("bullish_fvgs_below") or smc_result.get("bearish_fvgs_above"):
        return "SMC Fair Value Gap"

    if liquidity_result.get("stop_hunt", {}) and liquidity_result.get("stop_hunt", {}).get("detected"):
        return "Stop Hunt Reversal"

    return "Technical Confluence"


async def generate_signal(symbol: str) -> Optional[Signal]:
    """
    Main orchestrator: run all engines and generate a signal if confidence >= 60.
    """
    try:
        # Fetch price data
        price = await binance_client.get_price(symbol)
        if price == 0:
            return None

        # Fetch candles for primary timeframe (1h)
        candles_1h = await aggregator.get_best_candles(symbol, "1h", 100)
        if len(candles_1h) < 30:
            logger.warning(f"Insufficient 1h candles for {symbol}")
            return None

        # Fetch order book
        order_book = await binance_client.get_order_book(symbol, 20)

        # Run analysis engines on 1h candles
        smc_result = smc_engine.analyze(candles_1h)
        ict_result = ict_engine.analyze(candles_1h)
        liquidity_result = liquidity_engine.analyze(candles_1h)
        wyckoff_result = wyckoff_engine.analyze(candles_1h)
        whale_result = whale_tracker.analyze(candles_1h, order_book)
        vol_result = volatility_engine.analyze(candles_1h)

        # Multi-timeframe analysis
        mtf_result = await mtf_analyzer.analyze(symbol)

        # Determine signal direction
        signal_type = _determine_signal_type(smc_result, ict_result, liquidity_result, mtf_result)
        if signal_type is None:
            return None

        # Score the signal
        score_result = confidence_scorer.score(
            smc_result, ict_result, liquidity_result, wyckoff_result, mtf_result, signal_type
        )
        confidence_score = score_result.get("confidence_score", 0)

        if confidence_score < settings.MIN_CONFIDENCE_SCORE:
            logger.debug(f"Signal for {symbol} below threshold: {confidence_score:.1f}")
            return None

        # Calculate entry zone
        entry_low, entry_high = _calculate_entry_zone(candles_1h, signal_type, smc_result, ict_result)
        entry_mid = (entry_low + entry_high) / 2

        # Calculate stop loss
        stop_loss = _calculate_stop_loss(candles_1h, signal_type, entry_mid, smc_result, liquidity_result)

        # Calculate take profits
        tp1, tp2, tp3 = _calculate_take_profits(entry_mid, stop_loss, signal_type, liquidity_result, smc_result)

        # Calculate risk percentages
        risk_pct = abs(entry_mid - stop_loss) / entry_mid * 100
        tp1_pct = abs(tp1 - entry_mid) / entry_mid * 100
        tp2_pct = abs(tp2 - entry_mid) / entry_mid * 100
        tp3_pct = abs(tp3 - entry_mid) / entry_mid * 100

        # Risk/reward
        rr = tp2_pct / risk_pct if risk_pct > 0 else 0

        # Safe leverage
        nearest_liq_zone = liquidity_result.get("nearest_liquidity_below") or (entry_mid * 0.9)
        if signal_type == "SHORT":
            nearest_liq_zone = liquidity_result.get("nearest_liquidity_above") or (entry_mid * 1.1)

        leverage = calculate_safe_leverage(entry_mid, nearest_liq_zone)
        liquidation_price = get_liquidation_price(entry_mid, leverage, signal_type)

        # Setup type
        setup_type = _determine_setup_type(smc_result, ict_result, liquidity_result, wyckoff_result)

        # Reasoning
        reasoning = score_result.get("reasoning", [])
        if whale_result.get("is_whale_active"):
            reasoning.append(f"Whale activity detected: score {whale_result.get('whale_score', 0):.0f}/100")
        if vol_result.get("is_overbought"):
            reasoning.append(f"RSI overbought ({vol_result.get('rsi', 0):.1f}) - confirms short bias")
        if vol_result.get("is_oversold"):
            reasoning.append(f"RSI oversold ({vol_result.get('rsi', 0):.1f}) - confirms long bias")

        # Kill zone info
        kill_zones = get_kill_zones()
        kill_zone_name = kill_zones.get("active_session", "Off Hours")

        # Invalidation
        if signal_type == "LONG":
            invalidation = f"Price closes below {stop_loss:.4f} - setup invalidated"
        else:
            invalidation = f"Price closes above {stop_loss:.4f} - setup invalidated"

        now_pkt = datetime.now(timezone.utc).astimezone(PKT)

        signal = Signal(
            id=str(uuid.uuid4()),
            coin=symbol,
            exchange="binance",
            signal_type=signal_type,
            timeframe="1h",
            entry_low=entry_low,
            entry_high=entry_high,
            stop_loss=stop_loss,
            stop_loss_pct=round(risk_pct, 3),
            take_profit_1=tp1,
            take_profit_1_pct=round(tp1_pct, 3),
            take_profit_2=tp2,
            take_profit_2_pct=round(tp2_pct, 3),
            take_profit_3=tp3,
            take_profit_3_pct=round(tp3_pct, 3),
            recommended_leverage=leverage,
            liquidation_price=liquidation_price,
            risk_reward=round(rr, 2),
            confidence_score=confidence_score,
            setup_type=setup_type,
            reasoning=reasoning,
            invalidation=invalidation,
            kill_zone=kill_zone_name,
            created_at=now_pkt,
            is_active=True,
        )
        return signal

    except Exception as e:
        logger.error(f"generate_signal error for {symbol}: {e}")
        return None


async def scan_all_coins() -> List[Signal]:
    """Scan all top 50 coins and return valid signals."""
    signals = []
    semaphore = asyncio.Semaphore(5)  # Limit concurrent requests

    async def scan_one(symbol: str):
        async with semaphore:
            try:
                signal = await generate_signal(symbol)
                if signal:
                    signals.append(signal)
                    logger.info(f"Signal generated for {symbol}: {signal.signal_type} confidence={signal.confidence_score}")
            except Exception as e:
                logger.warning(f"scan_one failed for {symbol}: {e}")

    await asyncio.gather(*[scan_one(s) for s in settings.TOP_50_COINS])
    return sorted(signals, key=lambda s: s.confidence_score, reverse=True)


class SignalGenerator:
    async def generate(self, symbol: str) -> Optional[Signal]:
        return await generate_signal(symbol)

    async def scan_all(self) -> List[Signal]:
        return await scan_all_coins()


signal_generator = SignalGenerator()

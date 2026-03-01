import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def score_signal(
    smc_result: Dict,
    ict_result: Dict,
    liquidity_result: Dict,
    wyckoff_result: Dict,
    mtf_result: Dict,
    signal_type: str,
) -> Dict:
    """
    Score a trading signal 0-100 based on confluence of analysis engines.

    SMC confluences (order block + FVG + BOS/CHoCH):   up to 30 points
    ICT confluences (OTE + kill zone + inst candle):    up to 25 points
    Liquidity (sweep + reclaim):                        up to 20 points
    Wyckoff alignment:                                  up to 10 points
    Multi-timeframe agreement:                          up to 15 points
    """
    score = 0.0
    reasoning: List[str] = []

    is_long = signal_type.upper() == "LONG"

    # =========================================================
    # 1. SMC Confluences - max 30 points
    # =========================================================
    smc_points = 0.0

    # Order block alignment (up to 10 pts)
    if is_long:
        ob = smc_result.get("nearest_bullish_ob")
        if ob:
            smc_points += 10
            reasoning.append(f"Bullish order block at {ob.get('top', 0):.4f}")
    else:
        ob = smc_result.get("nearest_bearish_ob")
        if ob:
            smc_points += 10
            reasoning.append(f"Bearish order block at {ob.get('bottom', 0):.4f}")

    # FVG alignment (up to 10 pts)
    if is_long:
        bull_fvgs = smc_result.get("bullish_fvgs_below", [])
        if bull_fvgs:
            smc_points += 8
            reasoning.append(f"Bullish FVG(s) below price: {len(bull_fvgs)} found")
    else:
        bear_fvgs = smc_result.get("bearish_fvgs_above", [])
        if bear_fvgs:
            smc_points += 8
            reasoning.append(f"Bearish FVG(s) above price: {len(bear_fvgs)} found")

    # BOS / CHoCH confirmation (up to 10 pts)
    latest_bos = smc_result.get("latest_bos")
    latest_choch = smc_result.get("latest_choch")
    if latest_bos:
        if (is_long and latest_bos.get("type") == "bullish") or (not is_long and latest_bos.get("type") == "bearish"):
            smc_points += 7
            reasoning.append(f"BOS {'bullish' if is_long else 'bearish'} confirmed")
    if latest_choch:
        if (is_long and latest_choch.get("type") == "bullish") or (not is_long and latest_choch.get("type") == "bearish"):
            smc_points += 5
            reasoning.append(f"CHoCH {'bullish' if is_long else 'bearish'} - trend shift")

    # Premium/discount zone bonus
    if is_long and smc_result.get("in_discount"):
        smc_points += 5
        reasoning.append("Price in discount zone - ideal for longs")
    elif not is_long and smc_result.get("in_premium"):
        smc_points += 5
        reasoning.append("Price in premium zone - ideal for shorts")

    smc_points = min(30, smc_points)
    score += smc_points

    # =========================================================
    # 2. ICT Confluences - max 25 points
    # =========================================================
    ict_points = 0.0

    # OTE zone alignment (up to 10 pts)
    ote = ict_result.get("ote")
    if ote and ote.get("in_ote_zone"):
        ot_dir = ote.get("direction")
        if (is_long and ot_dir == "bullish") or (not is_long and ot_dir == "bearish"):
            ict_points += 10
            reasoning.append(
                f"OTE zone active: 61.8-78.6% fib retracement (zone: {ote.get('ote_zone_low', 0):.4f} - {ote.get('ote_zone_high', 0):.4f})"
            )

    # Kill zone bonus (up to 8 pts)
    if ict_result.get("is_kill_zone"):
        ict_points += 8
        reasoning.append(f"Trading during kill zone: {ict_result.get('active_session', 'Active session')}")
    elif ict_result.get("active_session") not in ("Off Hours", None):
        ict_points += 3
        reasoning.append(f"Active session: {ict_result.get('active_session')}")

    # Institutional candle (up to 7 pts)
    inst_candle = ict_result.get("institutional_candle")
    if inst_candle and inst_candle.get("detected"):
        candle_dir = inst_candle.get("direction")
        if (is_long and candle_dir == "bullish") or (not is_long and candle_dir == "bearish"):
            ict_points += 7
            reasoning.append(
                f"Institutional {'bullish' if is_long else 'bearish'} candle: "
                f"{inst_candle.get('body_ratio', 0)}% body, {inst_candle.get('volume_spike', 1)}x volume"
            )

    # Silver Bullet (bonus)
    silver = ict_result.get("silver_bullet")
    if silver and silver.get("detected"):
        silver_dir = silver.get("type")
        if (is_long and silver_dir == "bullish") or (not is_long and silver_dir == "bearish"):
            ict_points += 5
            reasoning.append(f"ICT Silver Bullet pattern: {silver.get('description', '')}")

    # Judas Swing
    judas = ict_result.get("judas_swing")
    if judas and judas.get("detected"):
        judas_dir = judas.get("direction")
        if (is_long and judas_dir == "bullish") or (not is_long and judas_dir == "bearish"):
            ict_points += 5
            reasoning.append(f"Judas swing {judas_dir} reversal detected")

    ict_points = min(25, ict_points)
    score += ict_points

    # =========================================================
    # 3. Liquidity - max 20 points
    # =========================================================
    liq_points = 0.0

    # Stop hunt / sweep
    stop_hunt = liquidity_result.get("stop_hunt")
    if stop_hunt and stop_hunt.get("detected"):
        sh_dir = stop_hunt.get("type")
        if (is_long and sh_dir == "bullish") or (not is_long and sh_dir == "bearish"):
            liq_points += 10
            reasoning.append(stop_hunt.get("description", "Stop hunt detected"))

    # Sweep and reclaim (high probability)
    sweep = liquidity_result.get("sweep_reclaim")
    if sweep and sweep.get("detected"):
        sw_dir = sweep.get("type")
        if (is_long and sw_dir == "bullish") or (not is_long and sw_dir == "bearish"):
            liq_points += 15
            reasoning.append(sweep.get("description", "Liquidity sweep and reclaim"))

    # Nearby equal highs/lows as target
    if is_long:
        eq_highs = liquidity_result.get("equal_highs", [])
        nearest_above = liquidity_result.get("nearest_liquidity_above")
        if eq_highs:
            liq_points += 3
            reasoning.append(f"Equal highs above price as liquidity target")
    else:
        eq_lows = liquidity_result.get("equal_lows", [])
        nearest_below = liquidity_result.get("nearest_liquidity_below")
        if eq_lows:
            liq_points += 3
            reasoning.append(f"Equal lows below price as liquidity target")

    liq_points = min(20, liq_points)
    score += liq_points

    # =========================================================
    # 4. Wyckoff Alignment - max 10 points
    # =========================================================
    wyckoff_points = 0.0
    wyckoff_bias = wyckoff_result.get("wyckoff_bias", "neutral")
    phase = wyckoff_result.get("phase", {}).get("phase", "Unknown")

    if (is_long and wyckoff_bias == "bullish") or (not is_long and wyckoff_bias == "bearish"):
        wyckoff_points += 8
        reasoning.append(f"Wyckoff bias aligns: {wyckoff_bias} in {phase} phase")
    elif wyckoff_bias == "neutral":
        wyckoff_points += 2

    # Spring / Upthrust bonus
    if is_long:
        spring = wyckoff_result.get("spring")
        if spring and spring.get("detected"):
            wyckoff_points += 3
            reasoning.append(f"Wyckoff Spring: {spring.get('description', '')}")
    else:
        upthrust = wyckoff_result.get("upthrust")
        if upthrust and upthrust.get("detected"):
            wyckoff_points += 3
            reasoning.append(f"Wyckoff Upthrust: {upthrust.get('description', '')}")

    wyckoff_points = min(10, wyckoff_points)
    score += wyckoff_points

    # =========================================================
    # 5. Multi-Timeframe Agreement - max 15 points
    # =========================================================
    mtf_points = 0.0

    confluence = mtf_result.get("confluence", {})
    conf_direction = confluence.get("direction", "neutral")
    conf_score = confluence.get("score", 0)

    if (is_long and conf_direction == "bullish") or (not is_long and conf_direction == "bearish"):
        mtf_points += conf_score * 0.15  # Normalize to 15 pts
        reasoning.append(
            f"MTF confluence: {confluence.get('bullish_tfs' if is_long else 'bearish_tfs', 0)} "
            f"timeframes aligned ({conf_score:.0f}% weight)"
        )

    # Higher TF trend alignment
    trend_bias = mtf_result.get("trend_bias", {})
    htf_bias = trend_bias.get("bias", "neutral")
    if (is_long and htf_bias in ("bullish", "bullish_pullback")) or (not is_long and htf_bias in ("bearish", "bearish_pullback")):
        mtf_points += 3
        reasoning.append(f"HTF trend: {trend_bias.get('description', htf_bias)}")

    mtf_points = min(15, mtf_points)
    score += mtf_points

    total_score = min(100, round(score, 1))

    return {
        "confidence_score": total_score,
        "smc_points": round(smc_points, 1),
        "ict_points": round(ict_points, 1),
        "liquidity_points": round(liq_points, 1),
        "wyckoff_points": round(wyckoff_points, 1),
        "mtf_points": round(mtf_points, 1),
        "reasoning": reasoning,
        "passes_threshold": total_score >= 60,
    }


class ConfidenceScorer:
    def score(
        self,
        smc_result: Dict,
        ict_result: Dict,
        liquidity_result: Dict,
        wyckoff_result: Dict,
        mtf_result: Dict,
        signal_type: str,
    ) -> Dict:
        try:
            return score_signal(
                smc_result,
                ict_result,
                liquidity_result,
                wyckoff_result,
                mtf_result,
                signal_type,
            )
        except Exception as e:
            logger.error(f"ConfidenceScorer error: {e}")
            return {"confidence_score": 0.0, "reasoning": [], "passes_threshold": False}


confidence_scorer = ConfidenceScorer()

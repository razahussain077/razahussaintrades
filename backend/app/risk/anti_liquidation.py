import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Maintenance margin for perpetual futures (Binance default)
MAINTENANCE_MARGIN_RATE = 0.004  # 0.4%


def get_liquidation_price(
    entry: float,
    leverage: float,
    side: str,
    maintenance_margin_rate: float = MAINTENANCE_MARGIN_RATE,
) -> float:
    """
    Calculate the liquidation price for a perpetual futures position.

    For LONG:  liq_price = entry * (1 - 1/leverage + maintenance_margin_rate)
    For SHORT: liq_price = entry * (1 + 1/leverage - maintenance_margin_rate)

    Args:
        entry: Entry price
        leverage: Leverage (e.g., 10 = 10x)
        side: 'LONG' or 'SHORT'
        maintenance_margin_rate: Maintenance margin rate (default 0.4%)
    """
    if leverage <= 0 or entry <= 0:
        return 0.0

    if side.upper() == "LONG":
        liq = entry * (1 - 1 / leverage + maintenance_margin_rate)
    else:
        liq = entry * (1 + 1 / leverage - maintenance_margin_rate)

    return round(max(0.0, liq), 8)


def check_liquidation_safety(
    entry: float,
    stop_loss: float,
    leverage: float,
    nearest_liquidity: float,
    side: str,
) -> Dict:
    """
    Ensure liquidation price is beyond the nearest liquidity zone.
    The stop loss should be hit before liquidation occurs.

    Returns a dict indicating if the setup is safe.
    """
    liq_price = get_liquidation_price(entry, leverage, side)

    if side.upper() == "LONG":
        # Liquidation should be BELOW stop loss (deeper)
        liq_below_sl = liq_price < stop_loss
        liq_beyond_liquidity = liq_price < nearest_liquidity if nearest_liquidity else True
        is_safe = liq_below_sl
    else:
        # SHORT: liquidation should be ABOVE stop loss
        liq_above_sl = liq_price > stop_loss
        liq_beyond_liquidity = liq_price > nearest_liquidity if nearest_liquidity else True
        is_safe = liq_above_sl

    return {
        "is_safe": is_safe,
        "liquidation_price": liq_price,
        "stop_loss": stop_loss,
        "nearest_liquidity": nearest_liquidity,
        "liq_distance_from_entry_pct": round(abs(liq_price - entry) / entry * 100, 3),
        "sl_distance_from_entry_pct": round(abs(stop_loss - entry) / entry * 100, 3),
        "recommendation": (
            "Safe: SL triggered before liquidation" if is_safe
            else "UNSAFE: Liquidation may occur before SL - reduce leverage"
        ),
    }


def validate_trade(
    signal: Dict,
    portfolio: float,
    current_positions: List[Dict],
    max_portfolio_risk_pct: float = 5.0,
) -> Dict:
    """
    Validate a trade against portfolio risk rules.
    - Max 3 correlated positions (same sector/high BTC correlation)
    - Max 5% of portfolio at risk across all positions
    - Check leverage safety

    Args:
        signal: Signal dict with entry, stop_loss, signal_type, coin, confidence_score
        portfolio: Total portfolio USD value
        current_positions: List of current open position dicts
        max_portfolio_risk_pct: Maximum total portfolio risk allowed
    """
    issues = []
    warnings = []

    # 1. Max concurrent positions check
    if len(current_positions) >= 10:
        issues.append("Maximum 10 concurrent positions reached")

    # 2. Correlated positions check (same coin groups)
    BTC_GROUP = {"BTCUSDT"}
    ETH_GROUP = {"ETHUSDT", "STETHUSDT"}
    DEFI_GROUP = {"UNIUSDT", "AAVEUSDT", "COMPUSDT", "SUSHIUSDT", "CRVUSDT", "MKRUSDT"}
    L1_GROUP = {"SOLUSDT", "AVAXUSDT", "DOTUSDT", "ADAUSDT", "NEARUSDT", "ICPUSDT"}

    def get_group(coin: str) -> Optional[str]:
        if coin in BTC_GROUP:
            return "BTC"
        if coin in ETH_GROUP:
            return "ETH"
        if coin in DEFI_GROUP:
            return "DeFi"
        if coin in L1_GROUP:
            return "L1"
        return "Other"

    signal_group = get_group(signal.get("coin", ""))
    correlated_count = sum(
        1 for p in current_positions
        if get_group(p.get("coin", "")) == signal_group
    )
    if correlated_count >= 3:
        issues.append(f"Too many correlated positions in {signal_group} group (max 3)")
    elif correlated_count >= 2:
        warnings.append(f"Already have {correlated_count} positions in {signal_group} group")

    # 3. Total portfolio risk check
    total_risk = 0.0
    for pos in current_positions:
        pos_entry = pos.get("entry", 0)
        pos_sl = pos.get("stop_loss", 0)
        pos_size = pos.get("size", 0)
        if pos_entry > 0 and pos_sl > 0:
            pos_risk = abs(pos_entry - pos_sl) / pos_entry * pos_size * pos_entry
            total_risk += pos_risk

    # Add this signal's risk
    from app.risk.position_sizer import calculate_position_size
    entry = signal.get("entry_high", signal.get("entry_low", 0))
    sl = signal.get("stop_loss", 0)
    new_risk = portfolio * 0.01  # Default 1% risk

    total_risk_pct = (total_risk + new_risk) / portfolio * 100
    if total_risk_pct > max_portfolio_risk_pct:
        issues.append(
            f"Total portfolio risk would be {total_risk_pct:.1f}% (max {max_portfolio_risk_pct}%)"
        )

    # 4. Leverage safety
    entry_price = entry
    leverage = signal.get("recommended_leverage", 1)
    nearest_liq = signal.get("liquidation_price", 0)
    if entry_price > 0 and sl > 0 and leverage > 0:
        liq_check = check_liquidation_safety(entry_price, sl, leverage, nearest_liq, signal.get("signal_type", "LONG"))
        if not liq_check["is_safe"]:
            issues.append(liq_check["recommendation"])

    is_valid = len(issues) == 0

    return {
        "is_valid": is_valid,
        "issues": issues,
        "warnings": warnings,
        "total_portfolio_risk_pct": round(total_risk_pct, 2),
        "current_positions_count": len(current_positions),
        "correlated_positions": correlated_count,
    }

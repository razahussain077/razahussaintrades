from app.config import settings


def calculate_safe_leverage(
    entry_price: float,
    nearest_liquidity_zone: float,
    safety_margin: float = 1.5,
) -> float:
    """
    Calculate safe leverage based on distance to nearest liquidity zone.
    Formula: max_safe_leverage = (distance% * 100) / safety_margin
    Recommended = max_safe_leverage * 0.5, capped at MAX_LEVERAGE (default 10x).
    """
    if nearest_liquidity_zone <= 0 or entry_price <= 0:
        return 1.0

    distance = abs(entry_price - nearest_liquidity_zone) / entry_price
    if distance == 0:
        return 1.0

    max_safe_leverage = (distance * 100) / safety_margin
    recommended = max_safe_leverage * 0.5

    return round(min(recommended, settings.MAX_LEVERAGE), 1)


def dynamic_leverage(
    atr_pct: float,
    confidence_score: float,
    max_lev: float = 10.0,
) -> float:
    """
    Adjust leverage based on volatility (ATR%) and signal confidence.
    Lower volatility + higher confidence = higher leverage allowed.

    Args:
        atr_pct: ATR as percentage of price (e.g., 2.5 means 2.5%)
        confidence_score: 0-100 signal confidence
        max_lev: hard cap on leverage
    """
    if atr_pct <= 0:
        atr_pct = 1.0

    # Base leverage inversely proportional to volatility
    base = 100 / (atr_pct * 10)  # 1% ATR -> 10x base, 2% -> 5x base

    # Confidence multiplier: 60 confidence = 0.6x, 100 = 1.0x
    conf_mult = max(0.5, confidence_score / 100)
    leverage = base * conf_mult

    return round(min(leverage, max_lev, settings.MAX_LEVERAGE), 1)

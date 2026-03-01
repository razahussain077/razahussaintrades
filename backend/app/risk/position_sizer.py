def calculate_position_size(
    portfolio: float,
    risk_pct: float,
    entry: float,
    stop_loss: float,
) -> float:
    """
    Calculate position size (in base units) based on portfolio risk.

    Args:
        portfolio: Total portfolio value in USD
        risk_pct: Percentage of portfolio to risk (e.g., 1.0 = 1%)
        entry: Entry price
        stop_loss: Stop loss price

    Returns:
        position_size: Number of units to buy/sell
    """
    if entry <= 0 or stop_loss <= 0:
        return 0.0

    price_risk = abs(entry - stop_loss)
    if price_risk == 0:
        return 0.0

    risk_amount = portfolio * (risk_pct / 100)
    position_size = risk_amount / price_risk

    return round(position_size, 8)


def calculate_position_value(
    portfolio: float,
    risk_pct: float,
    entry: float,
    stop_loss: float,
) -> dict:
    """
    Full position calculation with value, margin, etc.

    Returns dict with position_size, position_value, risk_amount, margin_required.
    """
    position_size = calculate_position_size(portfolio, risk_pct, entry, stop_loss)
    risk_amount = portfolio * (risk_pct / 100)
    position_value = position_size * entry

    return {
        "position_size": position_size,
        "position_value": round(position_value, 4),
        "risk_amount": round(risk_amount, 4),
        "risk_pct": risk_pct,
        "entry": entry,
        "stop_loss": stop_loss,
        "price_risk_pct": round(abs(entry - stop_loss) / entry * 100, 4),
    }

"""
Portfolio Risk & Exposure Engine — Feature 4
Position sizing, liquidation calculator, correlation guard, daily loss tracker.
"""
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# In-memory state
_active_signals: List[Dict] = []
_risk_settings: Dict = {
    "balance": 1000.0,
    "risk_pct": 1.0,
    "max_trades": 5,
}
_daily_pnl: float = 0.0
_daily_reset_date: Optional[str] = None

# Correlated asset groups
CORRELATION_GROUPS = [
    {"name": "Large Cap", "symbols": ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"]},
    {"name": "L1 Alts", "symbols": ["AVAXUSDT", "DOTUSDT", "ATOMUSDT", "NEARUSDT", "ADAUSDT"]},
    {"name": "DeFi", "symbols": ["AAVEUSDT", "UNIUSDT", "CRVUSDT", "COMPUSDT", "SUSHIUSDT"]},
    {"name": "GameFi/NFT", "symbols": ["SANDUSDT", "MANAUSDT", "AXSUSDT", "ENJUSDT"]},
]


def _reset_daily_if_needed() -> None:
    global _daily_pnl, _daily_reset_date
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if _daily_reset_date != today:
        _daily_pnl = 0.0
        _daily_reset_date = today


def calculate_position_size(
    balance: float,
    risk_pct: float,
    entry_price: float,
    stop_loss_price: float,
) -> Dict:
    """
    Calculate position size using fixed risk formula.
    position_size = (balance * risk_pct/100) / |entry_price - stop_loss_price|
    """
    if balance <= 0 or entry_price <= 0 or stop_loss_price <= 0:
        return {"error": "Invalid inputs"}

    risk_amount = balance * (risk_pct / 100)
    sl_distance = abs(entry_price - stop_loss_price)
    if sl_distance == 0:
        return {"error": "Entry price equals stop loss"}

    position_size = risk_amount / sl_distance
    position_value = position_size * entry_price

    return {
        "position_size": round(position_size, 6),
        "position_value": round(position_value, 2),
        "risk_amount": round(risk_amount, 2),
        "risk_pct": risk_pct,
        "sl_distance": round(sl_distance, 8),
        "sl_distance_pct": round(sl_distance / entry_price * 100, 3),
    }


def suggest_leverage(confidence_score: float) -> Dict:
    """
    Suggest leverage based on signal confidence score.
    Low confidence (60-70%) = 3-5x
    Medium (70-80%) = 5-10x
    High (80%+) = 10-20x (never above 20x)
    """
    if confidence_score >= 80:
        leverage = min(20, int(confidence_score / 5))
        tier = "high"
    elif confidence_score >= 70:
        leverage = min(10, max(5, int(confidence_score / 8)))
        tier = "medium"
    else:
        leverage = min(5, max(3, int(confidence_score / 15)))
        tier = "low"

    return {
        "suggested_leverage": leverage,
        "tier": tier,
        "note": f"Based on {confidence_score:.0f}% signal confidence — never exceed 20x",
    }


def get_liquidation_price(entry_price: float, leverage: float, side: str) -> float:
    """Calculate exact liquidation price."""
    if leverage <= 0:
        return 0.0
    if side == "LONG":
        return round(entry_price * (1 - 1 / leverage), 8)
    else:
        return round(entry_price * (1 + 1 / leverage), 8)


def check_correlation_risk(signal_type: str, symbol: str, active_signals: List[Dict]) -> Dict:
    """
    Check if adding this signal creates high correlation risk.
    Warn if 3+ signals are the same direction on correlated assets.
    """
    warnings = []
    same_dir_count = 0

    for group in CORRELATION_GROUPS:
        if symbol not in group["symbols"]:
            continue

        group_signals = [
            s for s in active_signals
            if s.get("coin") in group["symbols"] and s.get("signal_type") == signal_type
        ]

        if len(group_signals) >= 2:  # Would become 3 with new signal
            same_dir_count = len(group_signals) + 1
            symbols_str = ", ".join(s.get("coin", "") for s in group_signals)
            warnings.append(
                f"⚠️ High correlation risk — {same_dir_count} {signal_type} positions on {group['name']} assets ({symbols_str} + {symbol})"
            )

    return {
        "has_correlation_risk": len(warnings) > 0,
        "warnings": warnings,
        "same_direction_correlated_count": same_dir_count,
    }


def get_portfolio_exposure(active_signals: List[Dict], balance: float) -> Dict:
    """Calculate current portfolio exposure summary."""
    _reset_daily_if_needed()

    long_count = sum(1 for s in active_signals if s.get("signal_type") == "LONG")
    short_count = sum(1 for s in active_signals if s.get("signal_type") == "SHORT")
    total_count = len(active_signals)

    # Estimate total risk exposure
    total_risk_usd = 0.0
    for sig in active_signals:
        # Estimate 1.5% risk per trade (default)
        total_risk_usd += balance * 0.015

    # Risk meter
    exposure_pct = (total_count / max(_risk_settings.get("max_trades", 5), 1)) * 100
    if exposure_pct >= 80:
        risk_level = "red"
        risk_label = "Over-Exposed"
    elif exposure_pct >= 50:
        risk_level = "yellow"
        risk_label = "Moderate"
    else:
        risk_level = "green"
        risk_label = "Safe"

    # Daily loss check
    daily_loss_pct = (_daily_pnl / balance * 100) if balance > 0 else 0
    daily_loss_warning = daily_loss_pct < -5

    return {
        "total_open_signals": total_count,
        "long_count": long_count,
        "short_count": short_count,
        "long_short_ratio": round(long_count / max(short_count, 1), 2),
        "total_risk_usd": round(total_risk_usd, 2),
        "daily_pnl": round(_daily_pnl, 2),
        "daily_pnl_pct": round(daily_loss_pct, 2),
        "daily_loss_warning": daily_loss_warning,
        "daily_loss_message": "🛑 Daily loss limit reached — signals still shown but marked HIGH RISK" if daily_loss_warning else None,
        "risk_level": risk_level,
        "risk_label": risk_label,
        "max_trades": _risk_settings.get("max_trades", 5),
        "over_max_warning": total_count >= _risk_settings.get("max_trades", 5),
    }


def update_risk_settings(settings: Dict) -> None:
    """Update risk settings."""
    global _risk_settings
    _risk_settings.update(settings)


def update_daily_pnl(pnl_change: float) -> None:
    """Update daily P&L tracker."""
    global _daily_pnl
    _reset_daily_if_needed()
    _daily_pnl += pnl_change


def get_risk_settings() -> Dict:
    return dict(_risk_settings)


class RiskEngine:
    """Portfolio risk & exposure engine."""

    def calculate_position(
        self,
        balance: float,
        risk_pct: float,
        entry_price: float,
        stop_loss_price: float,
        confidence_score: float,
        signal_type: str,
    ) -> Dict:
        """Full position calculation with leverage and liquidation price."""
        try:
            pos = calculate_position_size(balance, risk_pct, entry_price, stop_loss_price)
            if "error" in pos:
                return pos

            lev_info = suggest_leverage(confidence_score)
            leverage = lev_info["suggested_leverage"]
            liq_price = get_liquidation_price(entry_price, leverage, signal_type)

            return {
                **pos,
                **lev_info,
                "liquidation_price": liq_price,
                "entry_price": entry_price,
                "stop_loss_price": stop_loss_price,
            }
        except Exception as e:
            logger.error(f"RiskEngine.calculate_position error: {e}")
            return {"error": str(e)}

    def get_portfolio(self, active_signals: List[Dict]) -> Dict:
        """Get portfolio exposure summary."""
        balance = _risk_settings.get("balance", 1000.0)
        return get_portfolio_exposure(active_signals, balance)

    def check_correlation(self, signal_type: str, symbol: str, active_signals: List[Dict]) -> Dict:
        return check_correlation_risk(signal_type, symbol, active_signals)

    def update_settings(self, settings: Dict) -> None:
        update_risk_settings(settings)

    def get_settings(self) -> Dict:
        return get_risk_settings()


risk_engine = RiskEngine()

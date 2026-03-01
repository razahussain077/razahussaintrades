"""
Phase 3 API Routes — Market Maker Level Features
Liquidation Heatmap, Funding Rate, Entry Zones, Risk Engine,
ML Engine, Backtest, News/Events, Market Regime, Signal History
"""
import asyncio
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.engines.liquidation_engine import liquidation_engine
from app.engines.funding_engine import funding_engine
from app.engines.entry_engine import entry_engine
from app.engines.risk_engine import risk_engine, update_risk_settings
from app.engines.ml_engine import ml_engine
from app.engines.backtest_engine import backtest_engine
from app.engines.news_engine import news_engine
from app.engines.regime_engine import regime_engine
from app.exchanges.binance_client import binance_client
from app.exchanges.aggregator import aggregator
from app.database.models import get_signals, get_signal_stats, save_signal_history

logger = logging.getLogger(__name__)
phase3_router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# FEATURE 1: LIQUIDATION HEATMAP
# ─────────────────────────────────────────────────────────────────────────────

@phase3_router.get(
    "/liquidation-heatmap/{symbol}",
    summary="Get liquidation heatmap for symbol",
    tags=["Phase 3 - Liquidation"],
)
async def get_liquidation_heatmap(symbol: str):
    """
    Returns estimated liquidation price zones with density scores.
    Identifies liquidation magnets (highest concentration clusters).
    """
    symbol = symbol.upper()
    result = await liquidation_engine.get_heatmap(symbol)
    if "error" in result and "heatmap_zones" not in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result


# ─────────────────────────────────────────────────────────────────────────────
# FEATURE 2: FUNDING RATE
# ─────────────────────────────────────────────────────────────────────────────

@phase3_router.get(
    "/funding-rate/{symbol}",
    summary="Get funding rate data and signal interpretation",
    tags=["Phase 3 - Funding Rate"],
)
async def get_funding_rate(symbol: str):
    """
    Returns current funding rate, history, and signal modifier.
    Positive rate = longs paying shorts = SHORT confidence boost (market over-leveraged LONG).
    Negative rate = shorts paying longs = LONG confidence boost (market over-leveraged SHORT).
    """
    symbol = symbol.upper()
    result = await funding_engine.get_funding_data(symbol)
    return result


@phase3_router.get(
    "/funding-rate/{symbol}/modifier",
    summary="Get funding rate confidence modifier for a signal direction",
    tags=["Phase 3 - Funding Rate"],
)
async def get_funding_modifier(
    symbol: str,
    signal_type: str = Query("LONG", regex="^(LONG|SHORT)$"),
):
    """Get confidence boost from funding rate for a given signal direction."""
    symbol = symbol.upper()
    return funding_engine.get_signal_modifier(symbol, signal_type)


# ─────────────────────────────────────────────────────────────────────────────
# FEATURE 3: ENTRY ZONES
# ─────────────────────────────────────────────────────────────────────────────

class EntryZoneRequest(BaseModel):
    signal_type: str
    key_level_top: float
    key_level_bottom: float
    current_price: float
    stop_loss: float


@phase3_router.post(
    "/entry-zones",
    summary="Calculate smart entry zones for a signal",
    tags=["Phase 3 - Entry Zones"],
)
async def calculate_entry_zones(req: EntryZoneRequest):
    """
    Calculate 3 entry levels with position allocation percentages.
    Entry 1 (30%): First touch, Entry 2 (40%): Midpoint, Entry 3 (30%): Extreme.
    """
    from app.engines.entry_engine import calculate_entry_zones, calculate_weighted_average_entry, validate_entry_zone

    entries = calculate_entry_zones(
        req.signal_type, req.key_level_top, req.key_level_bottom, req.current_price
    )
    avg_entry = calculate_weighted_average_entry(entries)
    valid = validate_entry_zone(entries, req.stop_loss, req.signal_type)

    return {
        "entries": entries,
        "weighted_average_entry": avg_entry,
        "is_valid": valid,
        "invalidation_note": None if valid else "Entry 3 beyond stop loss — signal invalidated",
    }


# ─────────────────────────────────────────────────────────────────────────────
# FEATURE 4: RISK ENGINE
# ─────────────────────────────────────────────────────────────────────────────

@phase3_router.get(
    "/risk/position-size",
    summary="Calculate position size with leverage suggestion",
    tags=["Phase 3 - Risk"],
)
async def calculate_position_size(
    balance: float = Query(..., gt=0, description="Account balance in USD"),
    risk_pct: float = Query(1.0, ge=0.1, le=10.0, description="Risk percentage per trade"),
    entry_price: float = Query(..., gt=0),
    stop_loss_price: float = Query(..., gt=0),
    confidence_score: float = Query(70.0, ge=0, le=100),
    signal_type: str = Query("LONG", regex="^(LONG|SHORT)$"),
):
    """
    Calculate position size, suggested leverage, and liquidation price.
    Formula: position_size = (balance * risk_pct) / |entry - stop_loss|
    """
    result = risk_engine.calculate_position(
        balance, risk_pct, entry_price, stop_loss_price, confidence_score, signal_type
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@phase3_router.get(
    "/risk/portfolio",
    summary="Get portfolio exposure summary",
    tags=["Phase 3 - Risk"],
)
async def get_portfolio_exposure():
    """
    Returns current portfolio risk exposure:
    open signals count, LONG/SHORT ratio, correlation warnings, daily P&L.
    """
    try:
        active_signals = await get_signals(is_active=True, limit=100)
        return risk_engine.get_portfolio(active_signals)
    except Exception as e:
        logger.error(f"get_portfolio_exposure error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class RiskSettingsRequest(BaseModel):
    balance: Optional[float] = None
    risk_pct: Optional[float] = None
    max_trades: Optional[int] = None


@phase3_router.post(
    "/risk/settings",
    summary="Update risk settings",
    tags=["Phase 3 - Risk"],
)
async def update_risk_settings_endpoint(settings: RiskSettingsRequest):
    """Update risk settings: account balance, risk percentage, max concurrent trades."""
    update_data = {k: v for k, v in settings.model_dump().items() if v is not None}
    risk_engine.update_settings(update_data)
    return {"message": "Risk settings updated", "settings": risk_engine.get_settings()}


@phase3_router.get(
    "/risk/settings",
    summary="Get current risk settings",
    tags=["Phase 3 - Risk"],
)
async def get_risk_settings():
    """Get current risk engine settings."""
    return risk_engine.get_settings()


# ─────────────────────────────────────────────────────────────────────────────
# FEATURE 5: ML ENGINE
# ─────────────────────────────────────────────────────────────────────────────

@phase3_router.get(
    "/ml/stats",
    summary="Get ML model statistics",
    tags=["Phase 3 - ML"],
)
async def get_ml_stats():
    """
    Returns ML model accuracy, feature importance, training status.
    ML activates after 50 completed signals.
    """
    return ml_engine.get_stats()


class MLOutcomeRequest(BaseModel):
    signal_id: str
    outcome: str  # TP1, TP2, TP3, SL, EXPIRED


@phase3_router.post(
    "/ml/train",
    summary="Trigger manual ML model retraining",
    tags=["Phase 3 - ML"],
)
async def trigger_ml_retrain():
    """Trigger manual retraining of the ML model."""
    success = ml_engine.retrain()
    return {
        "success": success,
        "message": "Model retrained" if success else "Not enough data or error during training",
        "stats": ml_engine.get_stats(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# FEATURE 6: BACKTEST ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class BacktestRequest(BaseModel):
    symbol: str
    timeframe: str = "1h"
    days: int = 30


@phase3_router.post(
    "/backtest/run",
    summary="Run backtest for symbol",
    tags=["Phase 3 - Backtest"],
)
async def run_backtest(req: BacktestRequest):
    """
    Run backtest on historical data.
    Returns: win rate, profit factor, Sharpe ratio, equity curve, trade list.
    """
    try:
        symbol = req.symbol.upper()
        days = min(req.days, 90)
        result = await backtest_engine.run(symbol, req.timeframe, days)
        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"run_backtest error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@phase3_router.get(
    "/backtest/results",
    summary="Get latest backtest results",
    tags=["Phase 3 - Backtest"],
)
async def get_backtest_results():
    """Get the most recently run backtest results."""
    results = backtest_engine.get_results()
    if results is None:
        return {"message": "No backtest results yet. Run a backtest first.", "results": None}
    return results


@phase3_router.get(
    "/paper-trading/status",
    summary="Get paper trading P&L status",
    tags=["Phase 3 - Backtest"],
)
async def get_paper_trading_status():
    """Get current paper trading portfolio status."""
    return backtest_engine.get_paper_status()


# ─────────────────────────────────────────────────────────────────────────────
# FEATURE 7: NEWS/EVENTS ENGINE
# ─────────────────────────────────────────────────────────────────────────────

@phase3_router.get(
    "/events/upcoming",
    summary="Get upcoming economic events",
    tags=["Phase 3 - Events"],
)
async def get_upcoming_events(
    days_ahead: int = Query(7, ge=1, le=30, description="Days to look ahead"),
):
    """
    Returns upcoming economic events with impact levels and countdowns.
    HIGH impact events (FOMC, CPI) add warnings to signals.
    """
    events = news_engine.get_events(days_ahead)
    next_event = news_engine.get_next_event()
    active_warnings = news_engine.get_warnings()

    return {
        "events": events,
        "next_event": next_event,
        "active_warnings": active_warnings,
        "has_active_warnings": len(active_warnings) > 0,
    }


@phase3_router.get(
    "/events/warnings",
    summary="Get currently active event warnings",
    tags=["Phase 3 - Events"],
)
async def get_active_warnings():
    """Get active event warnings that should be shown on signals."""
    warnings = news_engine.get_warnings()
    signal_warning = news_engine.get_signal_warning()
    return {
        "warnings": warnings,
        "signal_warning": signal_warning,
        "has_warnings": len(warnings) > 0,
    }


# ─────────────────────────────────────────────────────────────────────────────
# FEATURE 8: MARKET REGIME
# ─────────────────────────────────────────────────────────────────────────────

@phase3_router.get(
    "/regime/{symbol}",
    summary="Get market regime for symbol",
    tags=["Phase 3 - Regime"],
)
async def get_market_regime(
    symbol: str,
    timeframe: str = Query("1h", description="Timeframe for analysis"),
):
    """
    Detect market regime: TRENDING, RANGING, VOLATILE, or SQUEEZE.
    Returns regime-adapted signal parameters.
    """
    symbol = symbol.upper()
    try:
        candles = await binance_client.get_klines(symbol, timeframe, 100)
        if len(candles) < 35:
            return {
                "symbol": symbol,
                "regime": "ranging",
                "label": "RANGING",
                "emoji": "↔️",
                "description": "Insufficient data",
                "history": [],
            }

        regime_data = regime_engine.detect(symbol, candles)
        history = regime_engine.get_history(symbol)
        adaptation_long = regime_engine.get_adaptation(regime_data["regime"], "LONG")
        adaptation_short = regime_engine.get_adaptation(regime_data["regime"], "SHORT")

        return {
            "symbol": symbol,
            **regime_data,
            "long_adaptation": adaptation_long,
            "short_adaptation": adaptation_short,
            "history": history,
        }
    except Exception as e:
        logger.error(f"get_market_regime error for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# FEATURE 9: SIGNAL HISTORY + P&L TRACKER
# ─────────────────────────────────────────────────────────────────────────────

@phase3_router.get(
    "/signals/history",
    summary="Get paginated signal history",
    tags=["Phase 3 - Signal History"],
)
async def get_signal_history(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    coin: Optional[str] = Query(None),
    signal_type: Optional[str] = Query(None, regex="^(LONG|SHORT)$"),
):
    """
    Get paginated signal history with P&L data.
    Includes closed signals with results.
    """
    try:
        signals = await get_signals(
            is_active=False,
            coin=coin.upper() if coin else None,
            signal_type=signal_type,
            limit=limit,
        )

        # Calculate simple P&L for each
        for sig in signals:
            entry = (sig.get("entry_low", 0) + sig.get("entry_high", 0)) / 2
            result = sig.get("result")
            if result == "WIN":
                sig["pnl_pct"] = sig.get("take_profit_1_pct", 1.5)
            elif result == "LOSS":
                sig["pnl_pct"] = -sig.get("stop_loss_pct", 1.0)
            elif result == "BE":
                sig["pnl_pct"] = 0.0
            else:
                sig["pnl_pct"] = None

        return {
            "signals": signals,
            "count": len(signals),
            "page": page,
        }
    except Exception as e:
        logger.error(f"get_signal_history error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@phase3_router.get(
    "/signals/stats",
    summary="Get aggregate signal performance statistics",
    tags=["Phase 3 - Signal History"],
)
async def get_signal_performance_stats():
    """
    Returns comprehensive performance statistics:
    win rate, total trades, best/worst trade, profit factor.
    """
    try:
        stats = await get_signal_stats()
        return stats
    except Exception as e:
        logger.error(f"get_signal_performance_stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@phase3_router.get(
    "/signals/active",
    summary="Get active signals with live P&L",
    tags=["Phase 3 - Signal History"],
)
async def get_active_signals_live():
    """
    Get all currently active signals with live P&L based on current price.
    """
    try:
        signals = await get_signals(is_active=True, limit=100)

        enriched = []
        for sig in signals:
            entry = (sig.get("entry_low", 0) + sig.get("entry_high", 0)) / 2
            symbol = sig.get("coin", "")
            try:
                current_price = await binance_client.get_price(symbol)
            except Exception:
                current_price = entry

            if entry > 0 and current_price > 0:
                if sig.get("signal_type") == "LONG":
                    unrealized_pnl_pct = (current_price - entry) / entry * 100
                else:
                    unrealized_pnl_pct = (entry - current_price) / entry * 100

                # Distance to TP1 and SL
                tp1 = sig.get("take_profit_1", 0)
                sl = sig.get("stop_loss", 0)
                if tp1 > 0 and sl > 0:
                    total_range = abs(tp1 - sl)
                    progress = abs(current_price - entry) / total_range if total_range > 0 else 0
                else:
                    progress = 0

                sig["current_price"] = current_price
                sig["unrealized_pnl_pct"] = round(unrealized_pnl_pct, 3)
                sig["progress_to_tp1"] = round(min(progress * 100, 100), 1)
            else:
                sig["current_price"] = current_price
                sig["unrealized_pnl_pct"] = 0.0
                sig["progress_to_tp1"] = 0.0

            enriched.append(sig)

        return {"signals": enriched, "count": len(enriched)}
    except Exception as e:
        logger.error(f"get_active_signals_live error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

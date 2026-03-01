import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from app.config import settings
from app.exchanges.aggregator import aggregator
from app.exchanges.binance_client import binance_client
from app.exchanges.coingecko_client import coingecko_client
from app.analysis.ict_engine import get_kill_zones
from app.analysis.correlation_engine import calculate_btc_correlation, build_correlation_matrix, get_market_cap_category
from app.analysis.smc_engine import smc_engine
from app.analysis.ict_engine import ict_engine
from app.analysis.liquidity_engine import liquidity_engine
from app.analysis.wyckoff_engine import wyckoff_engine
from app.analysis.whale_tracker import whale_tracker
from app.analysis.volatility_engine import volatility_engine, calculate_atr_percentage
from app.signals.signal_generator import signal_generator
from app.signals.models import (
    Signal, SignalFilter, PortfolioSettings, RiskCalculationRequest, RiskCalculationResponse
)
from app.risk.position_sizer import calculate_position_value
from app.risk.leverage_calculator import calculate_safe_leverage, dynamic_leverage
from app.risk.anti_liquidation import get_liquidation_price, check_liquidation_safety, validate_trade
from app.database.models import (
    save_signal, get_signals, get_signal_by_id,
    mark_signal_taken, save_portfolio_settings, get_portfolio_settings,
    save_signal_history, get_signal_stats, deactivate_signal
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# COINS
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/coins", summary="List all top coins with prices and signal counts")
async def list_coins():
    """Return all top 50 coins with aggregated price data."""
    try:
        coins_data = await aggregator.get_all_top_coins_data()
        # Add signal status and confidence from DB
        active_signals = await get_signals(is_active=True, limit=200)
        signal_map: Dict[str, Dict] = {}
        for sig in active_signals:
            symbol = sig.get("coin", "")
            if symbol not in signal_map or sig.get("confidence_score", 0) > signal_map[symbol].get("confidence_score", 0):
                signal_map[symbol] = sig

        for coin in coins_data:
            sym = coin["symbol"]
            best_sig = signal_map.get(sym)
            if best_sig:
                coin["signal_status"] = best_sig.get("signal_type", "WAIT")
                coin["confidence_score"] = round(best_sig.get("confidence_score", 0), 1)
                coin["active_signals"] = sum(1 for s in active_signals if s.get("coin") == sym)
            else:
                coin["signal_status"] = "WAIT"
                coin["confidence_score"] = 0
                coin["active_signals"] = 0

        return {"coins": coins_data, "count": len(coins_data)}
    except Exception as e:
        logger.error(f"list_coins error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/coins/{symbol}", summary="Get detailed coin data")
async def get_coin(symbol: str):
    """Return detailed data for a specific coin including funding rate and OI."""
    symbol = symbol.upper()
    try:
        agg = await aggregator.get_aggregated_price(symbol)
        ticker = await binance_client.get_ticker_24h(symbol)
        funding = await binance_client.get_funding_rate(symbol)
        oi = await binance_client.get_open_interest(symbol)

        coin_signals = await get_signals(coin=symbol, is_active=True, limit=10)

        return {
            "symbol": symbol,
            "binance_price": agg.binance_price,
            "bybit_price": agg.bybit_price,
            "okx_price": agg.okx_price,
            "average_price": agg.average_price,
            "volume_24h": agg.volume_24h,
            "price_change_pct_24h": agg.price_change_pct_24h,
            "high_24h": agg.high_24h,
            "low_24h": agg.low_24h,
            "funding_rate": funding.get("funding_rate", 0),
            "open_interest": oi.get("open_interest", 0),
            "active_signals": coin_signals,
        }
    except Exception as e:
        logger.error(f"get_coin error for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# SIGNALS
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/signals", summary="Get active trading signals")
async def list_signals(
    signal_type: Optional[str] = Query(None, description="LONG or SHORT"),
    coin: Optional[str] = Query(None),
    min_confidence: float = Query(60.0, ge=0, le=100),
    limit: int = Query(50, ge=1, le=200),
    is_active: bool = Query(True),
):
    """Return active trading signals with optional filters."""
    try:
        signals = await get_signals(
            is_active=is_active,
            coin=coin.upper() if coin else None,
            signal_type=signal_type.upper() if signal_type else None,
            limit=limit,
        )
        filtered = [s for s in signals if s.get("confidence_score", 0) >= min_confidence]
        return {"signals": filtered, "count": len(filtered)}
    except Exception as e:
        logger.error(f"list_signals error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/signals/scan/{symbol}", summary="Generate a fresh signal for a specific coin")
async def scan_symbol(symbol: str):
    """Run analysis and generate a signal for a specific symbol."""
    symbol = symbol.upper()
    try:
        signal = await signal_generator.generate(symbol)
        if signal is None:
            return {"message": f"No qualifying signal for {symbol}", "signal": None}

        signal_dict = signal.model_dump()
        signal_dict["created_at"] = signal_dict["created_at"].isoformat()
        await save_signal(signal_dict)

        return {"signal": signal_dict}
    except Exception as e:
        logger.error(f"scan_symbol error for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/signals/{signal_id}", summary="Get a specific signal by ID")
async def get_signal(signal_id: str):
    """Return details of a specific signal."""
    signal = await get_signal_by_id(signal_id)
    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")
    return signal


@router.post("/signals/{signal_id}/take", summary="Mark a signal as taken")
async def take_signal(signal_id: str):
    """Mark a signal as taken by the user."""
    success = await mark_signal_taken(signal_id)
    if not success:
        raise HTTPException(status_code=404, detail="Signal not found or error updating")
    return {"message": "Signal marked as taken", "signal_id": signal_id}


@router.post("/signals/{signal_id}/close", summary="Close a signal with result")
async def close_signal(signal_id: str, result: str = Query(..., regex="^(WIN|LOSS|BE)$"), pnl: float = Query(0.0)):
    """Close a signal and record the result."""
    success = await save_signal_history({
        "signal_id": signal_id,
        "result": result,
        "pnl": pnl,
    })
    if not success:
        raise HTTPException(status_code=500, detail="Failed to close signal")
    return {"message": f"Signal closed: {result}", "pnl": pnl}


@router.get("/signals/stats/summary", summary="Get signal performance statistics")
async def signal_stats():
    """Return win/loss statistics for all closed signals."""
    stats = await get_signal_stats()
    return stats


# ─────────────────────────────────────────────────────────────────────────────
# MARKET
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/market/overview", summary="Global market overview")
async def market_overview():
    """Return total market cap, BTC dominance, fear/greed index."""
    try:
        overview = await aggregator.get_market_overview()
        return overview
    except Exception as e:
        logger.error(f"market_overview error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/market/kill-zones", summary="Current ICT kill zone info")
async def kill_zones_info():
    """Return current and upcoming ICT kill zones with PKT times."""
    return format_kill_zones()


# ─────────────────────────────────────────────────────────────────────────────
# KILL ZONES (alias for frontend compatibility)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/killzones", summary="Current ICT kill zone info (alias)")
async def kill_zones_alias():
    """Return current and upcoming ICT kill zones with PKT times."""
    return format_kill_zones()


def format_kill_zones() -> Dict:
    """Return kill zone data in the format expected by the frontend."""
    from datetime import datetime, timezone
    import pytz

    raw = get_kill_zones()
    PKT = pytz.timezone(settings.PKT_TIMEZONE)
    now_pkt = datetime.now(timezone.utc).astimezone(PKT)

    kill_zone_sessions = [
        {"name": "Asian", "utc_start": 0, "utc_end": 9, "pkt_start": 5, "pkt_end": 14},
        {"name": "London", "utc_start": 8, "utc_end": 12, "pkt_start": 13, "pkt_end": 17},
        {"name": "New York", "utc_start": 13, "utc_end": 18, "pkt_start": 18, "pkt_end": 23},
        {"name": "London Close", "utc_start": 17, "utc_end": 19, "pkt_start": 22, "pkt_end": 24},
    ]

    hour_utc = datetime.now(timezone.utc).hour
    active_name = raw.get("active_session", "Off Hours")

    zones = []
    for s in kill_zone_sessions:
        is_active = s["utc_start"] <= hour_utc < s["utc_end"]
        end_hour = s["pkt_end"] % 24
        # Minutes until next start (approximate)
        minutes_until = None
        if not is_active:
            diff_h = (s["utc_start"] - hour_utc) % 24
            minutes_until = diff_h * 60

        zones.append({
            "name": s["name"],
            "is_active": is_active,
            "start_pkt": f"{s['pkt_start']:02d}:00",
            "end_pkt": f"{end_hour:02d}:00",
            "minutes_until_next": minutes_until,
        })

    return {
        "current_time_pkt": now_pkt.strftime("%H:%M"),
        "active_session": active_name if active_name != "Off Hours" else None,
        "zones": zones,
        # legacy fields
        "current_pkt_time": raw.get("current_pkt_time"),
        "is_kill_zone": raw.get("is_kill_zone", False),
    }


# ─────────────────────────────────────────────────────────────────────────────
# RISK
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/risk/calculate", summary="Calculate leverage, position size, and liquidation price")
async def risk_calculate(
    portfolio: float = Query(..., gt=0, description="Portfolio size in USD"),
    risk_pct: float = Query(1.0, ge=0.1, le=10.0, description="Risk percentage"),
    entry_price: float = Query(..., gt=0),
    stop_loss: float = Query(..., gt=0),
    nearest_liquidity: Optional[float] = Query(None),
    side: str = Query("LONG", regex="^(LONG|SHORT)$"),
):
    """Calculate position size, leverage, and liquidation price."""
    try:
        pos = calculate_position_value(portfolio, risk_pct, entry_price, stop_loss)
        leverage = calculate_safe_leverage(entry_price, nearest_liquidity or stop_loss)
        liq_price = get_liquidation_price(entry_price, leverage, side)
        liq_check = check_liquidation_safety(
            entry_price, stop_loss, leverage, nearest_liquidity or stop_loss, side
        )

        margin_required = (pos["position_size"] * entry_price) / leverage if leverage > 0 else 0

        return {
            "position_size": pos["position_size"],
            "position_value": pos["position_value"],
            "risk_amount": pos["risk_amount"],
            "recommended_leverage": leverage,
            "liquidation_price": liq_price,
            "max_loss": pos["risk_amount"],
            "margin_required": round(margin_required, 4),
            "liquidation_safety": liq_check,
        }
    except Exception as e:
        logger.error(f"risk_calculate error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# PORTFOLIO
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/portfolio/settings", summary="Save portfolio settings")
async def save_settings(settings_data: PortfolioSettings):
    """Save user portfolio configuration."""
    try:
        success = await save_portfolio_settings(settings_data.model_dump())
        if not success:
            raise HTTPException(status_code=500, detail="Failed to save settings")
        return {"message": "Settings saved", "settings": settings_data.model_dump()}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/portfolio/settings", summary="Get portfolio settings")
async def load_settings():
    """Return current portfolio settings."""
    settings_data = await get_portfolio_settings()
    if not settings_data:
        # Return defaults
        return {
            "budget": 1000.0,
            "risk_tolerance": 1.0,
            "preferred_timeframes": ["1h", "4h"],
            "max_positions": 5,
            "max_leverage": 10.0,
        }
    return settings_data


# ─────────────────────────────────────────────────────────────────────────────
# CORRELATION
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/correlation", summary="BTC correlation data for top coins")
async def get_correlation(
    symbols: Optional[str] = Query(None, description="Comma-separated symbols, default BTC+top 10"),
    periods: int = Query(30, ge=10, le=100),
):
    """Return BTC correlation for specified coins."""
    try:
        if symbols:
            symbol_list = [s.strip().upper() for s in symbols.split(",")][:10]
        else:
            symbol_list = settings.TOP_50_COINS[:10]

        btc_candles = await aggregator.get_best_candles("BTCUSDT", "1h", periods + 5)
        results = []
        for sym in symbol_list:
            if sym == "BTCUSDT":
                results.append({"symbol": sym, "correlation": 1.0, "interpretation": "Reference"})
                continue
            candles = await aggregator.get_best_candles(sym, "1h", periods + 5)
            corr = calculate_btc_correlation(btc_candles, candles, periods)
            results.append({"symbol": sym, **corr})

        return {"correlations": results, "periods": periods, "base": "BTCUSDT"}
    except Exception as e:
        logger.error(f"get_correlation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# LIQUIDATION HEATMAP
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/liquidation-heatmap", summary="Estimated liquidation price zones")
async def liquidation_heatmap(
    symbol: str = Query("BTCUSDT"),
    leverage_levels: str = Query("2,5,10,20", description="Comma-separated leverage values"),
):
    """
    Return estimated liquidation prices at different leverage levels
    as a heatmap proxy based on current price.
    """
    try:
        symbol = symbol.upper()
        price = await binance_client.get_price(symbol)
        if price == 0:
            raise HTTPException(status_code=404, detail=f"Price not available for {symbol}")

        leverages = [float(l) for l in leverage_levels.split(",")]
        heatmap = []
        for lev in leverages:
            long_liq = get_liquidation_price(price, lev, "LONG")
            short_liq = get_liquidation_price(price, lev, "SHORT")
            heatmap.append({
                "leverage": lev,
                "long_liquidation": long_liq,
                "short_liquidation": short_liq,
                "long_liq_distance_pct": round(abs(price - long_liq) / price * 100, 2),
                "short_liq_distance_pct": round(abs(short_liq - price) / price * 100, 2),
            })

        return {
            "symbol": symbol,
            "current_price": price,
            "heatmap": heatmap,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"liquidation_heatmap error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# CANDLES
# ─────────────────────────────────────────────────────────────────────────────

# Map frontend timeframe labels to Binance interval strings
BINANCE_INTERVAL_MAP: Dict[str, str] = {
    "1m": "1m", "3m": "3m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1h", "1H": "1h", "2h": "2h", "4h": "4h", "4H": "4h",
    "6h": "6h", "8h": "8h", "12h": "12h",
    "1d": "1d", "1D": "1d", "3d": "3d",
    "1w": "1w", "1W": "1w", "1M": "1M",
}


@router.get("/candles/{symbol}", summary="Get OHLCV candle data for a symbol")
async def get_candles(
    symbol: str,
    timeframe: str = Query("1H", description="Timeframe: 1m, 5m, 15m, 30m, 1H, 4H, 1D, 1W"),
    limit: int = Query(200, ge=10, le=1000),
):
    """Return candle data formatted for TradingView lightweight-charts."""
    symbol = symbol.upper()
    interval = BINANCE_INTERVAL_MAP.get(timeframe, "1h")
    try:
        candles = await aggregator.get_best_candles(symbol, interval, limit)
        if not candles:
            raise HTTPException(status_code=404, detail=f"No candle data for {symbol}")
        # Convert to TradingView format (time in seconds)
        result = [
            {
                "time": int(c["timestamp"]) // 1000,
                "open": c["open"],
                "high": c["high"],
                "low": c["low"],
                "close": c["close"],
                "volume": c.get("volume", 0),
            }
            for c in candles
        ]
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"get_candles error for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/analysis/{symbol}", summary="Run full SMC/ICT analysis on a symbol")
async def analyze_symbol(
    symbol: str,
    timeframe: str = Query("1H"),
    limit: int = Query(100, ge=20, le=500),
):
    """Run all analysis engines for a symbol and return results."""
    symbol = symbol.upper()
    interval = BINANCE_INTERVAL_MAP.get(timeframe, "1h")
    try:
        candles = await aggregator.get_best_candles(symbol, interval, limit)
        if len(candles) < 20:
            raise HTTPException(status_code=404, detail=f"Insufficient data for {symbol}")

        order_book = await binance_client.get_order_book(symbol, 20)

        smc_result = smc_engine.analyze(candles)
        ict_result = ict_engine.analyze(candles)
        liq_result = liquidity_engine.analyze(candles)
        wyckoff_result = wyckoff_engine.analyze(candles)
        whale_result = whale_tracker.analyze(candles, order_book)
        vol_result = volatility_engine.analyze(candles)

        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "candle_count": len(candles),
            "smc": smc_result,
            "ict": ict_result,
            "liquidity": liq_result,
            "wyckoff": wyckoff_result,
            "whale": whale_result,
            "volatility": vol_result,
            "kill_zones": get_kill_zones(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"analyze_symbol error for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

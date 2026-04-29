import asyncio
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database.db import init_db
from app.websocket_manager import manager
from app.api.routes import router
from app.api.websocket_routes import ws_router
from app.api.phase3_routes import phase3_router
from app.api.orderflow_routes import orderflow_router
from app.api.notifications_routes import notifications_router
from app.api.execution_routes import execution_router
from app.exchanges.binance_client import binance_client
from app.signals.signal_generator import signal_generator
from app.database.models import save_signal
from app.streams import stream_supervisor
from app.services.calendar_provider import refresh_calendar_loop

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Crypto Trading Signal Bot API",
    description="Smart Money Concepts + ICT methodology trading signal bot with real-time WebSocket support",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — `*` is acceptable in development but unsafe in production. Honor the
# `ALLOWED_ORIGINS` setting (comma-separated list) in production. Note: when
# `allow_origins=["*"]` is used, the spec requires `allow_credentials=False`.
_origins_raw = (settings.ALLOWED_ORIGINS or "*").strip()
if _origins_raw == "*" or settings.ENVIRONMENT == "development":
    _allow_origins: list[str] = ["*"]
    _allow_credentials = False
else:
    _allow_origins = [o.strip() for o in _origins_raw.split(",") if o.strip()]
    _allow_credentials = True

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(router, prefix="/api", tags=["API"])
app.include_router(ws_router, tags=["WebSocket"])
app.include_router(phase3_router, prefix="/api", tags=["Phase 3"])
app.include_router(orderflow_router, prefix="/api", tags=["Order Flow"])
app.include_router(notifications_router, tags=["Notifications"])
app.include_router(execution_router, tags=["Execution"])


@app.on_event("startup")
async def startup_event():
    """Initialize DB, start background tasks on app startup."""
    logger.info("Starting Crypto Trading Signal Bot API v2.0 (Phase 3)...")

    # Initialize database
    try:
        await init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.error(f"DB init failed: {e}")

    # Start WebSocket broadcast background tasks
    try:
        await manager.start_background_tasks()
        logger.info("WebSocket broadcast tasks started")
    except Exception as e:
        logger.error(f"WS manager start failed: {e}")

    # Start real-time order-flow streams (liquidations + aggTrade for CVD).
    # These run as background asyncio tasks managed by `stream_supervisor`.
    try:
        # Subscribe aggTrade to a manageable subset — top 30 symbols by default.
        # This stays well under Binance's combined-stream limits and avoids
        # hammering CPU on slower hosts.
        aggtrade_symbols = settings.TOP_50_COINS[:30]
        await stream_supervisor.start(aggtrade_symbols)
    except Exception as e:
        logger.error(f"stream supervisor start failed: {e}")

    # Start background loops
    asyncio.create_task(_price_refresh_loop())
    asyncio.create_task(_signal_scan_loop())
    asyncio.create_task(_signal_monitor_loop())
    asyncio.create_task(_ml_retrain_loop())
    asyncio.create_task(_funding_rate_refresh_loop())
    # Real economic calendar — refreshes every 6h from ForexFactory mirror.
    # Until the first fetch lands the news engine emits synthesized fallback
    # events tagged `is_indicative=True`.
    asyncio.create_task(refresh_calendar_loop())
    logger.info("API startup complete — all background tasks started")


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on shutdown."""
    logger.info("Shutting down...")
    try:
        await stream_supervisor.stop()
    except Exception as e:
        logger.warning(f"stream supervisor shutdown error: {e}")
    await manager.stop()
    await binance_client.close()
    try:
        from app.notifications import telegram_client
        await telegram_client.aclose()
    except Exception as e:
        logger.warning(f"telegram shutdown error: {e}")


async def _price_refresh_loop():
    """Periodically fetch latest prices and update WebSocket broadcast cache."""
    while True:
        try:
            prices = await binance_client.get_all_prices()
            top_prices = {
                symbol: price
                for symbol, price in prices.items()
                if symbol in settings.TOP_50_COINS
            }
            for symbol, price in top_prices.items():
                manager.update_price(symbol, price)
        except Exception as e:
            logger.warning(f"Price refresh loop error: {e}")
        await asyncio.sleep(settings.PRICE_CACHE_TTL)


async def _signal_scan_loop():
    """Scan all coins for signals every 5 minutes."""
    from app.notifications import is_kill_switch_active, telegram_client
    await asyncio.sleep(30)  # Initial delay
    while True:
        try:
            if is_kill_switch_active():
                logger.warning("Signal scan loop: kill switch active — skipping cycle")
            else:
                logger.info("Signal scan loop: scanning all coins...")
                signals = await signal_generator.scan_all()
                # Hoist equity / position / PnL fetches OUT of the per-signal
                # loop. The previous version called get_account_equity_usd()
                # for every signal, which (a) blocks the asyncio event loop
                # on each sync ccxt round-trip and (b) burns rate limit. Read
                # them once per cycle and pass cached values down.
                _exec_equity: float = 0.0
                _exec_open_count: int = 0
                _exec_today_pnl: float = 0.0
                if settings.AUTO_EXECUTION_ENABLED and signals:
                    try:
                        from app.execution.ccxt_executor import (
                            get_account_equity_usd,
                        )
                        from app.execution.state import (
                            count_open_executed_positions,
                            today_realised_pnl_usd,
                        )
                        # ccxt fetch_balance is synchronous; run it off-thread
                        # so it can't stall the event loop.
                        _exec_equity = await asyncio.to_thread(
                            get_account_equity_usd,
                        )
                        _exec_open_count = await count_open_executed_positions()
                        _exec_today_pnl = await today_realised_pnl_usd()
                    except Exception as e:
                        logger.warning("auto-exec preflight failed: %s", e)
                for sig in signals:
                    sig_dict = sig.model_dump()
                    sig_dict["created_at"] = sig_dict["created_at"].isoformat()
                    await save_signal(sig_dict)
                    await manager.push_signal(sig_dict)
                    # Best-effort Telegram push. The client is a no-op when
                    # not configured / disabled, and gracefully handles HTTP
                    # failures, so we never raise into the scan loop.
                    try:
                        await telegram_client.send_signal(sig_dict)
                    except Exception as e:
                        logger.warning("telegram push failed: %s", e)
                    # Optional auto-execution. Off unless AUTO_EXECUTION_ENABLED
                    # and the user has armed via TOTP. The executor itself
                    # handles every gate (kill switch, caps, idempotency,
                    # dry-run); we just hand it the signal and forget.
                    if settings.AUTO_EXECUTION_ENABLED:
                        try:
                            from app.execution.ccxt_executor import ccxt_executor
                            # `place_for_signal` may make synchronous ccxt
                            # calls in the live (non-dry-run) path, so it too
                            # is wrapped in to_thread to avoid blocking the
                            # event loop while N other signals are being
                            # broadcast and saved.
                            result = await asyncio.to_thread(
                                ccxt_executor.place_for_signal,
                                sig_dict,
                                _exec_equity,
                                _exec_open_count,
                                _exec_today_pnl,
                            )
                            if result.get("ok"):
                                logger.info(
                                    "auto-exec placed %s for signal %s "
                                    "(dry_run=%s)",
                                    result.get("order_id"), sig_dict.get("id"),
                                    result.get("dry_run"),
                                )
                            else:
                                logger.info(
                                    "auto-exec skipped signal %s: %s",
                                    sig_dict.get("id"), result.get("reason"),
                                )
                        except Exception as e:
                            logger.warning("auto-exec failed: %s", e)
                logger.info(f"Signal scan complete: {len(signals)} signals generated")
        except Exception as e:
            logger.warning(f"Signal scan loop error: {e}")
        await asyncio.sleep(300)  # 5 minutes


async def _signal_monitor_loop():
    """Monitor active signal prices every 1 minute to detect TP/SL hits."""
    from app.database.models import get_signals, save_signal_history

    await asyncio.sleep(60)  # Initial delay
    while True:
        try:
            active_signals = await get_signals(is_active=True, limit=100)
            for sig in active_signals:
                symbol = sig.get("coin", "")
                if not symbol:
                    continue
                try:
                    current_price = await binance_client.get_price(symbol)
                    if current_price <= 0:
                        continue

                    signal_type = sig.get("signal_type", "LONG")
                    entry = (sig.get("entry_low", 0) + sig.get("entry_high", 0)) / 2
                    sl = sig.get("stop_loss", 0)
                    tp1 = sig.get("take_profit_1", 0)

                    hit_result = None
                    if signal_type == "LONG":
                        if current_price <= sl:
                            hit_result = "LOSS"
                        elif current_price >= tp1:
                            hit_result = "WIN"
                    else:
                        if current_price >= sl:
                            hit_result = "LOSS"
                        elif current_price <= tp1:
                            hit_result = "WIN"

                    if hit_result:
                        pnl = tp1 - entry if hit_result == "WIN" else sl - entry
                        await save_signal_history({
                            "signal_id": sig["id"],
                            "result": hit_result,
                            "pnl": round(pnl, 8),
                        })
                        logger.info(f"Signal {sig['id']} ({symbol}) auto-closed: {hit_result}")
                except Exception as e:
                    logger.debug(f"Signal monitor error for {symbol}: {e}")
        except Exception as e:
            logger.warning(f"Signal monitor loop error: {e}")
        await asyncio.sleep(60)  # 1 minute


async def _ml_retrain_loop():
    """Retrain ML model every 24 hours."""
    from app.engines.ml_engine import ml_engine

    await asyncio.sleep(3600)  # Wait 1 hour before first retrain attempt
    while True:
        try:
            logger.info("ML retrain loop: attempting model retrain...")
            ml_engine.retrain()
        except Exception as e:
            logger.warning(f"ML retrain loop error: {e}")
        await asyncio.sleep(86400)  # 24 hours


async def _funding_rate_refresh_loop():
    """Refresh funding rates for top coins every 1 hour."""
    from app.engines.funding_engine import funding_engine

    await asyncio.sleep(120)  # Initial delay
    while True:
        try:
            for symbol in settings.TOP_50_COINS[:20]:  # Top 20 most active
                try:
                    await funding_engine.get_funding_data(symbol)
                    await asyncio.sleep(0.2)  # Small delay between requests
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"Funding rate refresh error: {e}")
        await asyncio.sleep(3600)  # 1 hour


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "crypto-signal-bot",
        "version": "2.0.0",
        "environment": settings.ENVIRONMENT,
        "phase": "3",
    }


@app.get("/", tags=["Root"])
async def root():
    return {
        "message": "Crypto Trading Signal Bot API v2.0 — Phase 3 Market Maker Edition",
        "docs": "/docs",
        "health": "/health",
    }

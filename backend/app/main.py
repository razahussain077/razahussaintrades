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
from app.exchanges.binance_client import binance_client

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

# CORS - allow all for dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(router, prefix="/api", tags=["API"])
app.include_router(ws_router, tags=["WebSocket"])
app.include_router(phase3_router, prefix="/api", tags=["Phase 3"])


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

    # Start background loops
    asyncio.create_task(_price_refresh_loop())
    asyncio.create_task(_signal_scan_loop())
    asyncio.create_task(_signal_monitor_loop())
    asyncio.create_task(_ml_retrain_loop())
    asyncio.create_task(_funding_rate_refresh_loop())
    logger.info("API startup complete — all background tasks started")


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on shutdown."""
    logger.info("Shutting down...")
    await manager.stop()
    await binance_client.close()


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
    from app.signals.signal_generator import signal_generator
    from app.database.models import save_signal

    await asyncio.sleep(30)  # Initial delay
    while True:
        try:
            logger.info("Signal scan loop: scanning all coins...")
            signals = await signal_generator.scan_all()
            for signal in signals:
                signal_dict = signal.model_dump()
                signal_dict["created_at"] = signal_dict["created_at"].isoformat()
                await save_signal(signal_dict)
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

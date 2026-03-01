import asyncio
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database.db import init_db
from app.websocket_manager import manager
from app.api.routes import router
from app.api.websocket_routes import ws_router
from app.exchanges.binance_client import binance_client
from app.signals.signal_generator import signal_generator
from app.database.models import save_signal

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Crypto Trading Signal Bot API",
    description="Smart Money Concepts + ICT methodology trading signal bot with real-time WebSocket support",
    version="1.0.0",
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


@app.on_event("startup")
async def startup_event():
    """Initialize DB, start background tasks on app startup."""
    logger.info("Starting Crypto Trading Signal Bot API...")

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

    # Start price refresh background loop
    asyncio.create_task(_price_refresh_loop())
    # Start signal scan background loop
    asyncio.create_task(_signal_scan_loop())
    logger.info("API startup complete")


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


_SIGNAL_SCAN_INTERVAL_SECONDS = 300  # scan all coins every 5 minutes


async def _signal_scan_loop():
    """Background loop: scan all top coins for signals every 5 minutes."""
    # Initial delay to let the app fully start
    await asyncio.sleep(30)
    while True:
        try:
            logger.info("Starting background signal scan for all coins...")
            signals = await signal_generator.scan_all()
            for sig in signals:
                sig_dict = sig.model_dump()
                sig_dict["created_at"] = sig_dict["created_at"].isoformat()
                await save_signal(sig_dict)
                await manager.push_signal(sig_dict)
            logger.info(f"Signal scan complete: {len(signals)} signals generated")
        except Exception as e:
            logger.error(f"Signal scan loop error: {e}")
        await asyncio.sleep(_SIGNAL_SCAN_INTERVAL_SECONDS)


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "crypto-signal-bot",
        "version": "1.0.0",
        "environment": settings.ENVIRONMENT,
    }


@app.get("/", tags=["Root"])
async def root():
    return {
        "message": "Crypto Trading Signal Bot API",
        "docs": "/docs",
        "health": "/health",
    }

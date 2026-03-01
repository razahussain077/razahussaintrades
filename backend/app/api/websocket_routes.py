import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.websocket_manager import manager
from app.exchanges.aggregator import aggregator
from app.exchanges.binance_client import binance_client
from app.config import settings
from app.analysis.ict_engine import get_kill_zones

logger = logging.getLogger(__name__)
ws_router = APIRouter()


@ws_router.websocket("/ws/prices")
async def websocket_prices(websocket: WebSocket):
    """
    WebSocket endpoint for live price updates.
    Broadcasts price changes every second to connected clients.
    """
    await manager.connect(websocket, "prices")
    try:
        # Send initial prices immediately on connect
        prices = await binance_client.get_all_prices()
        if prices:
            # Filter to top 50 coins only
            filtered = {k: v for k, v in prices.items() if k in settings.TOP_50_COINS}
            await manager.send_personal(websocket, {
                "type": "initial_prices",
                "data": filtered,
            })
            # Update cache
            for symbol, price in filtered.items():
                manager.update_price(symbol, price)

        # Keep connection alive, receiving any client messages
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                # Handle client commands (e.g., subscribe to specific symbols)
                try:
                    msg = json.loads(data)
                    if msg.get("action") == "ping":
                        await manager.send_personal(websocket, {"type": "pong"})
                    elif msg.get("action") == "get_price":
                        symbol = msg.get("symbol", "").upper()
                        if symbol:
                            price = await binance_client.get_price(symbol)
                            await manager.send_personal(websocket, {
                                "type": "price",
                                "symbol": symbol,
                                "price": price,
                            })
                except json.JSONDecodeError:
                    pass
            except asyncio.TimeoutError:
                # Send heartbeat
                try:
                    await manager.send_personal(websocket, {"type": "heartbeat"})
                except Exception:
                    break
    except WebSocketDisconnect:
        manager.disconnect(websocket, "prices")
    except Exception as e:
        logger.error(f"WebSocket prices error: {e}")
        manager.disconnect(websocket, "prices")


@ws_router.websocket("/ws/signals")
async def websocket_signals(websocket: WebSocket):
    """
    WebSocket endpoint for live signal updates.
    Broadcasts new and updated signals to connected clients.
    """
    await manager.connect(websocket, "signals")
    try:
        from app.database.models import get_signals
        recent_signals = await get_signals(is_active=True, limit=20)
        await manager.send_personal(websocket, {
            "type": "initial_signals",
            "data": recent_signals,
            "count": len(recent_signals),
        })

        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=60.0)
                try:
                    msg = json.loads(data)
                    if msg.get("action") == "ping":
                        await manager.send_personal(websocket, {"type": "pong"})
                    elif msg.get("action") == "get_signals":
                        signals = await get_signals(is_active=True, limit=50)
                        await manager.send_personal(websocket, {
                            "type": "signals_update",
                            "data": signals,
                        })
                except json.JSONDecodeError:
                    pass
            except asyncio.TimeoutError:
                try:
                    await manager.send_personal(websocket, {"type": "heartbeat"})
                except Exception:
                    break
    except WebSocketDisconnect:
        manager.disconnect(websocket, "signals")
    except Exception as e:
        logger.error(f"WebSocket signals error: {e}")
        manager.disconnect(websocket, "signals")


@ws_router.websocket("/ws/market")
async def websocket_market(websocket: WebSocket):
    """
    WebSocket endpoint for market overview updates.
    Broadcasts market data every 60 seconds.
    """
    await manager.connect(websocket, "market")
    try:
        # Initial market data
        overview = await aggregator.get_market_overview()
        kill_zones = get_kill_zones()
        await manager.send_personal(websocket, {
            "type": "market_overview",
            "data": {**overview, "kill_zones": kill_zones},
        })

        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=60.0)
                try:
                    msg = json.loads(data)
                    if msg.get("action") == "ping":
                        await manager.send_personal(websocket, {"type": "pong"})
                    elif msg.get("action") == "refresh":
                        overview = await aggregator.get_market_overview()
                        kill_zones = get_kill_zones()
                        await manager.send_personal(websocket, {
                            "type": "market_overview",
                            "data": {**overview, "kill_zones": kill_zones},
                        })
                except json.JSONDecodeError:
                    pass
            except asyncio.TimeoutError:
                # Send market update every minute
                try:
                    overview = await aggregator.get_market_overview()
                    await manager.send_personal(websocket, {
                        "type": "market_overview",
                        "data": {**overview, "kill_zones": get_kill_zones()},
                    })
                except Exception:
                    break
    except WebSocketDisconnect:
        manager.disconnect(websocket, "market")
    except Exception as e:
        logger.error(f"WebSocket market error: {e}")
        manager.disconnect(websocket, "market")

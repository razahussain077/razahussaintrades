import asyncio
import json
import logging
from typing import Dict, Set, Any
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {
            "prices": set(),
            "signals": set(),
            "market": set(),
        }
        self._price_cache: Dict[str, float] = {}
        self._signal_queue: asyncio.Queue = asyncio.Queue()
        self._running = False

    async def connect(self, websocket: WebSocket, channel: str) -> None:
        await websocket.accept()
        if channel not in self.active_connections:
            self.active_connections[channel] = set()
        self.active_connections[channel].add(websocket)
        logger.info(f"Client connected to channel '{channel}'. Total: {len(self.active_connections[channel])}")

    def disconnect(self, websocket: WebSocket, channel: str) -> None:
        self.active_connections.get(channel, set()).discard(websocket)
        logger.info(f"Client disconnected from channel '{channel}'.")

    async def broadcast(self, channel: str, data: Any) -> None:
        if channel not in self.active_connections:
            return
        dead: Set[WebSocket] = set()
        message = json.dumps(data) if not isinstance(data, str) else data
        for ws in list(self.active_connections[channel]):
            try:
                await ws.send_text(message)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self.active_connections[channel].discard(ws)

    async def send_personal(self, websocket: WebSocket, data: Any) -> None:
        message = json.dumps(data) if not isinstance(data, str) else data
        try:
            await websocket.send_text(message)
        except Exception as e:
            logger.warning(f"Failed to send personal message: {e}")

    def update_price(self, symbol: str, price: float) -> None:
        self._price_cache[symbol] = price

    def get_prices(self) -> Dict[str, float]:
        return dict(self._price_cache)

    async def push_signal(self, signal_data: Dict) -> None:
        await self._signal_queue.put(signal_data)

    async def broadcast_prices_loop(self) -> None:
        """Broadcast cached prices every second."""
        while self._running:
            try:
                if self._price_cache and self.active_connections.get("prices"):
                    await self.broadcast("prices", {
                        "type": "prices",
                        "data": self._price_cache,
                    })
            except Exception as e:
                logger.error(f"Price broadcast error: {e}")
            await asyncio.sleep(1)

    async def broadcast_signals_loop(self) -> None:
        """Consume signal queue and broadcast to subscribers."""
        while self._running:
            try:
                try:
                    signal = self._signal_queue.get_nowait()
                    await self.broadcast("signals", {"type": "signal", "data": signal})
                except asyncio.QueueEmpty:
                    pass
            except Exception as e:
                logger.error(f"Signal broadcast error: {e}")
            await asyncio.sleep(0.5)

    async def start_background_tasks(self) -> None:
        self._running = True
        asyncio.create_task(self.broadcast_prices_loop())
        asyncio.create_task(self.broadcast_signals_loop())

    async def stop(self) -> None:
        self._running = False


manager = ConnectionManager()

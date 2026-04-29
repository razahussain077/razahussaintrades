"""
WebSocket consumers for real-time exchange data feeds.

Each module in this package owns one stream + a graceful reconnect loop.
The `register_streams(app)` function in this __init__ wires them all into
FastAPI's lifespan so they start at boot and stop on shutdown.
"""
from __future__ import annotations

import asyncio
import logging
from typing import List

from app.streams.liquidation_stream import LiquidationStream
from app.streams.aggtrade_stream import AggTradeStream

logger = logging.getLogger(__name__)


class StreamSupervisor:
    """
    Owns the long-running tasks for all WebSocket consumers and exposes
    `start()` / `stop()` for the FastAPI lifespan to call.
    """

    def __init__(self) -> None:
        self.liquidation = LiquidationStream()
        self.aggtrade = AggTradeStream()
        self._tasks: List[asyncio.Task] = []

    async def start(self, aggtrade_symbols: List[str]) -> None:
        """Spin up background tasks for every stream."""
        if self._tasks:
            return
        self._tasks.append(asyncio.create_task(
            self.liquidation.run(), name="liquidation_stream"
        ))
        self._tasks.append(asyncio.create_task(
            self.aggtrade.run(aggtrade_symbols), name="aggtrade_stream"
        ))
        logger.info(
            "stream supervisor: started liquidation + aggTrade streams (%d symbols)",
            len(aggtrade_symbols),
        )

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
        self._tasks = []
        logger.info("stream supervisor: stopped")


stream_supervisor = StreamSupervisor()

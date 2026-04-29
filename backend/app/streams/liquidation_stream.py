"""
Binance USDⓂ-Futures liquidation stream consumer.

Subscribes to wss://fstream.binance.com/ws/!forceOrder@arr — the all-symbols
forced-order (liquidation) stream. Each message has the shape:

    {
      "e": "forceOrder",
      "E": 1568014460893,
      "o": {
        "s": "BTCUSDT",       # symbol
        "S": "SELL",          # side of the liquidating ORDER (so SELL = long
                              # was liquidated; BUY = short was liquidated)
        "o": "LIMIT",
        "q": "0.014",         # original quantity
        "p": "9910",          # original price
        "ap": "9910",         # average filled price
        "X": "FILLED",        # order status
        "l": "0.014",         # last filled quantity
        "z": "0.014",         # accumulated filled quantity
        "T": 1568014460893    # trade time
      }
    }

This stream is the ground truth for liquidations on Binance perps and
replaces the synthetic estimator that `liquidation_engine.estimate_liquidation_zones`
falls back on when no real events are available.

Reconnect strategy: exponential backoff up to 60s, infinite retries. Crashes
in the message handler are logged but don't take down the stream.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

try:
    import websockets
    from websockets.exceptions import ConnectionClosed
    _WS_AVAILABLE = True
except Exception:  # pragma: no cover — websockets is in requirements but be robust
    websockets = None
    ConnectionClosed = Exception  # type: ignore
    _WS_AVAILABLE = False

from app.engines.liquidation_engine import add_liquidation_event

logger = logging.getLogger(__name__)

_BINANCE_FUTURES_WS_URL = "wss://fstream.binance.com/ws/!forceOrder@arr"
_MAX_BACKOFF_SECONDS = 60
_INITIAL_BACKOFF_SECONDS = 1


class LiquidationStream:
    """Long-running liquidation stream consumer for Binance USDⓂ-Futures."""

    def __init__(self, ws_url: str = _BINANCE_FUTURES_WS_URL) -> None:
        self.ws_url = ws_url
        self._stopping = False
        self.events_received: int = 0
        self.last_event_ts: Optional[int] = None

    async def run(self) -> None:
        """Reconnect loop. Cancels cleanly on `task.cancel()`."""
        if not _WS_AVAILABLE:
            logger.error("liquidation_stream: 'websockets' library unavailable; stream disabled")
            return

        backoff = _INITIAL_BACKOFF_SECONDS
        while not self._stopping:
            try:
                logger.info("liquidation_stream: connecting to %s", self.ws_url)
                async with websockets.connect(
                    self.ws_url,
                    ping_interval=20,
                    ping_timeout=20,
                    close_timeout=5,
                    max_size=2 ** 20,
                ) as ws:
                    backoff = _INITIAL_BACKOFF_SECONDS  # connection successful
                    async for raw in ws:
                        await self._handle_message(raw)
            except asyncio.CancelledError:
                logger.info("liquidation_stream: cancelled")
                break
            except ConnectionClosed as e:
                logger.warning("liquidation_stream: connection closed (%s); reconnecting in %ds", e, backoff)
            except Exception as e:
                logger.error("liquidation_stream: unexpected error: %s; reconnecting in %ds", e, backoff)

            try:
                await asyncio.sleep(backoff)
            except asyncio.CancelledError:
                break
            backoff = min(backoff * 2, _MAX_BACKOFF_SECONDS)

    async def stop(self) -> None:
        self._stopping = True

    # ------------------------------------------------------------------
    # Message handling
    # ------------------------------------------------------------------

    async def _handle_message(self, raw: str | bytes) -> None:
        try:
            data = json.loads(raw)
        except (TypeError, ValueError) as e:
            logger.debug("liquidation_stream: bad json: %s", e)
            return

        order = data.get("o") if isinstance(data, dict) else None
        if not order:
            return
        try:
            symbol = order["s"]
            side = order["S"]                   # 'BUY' or 'SELL'
            qty = float(order.get("z") or order.get("q") or 0.0)
            price = float(order.get("ap") or order.get("p") or 0.0)
            ts = int(order.get("T") or data.get("E") or 0)
        except (KeyError, TypeError, ValueError):
            logger.debug("liquidation_stream: malformed order payload: %s", order)
            return

        if qty <= 0 or price <= 0:
            return

        # Side semantics: SELL means the liquidating order was a SELL → a LONG
        # position got liquidated. BUY means a SHORT got liquidated. We pass
        # through `side` unchanged; `liquidation_engine` already interprets it.
        add_liquidation_event(symbol=symbol, side=side, quantity=qty, price=price)
        self.events_received += 1
        self.last_event_ts = ts

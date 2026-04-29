"""
Binance USDⓂ-Futures aggTrade stream consumer (multi-symbol).

Subscribes to wss://fstream.binance.com/stream?streams=<sym>@aggTrade/<sym>@aggTrade/...
for the configured top-N symbols and feeds each tick into
`orderflow_engine.record_trade` so the CVD / large-print / divergence
detectors have live data.

Each combined-stream message has the shape:

    {
      "stream": "btcusdt@aggTrade",
      "data": {
        "e": "aggTrade",
        "E": 1568879465576,
        "s": "BTCUSDT",
        "a": 5933014,            # aggregate trade ID
        "p": "9999.99",          # price
        "q": "1.20",             # quantity
        "f": ..., "l": ...,
        "T": 1568879465576,      # trade time
        "m": true                # was the buyer the maker?
      }
    }

The combined-stream URL has a 1024-stream limit. We cap symbols at 200 and
wrap them into a single connection — well below the cap and far cheaper
than one socket per symbol.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import List, Optional

try:
    import websockets
    from websockets.exceptions import ConnectionClosed
    _WS_AVAILABLE = True
except Exception:  # pragma: no cover
    websockets = None
    ConnectionClosed = Exception  # type: ignore
    _WS_AVAILABLE = False

from app.engines.orderflow_engine import record_trade

logger = logging.getLogger(__name__)

_BINANCE_FSTREAM_BASE = "wss://fstream.binance.com/stream?streams="
_MAX_SUBSCRIBED_SYMBOLS = 200
_MAX_BACKOFF_SECONDS = 60
_INITIAL_BACKOFF_SECONDS = 1


def _build_combined_url(symbols: List[str]) -> str:
    streams = "/".join(f"{s.lower()}@aggTrade" for s in symbols)
    return _BINANCE_FSTREAM_BASE + streams


class AggTradeStream:
    """Long-running combined-stream aggTrade consumer."""

    def __init__(self) -> None:
        self._stopping = False
        self.ticks_received: int = 0
        self.last_tick_ms: Optional[int] = None
        self.subscribed_symbols: List[str] = []

    async def run(self, symbols: List[str]) -> None:
        if not _WS_AVAILABLE:
            logger.error("aggtrade_stream: 'websockets' library unavailable; stream disabled")
            return
        if not symbols:
            logger.warning("aggtrade_stream: no symbols configured; stream skipped")
            return

        self.subscribed_symbols = symbols[:_MAX_SUBSCRIBED_SYMBOLS]
        url = _build_combined_url(self.subscribed_symbols)
        backoff = _INITIAL_BACKOFF_SECONDS
        while not self._stopping:
            try:
                logger.info(
                    "aggtrade_stream: connecting (%d symbols)", len(self.subscribed_symbols)
                )
                async with websockets.connect(
                    url, ping_interval=20, ping_timeout=20, close_timeout=5,
                    max_size=2 ** 20,
                ) as ws:
                    backoff = _INITIAL_BACKOFF_SECONDS
                    async for raw in ws:
                        await self._handle_message(raw)
            except asyncio.CancelledError:
                logger.info("aggtrade_stream: cancelled")
                break
            except ConnectionClosed as e:
                logger.warning("aggtrade_stream: connection closed (%s); reconnecting in %ds", e, backoff)
            except Exception as e:
                logger.error("aggtrade_stream: unexpected error: %s; reconnecting in %ds", e, backoff)

            try:
                await asyncio.sleep(backoff)
            except asyncio.CancelledError:
                break
            backoff = min(backoff * 2, _MAX_BACKOFF_SECONDS)

    async def stop(self) -> None:
        self._stopping = True

    async def _handle_message(self, raw: str | bytes) -> None:
        try:
            envelope = json.loads(raw)
        except (TypeError, ValueError):
            return

        # Combined-stream wraps the payload in {"stream": ..., "data": ...}.
        data = envelope.get("data") if isinstance(envelope, dict) else None
        if not data:
            return
        try:
            symbol = data["s"]
            price = float(data.get("p") or 0.0)
            qty = float(data.get("q") or 0.0)
            ts = int(data.get("T") or data.get("E") or 0)
            is_buyer_maker = bool(data.get("m"))
        except (KeyError, TypeError, ValueError):
            return

        if price <= 0 or qty <= 0 or ts <= 0:
            return
        record_trade(symbol, ts, price, qty, is_buyer_maker)
        self.ticks_received += 1
        self.last_tick_ms = ts

"""
Order Flow API routes — exposes CVD, large-print bursts, CVD divergences,
and stream-supervisor health.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.engines.orderflow_engine import (
    detect_cvd_divergence,
    detect_large_prints,
    get_all_symbols_with_data,
    get_cvd_snapshot,
)
from app.exchanges.binance_client import binance_client
from app.streams import stream_supervisor

logger = logging.getLogger(__name__)
orderflow_router = APIRouter()


@orderflow_router.get(
    "/orderflow/{symbol}",
    summary="CVD + large prints for one symbol",
    tags=["Order Flow"],
)
async def get_orderflow(symbol: str):
    """
    Returns:
      * cvd over 1m / 5m / 15m / 1h windows (positive = aggressive buying)
      * delta_1m_normalized in [-1, +1] (signed share of last-minute volume)
      * large_buy_count / large_sell_count + dollar volumes (last 1m)
      * total trades recorded in the rolling buffer
    """
    symbol = symbol.upper()
    cvd = get_cvd_snapshot(symbol)
    bursts = detect_large_prints(symbol)
    return {
        "symbol": symbol,
        "cvd": cvd,
        "large_prints": bursts,
    }


@orderflow_router.get(
    "/orderflow/{symbol}/divergence",
    summary="Detect CVD–price divergence over recent 1m candles",
    tags=["Order Flow"],
)
async def get_orderflow_divergence(
    symbol: str,
    lookback_bars: int = Query(20, ge=6, le=120),
):
    """
    Looks at the last `lookback_bars` 1m candles and reports whether price
    made a new low/high while CVD did not (classic absorption divergence).
    """
    symbol = symbol.upper()
    candles = await binance_client.get_klines(symbol, "1m", limit=lookback_bars * 2)
    if not candles:
        raise HTTPException(status_code=502, detail="No 1m candles available")
    return detect_cvd_divergence(symbol, candles, lookback_bars=lookback_bars)


@orderflow_router.get(
    "/orderflow/streams/health",
    summary="Health snapshot of the WebSocket consumers",
    tags=["Order Flow"],
)
async def get_streams_health():
    return {
        "liquidation": {
            "events_received": stream_supervisor.liquidation.events_received,
            "last_event_ts": stream_supervisor.liquidation.last_event_ts,
        },
        "aggtrade": {
            "ticks_received": stream_supervisor.aggtrade.ticks_received,
            "last_tick_ms": stream_supervisor.aggtrade.last_tick_ms,
            "subscribed_symbols": stream_supervisor.aggtrade.subscribed_symbols,
        },
        "symbols_with_orderflow_data": get_all_symbols_with_data(),
    }

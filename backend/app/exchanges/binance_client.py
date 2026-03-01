import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Simple TTL cache
_cache: Dict[str, tuple] = {}  # key -> (value, expiry_ts)


def _get_cache(key: str) -> Optional[Any]:
    entry = _cache.get(key)
    if entry and time.time() < entry[1]:
        return entry[0]
    return None


def _set_cache(key: str, value: Any, ttl: int) -> None:
    _cache[key] = (value, time.time() + ttl)


class BinanceClient:
    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        self._futures_client: Optional[httpx.AsyncClient] = None
        self._ws_running = False
        self._price_callbacks: List = []

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=settings.BINANCE_BASE_URL,
                timeout=10.0,
            )
        return self._client

    @property
    def futures_client(self) -> httpx.AsyncClient:
        if self._futures_client is None or self._futures_client.is_closed:
            self._futures_client = httpx.AsyncClient(
                base_url=settings.BINANCE_FUTURES_URL,
                timeout=10.0,
            )
        return self._futures_client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
        if self._futures_client and not self._futures_client.is_closed:
            await self._futures_client.aclose()

    async def get_futures_symbols(self) -> List[str]:
        cache_key = "futures_symbols"
        cached = _get_cache(cache_key)
        if cached:
            return cached
        try:
            resp = await self.futures_client.get("/fapi/v1/exchangeInfo")
            resp.raise_for_status()
            data = resp.json()
            symbols = [
                s["symbol"]
                for s in data.get("symbols", [])
                if s.get("quoteAsset") == "USDT"
                and s.get("contractType") == "PERPETUAL"
                and s.get("status") == "TRADING"
            ]
            _set_cache(cache_key, symbols, 3600)
            return symbols
        except Exception as e:
            logger.error(f"Binance get_futures_symbols error: {e}")
            return []

    async def get_klines(
        self,
        symbol: str,
        interval: str = "1h",
        limit: int = 100,
    ) -> List[Dict]:
        cache_key = f"klines_{symbol}_{interval}_{limit}"
        cached = _get_cache(cache_key)
        if cached:
            return cached
        try:
            resp = await self.futures_client.get(
                "/fapi/v1/klines",
                params={"symbol": symbol, "interval": interval, "limit": limit},
            )
            resp.raise_for_status()
            raw = resp.json()
            candles = [
                {
                    "timestamp": c[0],
                    "open": float(c[1]),
                    "high": float(c[2]),
                    "low": float(c[3]),
                    "close": float(c[4]),
                    "volume": float(c[5]),
                    "close_time": c[6],
                    "quote_volume": float(c[7]),
                    "trades": int(c[8]),
                }
                for c in raw
            ]
            _set_cache(cache_key, candles, settings.CANDLE_CACHE_TTL)
            return candles
        except Exception as e:
            logger.error(f"Binance get_klines {symbol}/{interval} error: {e}")
            return []

    async def get_spot_klines(
        self,
        symbol: str,
        interval: str = "1h",
        limit: int = 100,
    ) -> List[Dict]:
        cache_key = f"spot_klines_{symbol}_{interval}_{limit}"
        cached = _get_cache(cache_key)
        if cached:
            return cached
        try:
            resp = await self.client.get(
                "/api/v3/klines",
                params={"symbol": symbol, "interval": interval, "limit": limit},
            )
            resp.raise_for_status()
            raw = resp.json()
            candles = [
                {
                    "timestamp": c[0],
                    "open": float(c[1]),
                    "high": float(c[2]),
                    "low": float(c[3]),
                    "close": float(c[4]),
                    "volume": float(c[5]),
                    "close_time": c[6],
                    "quote_volume": float(c[7]),
                    "trades": int(c[8]),
                }
                for c in raw
            ]
            _set_cache(cache_key, candles, settings.CANDLE_CACHE_TTL)
            return candles
        except Exception as e:
            logger.error(f"Binance get_spot_klines {symbol}/{interval} error: {e}")
            return []

    async def get_order_book(self, symbol: str, limit: int = 20) -> Dict:
        cache_key = f"orderbook_{symbol}_{limit}"
        cached = _get_cache(cache_key)
        if cached:
            return cached
        try:
            resp = await self.futures_client.get(
                "/fapi/v1/depth",
                params={"symbol": symbol, "limit": limit},
            )
            resp.raise_for_status()
            data = resp.json()
            result = {
                "bids": [[float(p), float(q)] for p, q in data.get("bids", [])],
                "asks": [[float(p), float(q)] for p, q in data.get("asks", [])],
            }
            _set_cache(cache_key, result, 5)
            return result
        except Exception as e:
            logger.error(f"Binance get_order_book {symbol} error: {e}")
            return {"bids": [], "asks": []}

    async def get_ticker_24h(self, symbol: Optional[str] = None) -> Any:
        cache_key = f"ticker24h_{symbol or 'all'}"
        cached = _get_cache(cache_key)
        if cached:
            return cached
        try:
            params = {}
            if symbol:
                params["symbol"] = symbol
            resp = await self.futures_client.get("/fapi/v1/ticker/24hr", params=params)
            resp.raise_for_status()
            data = resp.json()
            _set_cache(cache_key, data, settings.PRICE_CACHE_TTL)
            return data
        except Exception as e:
            logger.error(f"Binance get_ticker_24h error: {e}")
            return [] if symbol is None else {}

    async def get_funding_rate(self, symbol: str) -> Dict:
        cache_key = f"funding_{symbol}"
        cached = _get_cache(cache_key)
        if cached:
            return cached
        try:
            resp = await self.futures_client.get(
                "/fapi/v1/premiumIndex",
                params={"symbol": symbol},
            )
            resp.raise_for_status()
            data = resp.json()
            result = {
                "symbol": data.get("symbol"),
                "funding_rate": float(data.get("lastFundingRate", 0)),
                "next_funding_time": data.get("nextFundingTime"),
                "mark_price": float(data.get("markPrice", 0)),
                "index_price": float(data.get("indexPrice", 0)),
            }
            _set_cache(cache_key, result, 30)
            return result
        except Exception as e:
            logger.error(f"Binance get_funding_rate {symbol} error: {e}")
            return {"symbol": symbol, "funding_rate": 0.0}

    async def get_open_interest(self, symbol: str) -> Dict:
        cache_key = f"oi_{symbol}"
        cached = _get_cache(cache_key)
        if cached:
            return cached
        try:
            resp = await self.futures_client.get(
                "/fapi/v1/openInterest",
                params={"symbol": symbol},
            )
            resp.raise_for_status()
            data = resp.json()
            result = {
                "symbol": data.get("symbol"),
                "open_interest": float(data.get("openInterest", 0)),
                "time": data.get("time"),
            }
            _set_cache(cache_key, result, 30)
            return result
        except Exception as e:
            logger.error(f"Binance get_open_interest {symbol} error: {e}")
            return {"symbol": symbol, "open_interest": 0.0}

    async def get_price(self, symbol: str) -> float:
        cache_key = f"price_{symbol}"
        cached = _get_cache(cache_key)
        if cached is not None:
            return cached
        try:
            resp = await self.futures_client.get(
                "/fapi/v1/ticker/price",
                params={"symbol": symbol},
            )
            resp.raise_for_status()
            data = resp.json()
            price = float(data.get("price", 0))
            _set_cache(cache_key, price, settings.PRICE_CACHE_TTL)
            return price
        except Exception as e:
            logger.error(f"Binance get_price {symbol} error: {e}")
            return 0.0

    async def get_all_prices(self) -> Dict[str, float]:
        cache_key = "all_prices"
        cached = _get_cache(cache_key)
        if cached:
            return cached
        try:
            resp = await self.futures_client.get("/fapi/v1/ticker/price")
            resp.raise_for_status()
            raw = resp.json()
            prices = {item["symbol"]: float(item["price"]) for item in raw}
            _set_cache(cache_key, prices, settings.PRICE_CACHE_TTL)
            return prices
        except Exception as e:
            logger.error(f"Binance get_all_prices error: {e}")
            return {}


binance_client = BinanceClient()

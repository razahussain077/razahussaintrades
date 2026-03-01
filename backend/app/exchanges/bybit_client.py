import logging
import time
from typing import Any, Dict, List, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_cache: Dict[str, tuple] = {}


def _get_cache(key: str) -> Optional[Any]:
    entry = _cache.get(key)
    if entry and time.time() < entry[1]:
        return entry[0]
    return None


def _set_cache(key: str, value: Any, ttl: int) -> None:
    _cache[key] = (value, time.time() + ttl)


BYBIT_TO_STANDARD: Dict[str, str] = {}


def _normalize_symbol(bybit_symbol: str) -> str:
    """Convert BYBIT symbol like BTC-USDT to BTCUSDT."""
    return bybit_symbol.replace("-", "")


class BybitClient:
    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=settings.BYBIT_BASE_URL,
                timeout=10.0,
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def get_tickers(self, category: str = "linear") -> List[Dict]:
        """Fetch tickers from Bybit v5 API."""
        cache_key = f"bybit_tickers_{category}"
        cached = _get_cache(cache_key)
        if cached:
            return cached
        try:
            resp = await self.client.get(
                "/v5/market/tickers",
                params={"category": category},
            )
            resp.raise_for_status()
            data = resp.json()
            tickers = []
            for item in data.get("result", {}).get("list", []):
                symbol_raw = item.get("symbol", "")
                if not symbol_raw.endswith("USDT"):
                    continue
                tickers.append(
                    {
                        "symbol": symbol_raw,
                        "last_price": float(item.get("lastPrice", 0) or 0),
                        "price_change_pct": float(item.get("price24hPcnt", 0) or 0) * 100,
                        "volume_24h": float(item.get("volume24h", 0) or 0),
                        "high_24h": float(item.get("highPrice24h", 0) or 0),
                        "low_24h": float(item.get("lowPrice24h", 0) or 0),
                        "open_interest": float(item.get("openInterest", 0) or 0),
                        "funding_rate": float(item.get("fundingRate", 0) or 0),
                        "exchange": "bybit",
                    }
                )
            _set_cache(cache_key, tickers, settings.PRICE_CACHE_TTL)
            return tickers
        except Exception as e:
            logger.error(f"Bybit get_tickers error: {e}")
            return []

    async def get_klines(
        self,
        symbol: str,
        interval: str = "60",
        limit: int = 100,
    ) -> List[Dict]:
        """
        Fetch klines from Bybit v5 API.
        interval: 1, 3, 5, 15, 30, 60, 120, 240, 360, 720, D, W, M
        """
        cache_key = f"bybit_klines_{symbol}_{interval}_{limit}"
        cached = _get_cache(cache_key)
        if cached:
            return cached
        try:
            resp = await self.client.get(
                "/v5/market/kline",
                params={
                    "category": "linear",
                    "symbol": symbol,
                    "interval": interval,
                    "limit": limit,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            raw_list = data.get("result", {}).get("list", [])
            candles = []
            for c in reversed(raw_list):  # Bybit returns newest first
                candles.append(
                    {
                        "timestamp": int(c[0]),
                        "open": float(c[1]),
                        "high": float(c[2]),
                        "low": float(c[3]),
                        "close": float(c[4]),
                        "volume": float(c[5]),
                        "quote_volume": float(c[6]) if len(c) > 6 else 0.0,
                    }
                )
            _set_cache(cache_key, candles, settings.CANDLE_CACHE_TTL)
            return candles
        except Exception as e:
            logger.error(f"Bybit get_klines {symbol}/{interval} error: {e}")
            return []

    async def get_ticker(self, symbol: str) -> Dict:
        """Fetch single ticker."""
        tickers = await self.get_tickers()
        for t in tickers:
            if t["symbol"] == symbol:
                return t
        return {}

    @staticmethod
    def binance_interval_to_bybit(interval: str) -> str:
        mapping = {
            "1m": "1",
            "5m": "5",
            "15m": "15",
            "30m": "30",
            "1h": "60",
            "4h": "240",
            "1d": "D",
            "1w": "W",
        }
        return mapping.get(interval, "60")


bybit_client = BybitClient()

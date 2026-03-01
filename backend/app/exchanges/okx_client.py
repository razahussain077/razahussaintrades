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


class OKXClient:
    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=settings.OKX_BASE_URL,
                timeout=10.0,
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    @staticmethod
    def _okx_to_standard(symbol: str) -> str:
        """Convert OKX format BTC-USDT-SWAP -> BTCUSDT."""
        base = symbol.replace("-SWAP", "").replace("-USDT", "USDT").replace("-", "")
        return base

    async def get_tickers(self, inst_type: str = "SWAP") -> List[Dict]:
        """Fetch tickers from OKX v5 API."""
        cache_key = f"okx_tickers_{inst_type}"
        cached = _get_cache(cache_key)
        if cached:
            return cached
        try:
            resp = await self.client.get(
                "/api/v5/market/tickers",
                params={"instType": inst_type},
            )
            resp.raise_for_status()
            data = resp.json()
            tickers = []
            for item in data.get("data", []):
                inst_id = item.get("instId", "")
                if not inst_id.endswith("-USDT-SWAP"):
                    continue
                std_symbol = self._okx_to_standard(inst_id)
                tickers.append(
                    {
                        "symbol": std_symbol,
                        "okx_symbol": inst_id,
                        "last_price": float(item.get("last", 0) or 0),
                        "price_change_pct": 0.0,
                        "volume_24h": float(item.get("vol24h", 0) or 0),
                        "high_24h": float(item.get("high24h", 0) or 0),
                        "low_24h": float(item.get("low24h", 0) or 0),
                        "open_24h": float(item.get("open24h", 0) or 0),
                        "exchange": "okx",
                    }
                )
            _set_cache(cache_key, tickers, settings.PRICE_CACHE_TTL)
            return tickers
        except Exception as e:
            logger.error(f"OKX get_tickers error: {e}")
            return []

    async def get_klines(
        self,
        okx_symbol: str,
        bar: str = "1H",
        limit: int = 100,
    ) -> List[Dict]:
        """
        Fetch klines from OKX v5 API.
        bar: 1m, 3m, 5m, 15m, 30m, 1H, 2H, 4H, 6H, 12H, 1D, 1W
        okx_symbol should be in OKX format, e.g. BTC-USDT-SWAP
        """
        cache_key = f"okx_klines_{okx_symbol}_{bar}_{limit}"
        cached = _get_cache(cache_key)
        if cached:
            return cached
        try:
            resp = await self.client.get(
                "/api/v5/market/candles",
                params={"instId": okx_symbol, "bar": bar, "limit": limit},
            )
            resp.raise_for_status()
            data = resp.json()
            raw_list = data.get("data", [])
            candles = []
            for c in reversed(raw_list):  # OKX returns newest first
                candles.append(
                    {
                        "timestamp": int(c[0]),
                        "open": float(c[1]),
                        "high": float(c[2]),
                        "low": float(c[3]),
                        "close": float(c[4]),
                        "volume": float(c[5]),
                        "quote_volume": float(c[7]) if len(c) > 7 else 0.0,
                    }
                )
            _set_cache(cache_key, candles, settings.CANDLE_CACHE_TTL)
            return candles
        except Exception as e:
            logger.error(f"OKX get_klines {okx_symbol}/{bar} error: {e}")
            return []

    @staticmethod
    def standard_to_okx_symbol(symbol: str) -> str:
        """Convert BTCUSDT -> BTC-USDT-SWAP."""
        if symbol.endswith("USDT"):
            base = symbol[:-4]
            return f"{base}-USDT-SWAP"
        return symbol

    @staticmethod
    def binance_interval_to_okx(interval: str) -> str:
        mapping = {
            "1m": "1m",
            "5m": "5m",
            "15m": "15m",
            "30m": "30m",
            "1h": "1H",
            "4h": "4H",
            "1d": "1D",
            "1w": "1W",
        }
        return mapping.get(interval, "1H")


okx_client = OKXClient()

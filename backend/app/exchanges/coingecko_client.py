import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_cache: Dict[str, tuple] = {}
_last_request_time: float = 0.0
_REQUEST_INTERVAL = 2.5  # 30 req/min max; use 2.5s interval for safety margin


def _get_cache(key: str) -> Optional[Any]:
    entry = _cache.get(key)
    if entry and time.time() < entry[1]:
        return entry[0]
    return None


def _set_cache(key: str, value: Any, ttl: int) -> None:
    _cache[key] = (value, time.time() + ttl)


async def _rate_limit():
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < _REQUEST_INTERVAL:
        await asyncio.sleep(_REQUEST_INTERVAL - elapsed)
    _last_request_time = time.time()


class CoinGeckoClient:
    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=settings.COINGECKO_BASE_URL,
                timeout=15.0,
                headers={"Accept": "application/json"},
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def get_coins_markets(
        self,
        vs_currency: str = "usd",
        per_page: int = 50,
        page: int = 1,
    ) -> List[Dict]:
        """Fetch coins with market cap, volume, price data."""
        cache_key = f"cg_markets_{vs_currency}_{per_page}_{page}"
        cached = _get_cache(cache_key)
        if cached:
            return cached
        await _rate_limit()
        try:
            resp = await self.client.get(
                "/coins/markets",
                params={
                    "vs_currency": vs_currency,
                    "order": "market_cap_desc",
                    "per_page": per_page,
                    "page": page,
                    "sparkline": "false",
                    "price_change_percentage": "1h,24h,7d",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            result = [
                {
                    "id": coin.get("id"),
                    "symbol": coin.get("symbol", "").upper(),
                    "name": coin.get("name"),
                    "current_price": coin.get("current_price", 0),
                    "market_cap": coin.get("market_cap", 0),
                    "market_cap_rank": coin.get("market_cap_rank"),
                    "total_volume": coin.get("total_volume", 0),
                    "price_change_1h": coin.get("price_change_percentage_1h_in_currency", 0),
                    "price_change_24h": coin.get("price_change_percentage_24h_in_currency", 0),
                    "price_change_7d": coin.get("price_change_percentage_7d_in_currency", 0),
                    "high_24h": coin.get("high_24h", 0),
                    "low_24h": coin.get("low_24h", 0),
                    "circulating_supply": coin.get("circulating_supply", 0),
                    "image": coin.get("image"),
                }
                for coin in data
            ]
            _set_cache(cache_key, result, settings.MARKET_CACHE_TTL)
            return result
        except Exception as e:
            logger.error(f"CoinGecko get_coins_markets error: {e}")
            return []

    async def get_global_market_data(self) -> Dict:
        """Fetch global market data (total market cap, BTC dominance, etc.)."""
        cache_key = "cg_global"
        cached = _get_cache(cache_key)
        if cached:
            return cached
        await _rate_limit()
        try:
            resp = await self.client.get("/global")
            resp.raise_for_status()
            data = resp.json().get("data", {})
            result = {
                "total_market_cap_usd": data.get("total_market_cap", {}).get("usd", 0),
                "total_volume_usd": data.get("total_volume", {}).get("usd", 0),
                "btc_dominance": data.get("market_cap_percentage", {}).get("btc", 0),
                "eth_dominance": data.get("market_cap_percentage", {}).get("eth", 0),
                "active_cryptocurrencies": data.get("active_cryptocurrencies", 0),
                "markets": data.get("markets", 0),
                "market_cap_change_pct_24h": data.get("market_cap_change_percentage_24h_usd", 0),
            }
            _set_cache(cache_key, result, settings.MARKET_CACHE_TTL)
            return result
        except Exception as e:
            logger.error(f"CoinGecko get_global_market_data error: {e}")
            return {
                "total_market_cap_usd": 0,
                "total_volume_usd": 0,
                "btc_dominance": 0,
                "eth_dominance": 0,
                "active_cryptocurrencies": 0,
                "markets": 0,
                "market_cap_change_pct_24h": 0,
            }

    async def get_fear_greed_index(self) -> Dict:
        """
        CoinGecko free tier doesn't have fear/greed directly.
        We derive a simplified score from market data.
        """
        cache_key = "cg_fear_greed"
        cached = _get_cache(cache_key)
        if cached:
            return cached
        try:
            global_data = await self.get_global_market_data()
            market_change = global_data.get("market_cap_change_pct_24h", 0)
            btc_dom = global_data.get("btc_dominance", 50)

            # Simplified sentiment score based on market conditions
            score = 50  # neutral baseline
            score += min(25, max(-25, market_change * 5))
            # High BTC dominance often signals fear (alt flight to BTC)
            score -= (btc_dom - 40) * 0.5

            score = max(0, min(100, score))

            if score >= 75:
                label = "Extreme Greed"
            elif score >= 55:
                label = "Greed"
            elif score >= 45:
                label = "Neutral"
            elif score >= 25:
                label = "Fear"
            else:
                label = "Extreme Fear"

            result = {
                "score": round(score, 1),
                "label": label,
                "source": "derived",
            }
            _set_cache(cache_key, result, settings.MARKET_CACHE_TTL)
            return result
        except Exception as e:
            logger.error(f"CoinGecko get_fear_greed_index error: {e}")
            return {"score": 50, "label": "Neutral", "source": "derived"}


coingecko_client = CoinGeckoClient()

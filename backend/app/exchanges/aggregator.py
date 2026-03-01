import asyncio
import logging
from typing import Dict, List, Optional

from app.exchanges.binance_client import binance_client
from app.exchanges.bybit_client import bybit_client
from app.exchanges.okx_client import okx_client
from app.exchanges.coingecko_client import coingecko_client
from app.config import settings

logger = logging.getLogger(__name__)


class AggregatedPrice:
    def __init__(self):
        self.symbol: str = ""
        self.binance_price: float = 0.0
        self.bybit_price: float = 0.0
        self.okx_price: float = 0.0
        self.best_bid: float = 0.0
        self.best_ask: float = 0.0
        self.average_price: float = 0.0
        self.volume_24h: float = 0.0
        self.price_change_pct_24h: float = 0.0
        self.high_24h: float = 0.0
        self.low_24h: float = 0.0
        self.funding_rate: float = 0.0
        self.open_interest: float = 0.0
        self.exchange_count: int = 0


class ExchangeAggregator:
    async def get_aggregated_price(self, symbol: str) -> AggregatedPrice:
        """Fetch and aggregate price data from all exchanges."""
        result = AggregatedPrice()
        result.symbol = symbol

        prices = []

        # Binance
        try:
            binance_ticker = await binance_client.get_ticker_24h(symbol)
            if binance_ticker:
                bp = float(binance_ticker.get("lastPrice", 0))
                if bp > 0:
                    result.binance_price = bp
                    prices.append(bp)
                    result.volume_24h += float(binance_ticker.get("quoteVolume", 0))
                    result.price_change_pct_24h = float(binance_ticker.get("priceChangePercent", 0))
                    result.high_24h = float(binance_ticker.get("highPrice", 0))
                    result.low_24h = float(binance_ticker.get("lowPrice", 0))
                    result.exchange_count += 1
        except Exception as e:
            logger.warning(f"Binance price fetch failed for {symbol}: {e}")

        # Funding rate and OI from Binance futures
        try:
            fr = await binance_client.get_funding_rate(symbol)
            result.funding_rate = fr.get("funding_rate", 0.0)
            oi = await binance_client.get_open_interest(symbol)
            result.open_interest = oi.get("open_interest", 0.0)
        except Exception:
            pass

        # Bybit
        try:
            bybit_tickers = await bybit_client.get_tickers()
            for t in bybit_tickers:
                if t["symbol"] == symbol:
                    bp = t.get("last_price", 0)
                    if bp > 0:
                        result.bybit_price = bp
                        prices.append(bp)
                        result.exchange_count += 1
                    break
        except Exception as e:
            logger.warning(f"Bybit price fetch failed for {symbol}: {e}")

        # OKX
        try:
            okx_tickers = await okx_client.get_tickers()
            for t in okx_tickers:
                if t["symbol"] == symbol:
                    op = t.get("last_price", 0)
                    if op > 0:
                        result.okx_price = op
                        prices.append(op)
                        result.exchange_count += 1
                    break
        except Exception as e:
            logger.warning(f"OKX price fetch failed for {symbol}: {e}")

        if prices:
            result.average_price = sum(prices) / len(prices)
            result.best_bid = min(prices)
            result.best_ask = max(prices)

        return result

    async def get_all_top_coins_data(self) -> List[Dict]:
        """Return aggregated ticker data for all top coins."""
        try:
            all_binance = await binance_client.get_ticker_24h()
            binance_map: Dict[str, Dict] = {}
            if isinstance(all_binance, list):
                for item in all_binance:
                    binance_map[item.get("symbol", "")] = item

            all_bybit = await bybit_client.get_tickers()
            bybit_map: Dict[str, Dict] = {t["symbol"]: t for t in all_bybit}

            all_okx = await okx_client.get_tickers()
            okx_map: Dict[str, Dict] = {t["symbol"]: t for t in all_okx}

            results = []
            for symbol in settings.TOP_50_COINS:
                entry: Dict = {"symbol": symbol, "exchange": "binance", "sources": []}
                prices = []

                if symbol in binance_map:
                    b = binance_map[symbol]
                    bp = float(b.get("lastPrice", 0))
                    if bp > 0:
                        prices.append(bp)
                        entry["price_change_pct_24h"] = float(b.get("priceChangePercent", 0))
                        entry["volume_24h"] = float(b.get("quoteVolume", 0))
                        entry["high_24h"] = float(b.get("highPrice", 0))
                        entry["low_24h"] = float(b.get("lowPrice", 0))
                        entry["sources"].append("binance")

                if symbol in bybit_map:
                    bybit_p = bybit_map[symbol].get("last_price", 0)
                    if bybit_p > 0:
                        prices.append(bybit_p)
                        entry["sources"].append("bybit")

                if symbol in okx_map:
                    okx_p = okx_map[symbol].get("last_price", 0)
                    if okx_p > 0:
                        prices.append(okx_p)
                        entry["sources"].append("okx")

                if prices:
                    entry["price"] = sum(prices) / len(prices)
                    entry["exchange_count"] = len(prices)
                    results.append(entry)

            return results
        except Exception as e:
            logger.error(f"get_all_top_coins_data error: {e}")
            return []

    async def get_best_candles(
        self,
        symbol: str,
        interval: str = "1h",
        limit: int = 100,
    ) -> List[Dict]:
        """Get candles, preferring Binance, falling back to Bybit."""
        candles = await binance_client.get_klines(symbol, interval, limit)
        if candles:
            return candles

        # Fallback to Bybit
        bybit_interval = bybit_client.binance_interval_to_bybit(interval)
        candles = await bybit_client.get_klines(symbol, bybit_interval, limit)
        if candles:
            return candles

        # Fallback to OKX
        okx_symbol = okx_client.standard_to_okx_symbol(symbol)
        okx_bar = okx_client.binance_interval_to_okx(interval)
        candles = await okx_client.get_klines(okx_symbol, okx_bar, limit)
        return candles

    async def get_market_overview(self) -> Dict:
        """Aggregate market-wide overview data."""
        global_data = await coingecko_client.get_global_market_data()
        fear_greed = await coingecko_client.get_fear_greed_index()

        # BTC funding rate
        btc_funding = await binance_client.get_funding_rate("BTCUSDT")
        eth_funding = await binance_client.get_funding_rate("ETHUSDT")

        return {
            "total_market_cap_usd": global_data.get("total_market_cap_usd", 0),
            "total_volume_usd": global_data.get("total_volume_usd", 0),
            "btc_dominance": global_data.get("btc_dominance", 0),
            "eth_dominance": global_data.get("eth_dominance", 0),
            "market_cap_change_pct_24h": global_data.get("market_cap_change_pct_24h", 0),
            "fear_greed_score": fear_greed.get("score", 50),
            "fear_greed_label": fear_greed.get("label", "Neutral"),
            "btc_funding_rate": btc_funding.get("funding_rate", 0),
            "eth_funding_rate": eth_funding.get("funding_rate", 0),
            "active_cryptocurrencies": global_data.get("active_cryptocurrencies", 0),
        }


aggregator = ExchangeAggregator()

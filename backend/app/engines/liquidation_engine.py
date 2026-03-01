"""
Liquidation Heatmap Engine — Feature 1
Tracks real-time liquidation events and estimates liquidation zones
based on Open Interest and common leverage levels.
"""
import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.exchanges.binance_client import binance_client

logger = logging.getLogger(__name__)

# Common leverage levels traders use
LEVERAGE_LEVELS = [3, 5, 10, 20, 25, 50]

# In-memory store for recent liquidation events (last 1000 per symbol)
_liquidation_events: Dict[str, List[Dict]] = defaultdict(list)
_MAX_EVENTS = 1000


def _round_to_significant_level(price: float) -> float:
    """Round price to a significant level for clustering."""
    if price <= 0:
        return price
    # Use 0.5% increments for clustering
    magnitude = price * 0.005
    if magnitude >= 100:
        step = 100
    elif magnitude >= 10:
        step = 10
    elif magnitude >= 1:
        step = 1
    elif magnitude >= 0.1:
        step = 0.1
    elif magnitude >= 0.01:
        step = 0.01
    else:
        step = 0.001
    return round(round(price / step) * step, 8)


def estimate_liquidation_zones(
    current_price: float,
    open_interest: float,
    leverage_levels: Optional[List[int]] = None,
) -> List[Dict]:
    """
    Estimate liquidation price zones given current price and open interest.
    Returns a list of zones sorted by price.
    """
    if leverage_levels is None:
        leverage_levels = LEVERAGE_LEVELS

    zones: Dict[float, Dict] = {}

    for lev in leverage_levels:
        # Long liquidation: entry_price * (1 - 1/leverage)
        long_liq = current_price * (1 - 1 / lev)
        # Short liquidation: entry_price * (1 + 1/leverage)
        short_liq = current_price * (1 + 1 / lev)

        # Bucket by significant level
        long_key = _round_to_significant_level(long_liq)
        short_key = _round_to_significant_level(short_liq)

        # Approximate $ value at risk (proportional to leverage level distribution)
        # Higher leverage = more frequent = more $  at risk
        weight = lev / sum(LEVERAGE_LEVELS)
        liq_value = open_interest * weight * current_price

        if long_key not in zones:
            zones[long_key] = {"price": long_key, "long_value": 0.0, "short_value": 0.0, "leverages": []}
        zones[long_key]["long_value"] += liq_value
        zones[long_key]["leverages"].append(lev)

        if short_key not in zones:
            zones[short_key] = {"price": short_key, "long_value": 0.0, "short_value": 0.0, "leverages": []}
        zones[short_key]["short_value"] += liq_value
        zones[short_key]["leverages"].append(lev)

    result = []
    for zone in zones.values():
        total = zone["long_value"] + zone["short_value"]
        result.append({
            "price": zone["price"],
            "long_liquidation_value": round(zone["long_value"], 2),
            "short_liquidation_value": round(zone["short_value"], 2),
            "total_liquidation_value": round(total, 2),
            "density": "high" if total > open_interest * current_price * 0.15
                      else "medium" if total > open_interest * current_price * 0.05
                      else "low",
            "leverages": list(set(zone["leverages"])),
        })

    return sorted(result, key=lambda x: x["price"])


def find_liquidation_magnet(zones: List[Dict], current_price: float) -> Optional[Dict]:
    """
    Identify the liquidation magnet — price level with highest concentration
    of pending liquidations. Price is attracted toward these levels.
    """
    if not zones:
        return None

    # Find zone with highest total liquidation value
    best = max(zones, key=lambda z: z["total_liquidation_value"])

    direction = "above" if best["price"] > current_price else "below"
    distance_pct = abs(best["price"] - current_price) / current_price * 100

    return {
        "price": best["price"],
        "direction": direction,
        "distance_pct": round(distance_pct, 2),
        "liquidation_value": best["total_liquidation_value"],
        "density": best["density"],
    }


def add_liquidation_event(symbol: str, side: str, quantity: float, price: float) -> None:
    """Store a liquidation event from WebSocket feed."""
    event = {
        "symbol": symbol,
        "side": side,
        "quantity": quantity,
        "price": price,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "clustered_price": _round_to_significant_level(price),
    }
    events = _liquidation_events[symbol]
    events.append(event)
    if len(events) > _MAX_EVENTS:
        _liquidation_events[symbol] = events[-_MAX_EVENTS:]


def get_liquidation_clusters(symbol: str) -> List[Dict]:
    """Build liquidation clusters from recorded events."""
    events = _liquidation_events.get(symbol, [])
    clusters: Dict[float, Dict] = defaultdict(lambda: {
        "price": 0.0, "long_count": 0, "short_count": 0,
        "long_volume": 0.0, "short_volume": 0.0
    })

    for ev in events:
        key = ev["clustered_price"]
        clusters[key]["price"] = key
        if ev["side"] == "SELL":  # SELL = long liquidated
            clusters[key]["long_count"] += 1
            clusters[key]["long_volume"] += ev["quantity"] * ev["price"]
        else:
            clusters[key]["short_count"] += 1
            clusters[key]["short_volume"] += ev["quantity"] * ev["price"]

    result = []
    for data in clusters.values():
        total_vol = data["long_volume"] + data["short_volume"]
        result.append({
            **data,
            "total_volume": round(total_vol, 2),
        })

    return sorted(result, key=lambda x: x["total_volume"], reverse=True)


class LiquidationEngine:
    """Main liquidation heatmap engine."""

    async def get_heatmap(self, symbol: str) -> Dict:
        """
        Get full liquidation heatmap for a symbol.
        Combines estimated zones from OI data + real recorded events.
        """
        try:
            price = await binance_client.get_price(symbol)
            if price <= 0:
                return {"symbol": symbol, "error": "Price unavailable"}

            oi_data = await binance_client.get_open_interest(symbol)
            open_interest = float(oi_data.get("open_interest", 0))

            # Estimated zones based on OI
            zones = estimate_liquidation_zones(price, open_interest)

            # Real event clusters (if any)
            clusters = get_liquidation_clusters(symbol)

            # Merge clusters into zones
            for cluster in clusters:
                clustered_price = _round_to_significant_level(cluster["price"])
                for zone in zones:
                    if abs(zone["price"] - clustered_price) / max(clustered_price, 1) < 0.005:
                        zone["long_liquidation_value"] += cluster["long_volume"]
                        zone["short_liquidation_value"] += cluster["short_volume"]
                        zone["total_liquidation_value"] += cluster["total_volume"]
                        break

            # Find magnet
            magnet = find_liquidation_magnet(zones, price)

            return {
                "symbol": symbol,
                "current_price": price,
                "open_interest": open_interest,
                "heatmap_zones": zones,
                "liquidation_magnet": magnet,
                "real_events_count": len(_liquidation_events.get(symbol, [])),
            }
        except Exception as e:
            logger.error(f"LiquidationEngine.get_heatmap error for {symbol}: {e}")
            return {"symbol": symbol, "error": str(e), "heatmap_zones": [], "liquidation_magnet": None}


liquidation_engine = LiquidationEngine()

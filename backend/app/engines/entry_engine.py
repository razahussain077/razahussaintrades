"""
Smart Entry System — Feature 3
Calculates scale-in / DCA entry zones at confirmed SMC levels.
"""
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def calculate_entry_zones(
    signal_type: str,
    key_level_top: float,
    key_level_bottom: float,
    current_price: float,
) -> List[Dict]:
    """
    Calculate 3 entry levels within an Order Block or FVG zone.

    For LONG:
      Entry 1 (30%): First touch of the key level (top of OB / bottom of FVG)
      Entry 2 (40%): OB midpoint or FVG 50% fill
      Entry 3 (30%): Extreme of zone (OB bottom / FVG bottom)

    For SHORT:
      Entry 1 (30%): First touch of key level (bottom of OB / top of FVG)
      Entry 2 (40%): OB midpoint
      Entry 3 (30%): OB top / FVG top (extreme)
    """
    if key_level_top <= 0 or key_level_bottom <= 0:
        return []

    zone_mid = (key_level_top + key_level_bottom) / 2
    zone_size = key_level_top - key_level_bottom

    if signal_type == "LONG":
        # Entry from top of zone downward
        entry_1 = key_level_top  # First touch
        entry_2 = zone_mid       # Midpoint (deeper)
        entry_3 = key_level_bottom  # Extreme bottom
    else:
        # SHORT: entry from bottom of zone upward
        entry_1 = key_level_bottom  # First touch
        entry_2 = zone_mid           # Midpoint (deeper)
        entry_3 = key_level_top      # Extreme top

    entries = [
        {
            "level_name": "Entry 1 — Zone Touch",
            "price": round(entry_1, 8),
            "allocation_pct": 30,
            "description": "First touch of key level — initial position",
        },
        {
            "level_name": "Entry 2 — Zone Midpoint",
            "price": round(entry_2, 8),
            "allocation_pct": 40,
            "description": "OB midpoint or FVG 50% fill — add to position",
        },
        {
            "level_name": "Entry 3 — Zone Extreme",
            "price": round(entry_3, 8),
            "allocation_pct": 30,
            "description": "Extreme of zone — final add (max risk)",
        },
    ]

    return entries


def calculate_weighted_average_entry(entries: List[Dict]) -> float:
    """Calculate the weighted average entry price based on allocation percentages."""
    if not entries:
        return 0.0

    total_weight = sum(e["allocation_pct"] for e in entries)
    if total_weight == 0:
        return 0.0

    weighted_sum = sum(e["price"] * e["allocation_pct"] for e in entries)
    return round(weighted_sum / total_weight, 8)


def validate_entry_zone(
    entries: List[Dict],
    stop_loss: float,
    signal_type: str,
) -> bool:
    """
    Validate that Entry 3 is still within acceptable distance from SL.
    If Entry 3 is past the SL zone, signal is invalidated.
    """
    if not entries:
        return False

    extreme_entry = entries[2]["price"]  # Entry 3

    if signal_type == "LONG":
        # Entry 3 must be above stop loss
        return extreme_entry > stop_loss
    else:
        # Entry 3 must be below stop loss
        return extreme_entry < stop_loss


def build_entry_zone_from_signal(
    signal_type: str,
    smc_result: Dict,
    ict_result: Dict,
    current_price: float,
    stop_loss: float,
) -> Dict:
    """
    Build entry zone from signal analysis results.
    Returns entry zones, weighted average, and validity flag.
    """
    # Try to get OB or FVG zone
    zone_top = 0.0
    zone_bottom = 0.0
    zone_source = "price_based"

    if signal_type == "LONG":
        ob = smc_result.get("nearest_bullish_ob") or {}
        ote = ict_result.get("ote") or {}
        if ob:
            zone_top = ob.get("top", 0) or ob.get("high", 0)
            zone_bottom = ob.get("bottom", 0) or ob.get("low", 0)
            zone_source = "bullish_ob"
        elif ote and ote.get("in_ote_zone"):
            zone_top = ote.get("ote_zone_high", 0)
            zone_bottom = ote.get("ote_zone_low", 0)
            zone_source = "ict_ote"
    else:
        ob = smc_result.get("nearest_bearish_ob") or {}
        ote = ict_result.get("ote") or {}
        if ob:
            zone_top = ob.get("top", 0) or ob.get("high", 0)
            zone_bottom = ob.get("bottom", 0) or ob.get("low", 0)
            zone_source = "bearish_ob"
        elif ote and ote.get("in_ote_zone"):
            zone_top = ote.get("ote_zone_high", 0)
            zone_bottom = ote.get("ote_zone_low", 0)
            zone_source = "ict_ote"

    # Fallback: use price-based zone (0.5% range)
    if zone_top <= 0 or zone_bottom <= 0 or zone_top <= zone_bottom:
        spread = current_price * 0.005
        if signal_type == "LONG":
            zone_top = current_price
            zone_bottom = current_price - spread
        else:
            zone_top = current_price + spread
            zone_bottom = current_price
        zone_source = "price_based"

    entries = calculate_entry_zones(signal_type, zone_top, zone_bottom, current_price)
    weighted_avg = calculate_weighted_average_entry(entries)
    valid = validate_entry_zone(entries, stop_loss, signal_type)

    return {
        "entries": entries,
        "weighted_average_entry": weighted_avg,
        "zone_top": round(zone_top, 8),
        "zone_bottom": round(zone_bottom, 8),
        "zone_source": zone_source,
        "is_valid": valid,
        "invalidation_note": (
            None if valid
            else f"Entry 3 beyond stop loss zone — signal invalidated, NO further entries"
        ),
    }


class EntryEngine:
    """Smart entry / scale-in engine."""

    def calculate(
        self,
        signal_type: str,
        smc_result: Dict,
        ict_result: Dict,
        current_price: float,
        stop_loss: float,
    ) -> Dict:
        """Calculate smart entry zones for a signal."""
        try:
            return build_entry_zone_from_signal(
                signal_type, smc_result, ict_result, current_price, stop_loss
            )
        except Exception as e:
            logger.error(f"EntryEngine.calculate error: {e}")
            return {
                "entries": [],
                "weighted_average_entry": current_price,
                "is_valid": False,
                "error": str(e),
            }


entry_engine = EntryEngine()

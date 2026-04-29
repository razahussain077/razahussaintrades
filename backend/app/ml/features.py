"""
Feature extraction for the ML signal-confidence model.

Extends the original 9-feature toy schema with order-flow features (CVD,
large prints, divergence) gated on availability so historical samples without
order-flow data still train without leaking NaN.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Order matters — must stay in sync with FEATURE_NAMES.
FEATURE_NAMES: List[str] = [
    "engine_confluence",      # 0  rule-based reasons fired
    "funding_boost",          # 1  bps boost from funding rate
    "oi_change_pct",          # 2  open-interest %∆ over recent window
    "volume_relative",        # 3  volume / sma20(volume)
    "regime",                 # 4  0=ranging 1=trending 2=volatile 3=squeeze
    "kill_zone_active",       # 5  0/1
    "htf_aligned",            # 6  0/1 — htf bias matches signal direction
    "hour_pkt",               # 7  0-23 hour in PKT
    "day_of_week",            # 8  0-6 (Monday=0)
    # New in PR4 — order flow.
    "of_have_data",           # 9  0/1 — was order-flow snapshot populated?
    "of_delta_1m_norm",       # 10 normalized 1m delta in [-1, +1]
    "of_cvd_5m",              # 11 raw 5-minute CVD ($)
    "of_large_buy_count",     # 12 # large aggressive buys, 1m
    "of_large_sell_count",    # 13 # large aggressive sells, 1m
    "of_bullish_divergence",  # 14 0/1
    "of_bearish_divergence",  # 15 0/1
    # Higher-order context.
    "atr_pct",                # 16 ATR / price (normalized vol)
    "rr_gross",               # 17 gross reward:risk
    "rr_net",                 # 18 cost-adjusted reward:risk
]

NUM_FEATURES = len(FEATURE_NAMES)

_REGIME_MAP = {"ranging": 0, "trending": 1, "volatile": 2, "squeeze": 3}


def extract_features(signal_data: Dict) -> Optional[List[float]]:
    """Return a fixed-length feature vector or None on failure."""
    try:
        reasoning = signal_data.get("reasoning") or []
        engine_count = float(min(len(reasoning), 6))

        funding_boost = float(signal_data.get("funding_boost", 0) or 0)
        oi_change = float(signal_data.get("oi_change_pct", 0) or 0)
        volume_relative = float(signal_data.get("volume_relative", 1.0) or 1.0)
        regime = float(_REGIME_MAP.get(signal_data.get("regime", "ranging"), 0))

        kill_zone = signal_data.get("kill_zone", "Off Hours")
        kill_zone_active = 0.0 if kill_zone in ("Off Hours", None, "") else 1.0

        htf_aligned = 1.0 if float(signal_data.get("confidence_score", 0) or 0) >= 75 else 0.0

        # Time features
        created_at = signal_data.get("created_at") or ""
        hour, dow = 0.0, 0.0
        if created_at:
            try:
                dt = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
                pkt_dt = dt + timedelta(hours=5)
                hour = float(pkt_dt.hour)
                dow = float(pkt_dt.weekday())
            except Exception:
                pass

        of = signal_data.get("orderflow_result") or {}
        of_have_data = 1.0 if of.get("have_data") else 0.0
        of_delta = float(of.get("delta_1m_normalized", 0) or 0)
        of_cvd_5m = float(of.get("cvd_5m", 0) or 0)
        of_lbc = float(of.get("large_buy_count", 0) or 0)
        of_lsc = float(of.get("large_sell_count", 0) or 0)
        of_bull = 1.0 if of.get("bullish_divergence") else 0.0
        of_bear = 1.0 if of.get("bearish_divergence") else 0.0

        atr_pct = float(signal_data.get("atr_pct", 0) or 0)
        rr_gross = float(signal_data.get("rr_gross", 0) or 0)
        rr_net = float(signal_data.get("rr_net", rr_gross) or 0)

        out = [
            engine_count, funding_boost, oi_change, volume_relative, regime,
            kill_zone_active, htf_aligned, hour, dow,
            of_have_data, of_delta, of_cvd_5m, of_lbc, of_lsc, of_bull, of_bear,
            atr_pct, rr_gross, rr_net,
        ]
        if len(out) != NUM_FEATURES:
            logger.error("feature length mismatch: %d != %d", len(out), NUM_FEATURES)
            return None
        return out
    except Exception as e:
        logger.error("extract_features error: %s", e)
        return None

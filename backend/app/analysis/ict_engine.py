import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
import pytz

from app.config import settings

logger = logging.getLogger(__name__)
PKT = pytz.timezone(settings.PKT_TIMEZONE)


def _highs(candles: List[Dict]) -> np.ndarray:
    return np.array([c["high"] for c in candles], dtype=float)


def _lows(candles: List[Dict]) -> np.ndarray:
    return np.array([c["low"] for c in candles], dtype=float)


def _closes(candles: List[Dict]) -> np.ndarray:
    return np.array([c["close"] for c in candles], dtype=float)


def _opens(candles: List[Dict]) -> np.ndarray:
    return np.array([c["open"] for c in candles], dtype=float)


def get_kill_zones() -> Dict:
    """
    Return current active session and next session with PKT times.
    Sessions in UTC:
      Asian:       00:00 - 09:00 (PKT 05:00 - 14:00)
      London:      08:00 - 12:00 (PKT 13:00 - 17:00)
      New York:    13:00 - 18:00 (PKT 18:00 - 23:00)
      London Close: 17:00 - 19:00 (PKT 22:00 - 00:00)
    """
    now_utc = datetime.now(timezone.utc)
    now_pkt = now_utc.astimezone(PKT)
    hour_utc = now_utc.hour

    sessions = [
        {"name": "Asian", "utc_start": 0, "utc_end": 9, "pkt_start": 5, "pkt_end": 14},
        {"name": "London", "utc_start": 8, "utc_end": 12, "pkt_start": 13, "pkt_end": 17},
        {"name": "New York", "utc_start": 13, "utc_end": 18, "pkt_start": 18, "pkt_end": 23},
        {"name": "London Close", "utc_start": 17, "utc_end": 19, "pkt_start": 22, "pkt_end": 24},
    ]

    active_session = None
    for s in sessions:
        if s["utc_start"] <= hour_utc < s["utc_end"]:
            active_session = s
            break

    # Next session
    next_session = None
    if active_session:
        idx = sessions.index(active_session)
        next_session = sessions[(idx + 1) % len(sessions)]
    else:
        # Find the next upcoming session
        for s in sessions:
            if s["utc_start"] > hour_utc:
                next_session = s
                break
        if not next_session:
            next_session = sessions[0]

    # Is it a kill zone? (high-probability trading window)
    is_kill_zone = active_session is not None and active_session["name"] in ["London", "New York"]

    return {
        "current_utc_hour": hour_utc,
        "current_pkt_time": now_pkt.strftime("%H:%M PKT"),
        "active_session": active_session["name"] if active_session else "Off Hours",
        "active_session_pkt": (
            f"{active_session['pkt_start']:02d}:00 - {active_session['pkt_end']:02d}:00 PKT"
            if active_session else "N/A"
        ),
        "next_session": next_session["name"] if next_session else None,
        "next_session_pkt": (
            f"{next_session['pkt_start']:02d}:00 - {next_session['pkt_end']:02d}:00 PKT"
            if next_session else None
        ),
        "is_kill_zone": is_kill_zone,
        "sessions": sessions,
    }


def detect_ote(candles: List[Dict]) -> Optional[Dict]:
    """
    Optimal Trade Entry (OTE) at 61.8%-78.6% Fibonacci retracement of last impulse.
    Find the last significant swing, then compute fib levels.
    """
    if len(candles) < 20:
        return None

    highs = _highs(candles)
    lows = _lows(candles)
    closes = _closes(candles)

    # Find swing high and swing low in recent candles
    recent = 30
    window_highs = highs[-recent:]
    window_lows = lows[-recent:]

    swing_high_idx = int(np.argmax(window_highs))
    swing_low_idx = int(np.argmin(window_lows))
    swing_high = float(window_highs[swing_high_idx])
    swing_low = float(window_lows[swing_low_idx])

    current_price = float(closes[-1])
    range_size = swing_high - swing_low
    if range_size == 0:
        return None

    # Determine direction of last impulse
    if swing_low_idx > swing_high_idx:
        # Impulse down (bearish): OTE for short
        fib_50 = swing_high - 0.5 * range_size
        fib_618 = swing_high - 0.618 * range_size
        fib_786 = swing_high - 0.786 * range_size
        ote_high = swing_high - 0.618 * range_size
        ote_low = swing_high - 0.786 * range_size
        direction = "bearish"
        in_ote = ote_low <= current_price <= ote_high
    else:
        # Impulse up (bullish): OTE for long
        fib_50 = swing_low + 0.5 * range_size
        fib_618 = swing_low + 0.618 * range_size
        fib_786 = swing_low + 0.786 * range_size
        ote_low = swing_low + 0.618 * range_size
        ote_high = swing_low + 0.786 * range_size
        direction = "bullish"
        in_ote = ote_low <= current_price <= ote_high

    return {
        "direction": direction,
        "swing_high": swing_high,
        "swing_low": swing_low,
        "fib_50": round(fib_50, 6),
        "fib_618": round(fib_618, 6),
        "fib_786": round(fib_786, 6),
        "ote_zone_high": round(ote_high, 6),
        "ote_zone_low": round(ote_low, 6),
        "current_price": current_price,
        "in_ote_zone": in_ote,
    }


def detect_judas_swing(candles: List[Dict], session_open: Optional[float] = None) -> Optional[Dict]:
    """
    Judas Swing: fake pump/dump at session open.
    Price exceeds prior session range then quickly reverses.
    """
    if len(candles) < 10:
        return None

    highs = _highs(candles)
    lows = _lows(candles)
    closes = _closes(candles)

    # Use last 10 candles as session reference
    prior_range_high = float(np.max(highs[-10:-1]))
    prior_range_low = float(np.min(lows[-10:-1]))
    current_high = float(highs[-1])
    current_low = float(lows[-1])
    current_close = float(closes[-1])

    judas_detected = False
    direction = None

    # Bearish Judas: price exceeds high then closes back below
    if current_high > prior_range_high and current_close < prior_range_high:
        judas_detected = True
        direction = "bearish"

    # Bullish Judas: price dips below low then closes back above
    elif current_low < prior_range_low and current_close > prior_range_low:
        judas_detected = True
        direction = "bullish"

    if not judas_detected:
        return None

    return {
        "detected": True,
        "direction": direction,
        "prior_range_high": prior_range_high,
        "prior_range_low": prior_range_low,
        "sweep_level": current_high if direction == "bearish" else current_low,
        "close": current_close,
        "description": (
            f"{'Bearish' if direction == 'bearish' else 'Bullish'} Judas Swing detected: "
            f"price swept {'above' if direction == 'bearish' else 'below'} range then reversed"
        ),
    }


def detect_silver_bullet(candles: List[Dict]) -> Optional[Dict]:
    """
    ICT Silver Bullet: NY 10-11 AM or 2-3 PM session FVG pattern.
    Looks for a FVG formed during specific time windows.
    We detect based on current session timing + FVG presence.
    """
    if len(candles) < 5:
        return None

    now_utc = datetime.now(timezone.utc)
    hour_utc = now_utc.hour

    # Silver bullet windows: 10-11 AM NY (15:00-16:00 UTC), 2-3 PM NY (19:00-20:00 UTC)
    in_silver_bullet_window = hour_utc in (15, 16, 19, 20)
    window_name = None
    if hour_utc in (15, 16):
        window_name = "NY 10-11 AM (15:00-16:00 UTC)"
    elif hour_utc in (19, 20):
        window_name = "NY 2-3 PM (19:00-20:00 UTC)"

    if not in_silver_bullet_window:
        return None

    highs = _highs(candles)
    lows = _lows(candles)
    closes = _closes(candles)

    # Look for FVG in last 3 candles
    for i in range(max(0, len(candles) - 5), len(candles) - 2):
        # Bullish FVG
        if highs[i] < lows[i + 2]:
            return {
                "detected": True,
                "type": "bullish",
                "window": window_name,
                "fvg_bottom": float(highs[i]),
                "fvg_top": float(lows[i + 2]),
                "description": f"ICT Silver Bullet bullish FVG in {window_name}",
            }
        # Bearish FVG
        if lows[i] > highs[i + 2]:
            return {
                "detected": True,
                "type": "bearish",
                "window": window_name,
                "fvg_bottom": float(highs[i + 2]),
                "fvg_top": float(lows[i]),
                "description": f"ICT Silver Bullet bearish FVG in {window_name}",
            }

    return None


def detect_power_of_3(candles: List[Dict]) -> Dict:
    """
    AMD Pattern: Accumulation, Manipulation (Judas swing), Distribution.
    Looks for sideways range -> spike -> directional move.
    """
    if len(candles) < 30:
        return {"detected": False}

    closes = _closes(candles)
    highs = _highs(candles)
    lows = _lows(candles)

    # Phase 1: Accumulation (first third - low volatility range)
    acc_window = candles[: len(candles) // 3]
    acc_highs = _highs(acc_window)
    acc_lows = _lows(acc_window)
    acc_range = float(np.max(acc_highs) - np.min(acc_lows))
    acc_avg = float(np.mean(closes[: len(candles) // 3]))

    # Phase 2: Manipulation (middle - spike beyond range)
    man_window = candles[len(candles) // 3: 2 * len(candles) // 3]
    man_highs = _highs(man_window)
    man_lows = _lows(man_window)
    man_high = float(np.max(man_highs))
    man_low = float(np.min(man_lows))

    acc_range_high = float(np.max(acc_highs))
    acc_range_low = float(np.min(acc_lows))

    # Manipulation spike detected if price exceeds accumulation range by 0.3%
    bull_manipulation = man_low < acc_range_low * (1 - 0.003)
    bear_manipulation = man_high > acc_range_high * (1 + 0.003)

    # Phase 3: Distribution (last third - directional move)
    dist_window = candles[2 * len(candles) // 3:]
    dist_close = float(closes[-1])

    phase = "accumulation"
    direction = "neutral"
    if bull_manipulation and dist_close > acc_avg:
        phase = "distribution"
        direction = "bullish"
    elif bear_manipulation and dist_close < acc_avg:
        phase = "distribution"
        direction = "bearish"
    elif bull_manipulation or bear_manipulation:
        phase = "manipulation"
        direction = "bullish" if bull_manipulation else "bearish"

    return {
        "detected": phase in ("manipulation", "distribution"),
        "phase": phase,
        "direction": direction,
        "accumulation_range": {"high": acc_range_high, "low": acc_range_low, "range": acc_range},
        "manipulation_high": man_high,
        "manipulation_low": man_low,
        "distribution_close": dist_close,
    }


def detect_institutional_candle(candles: List[Dict]) -> Optional[Dict]:
    """
    Large body candle with >70% body-to-range ratio and volume spike.
    """
    if len(candles) < 21:
        return None

    opens = _opens(candles)
    closes = _closes(candles)
    highs = _highs(candles)
    lows = _lows(candles)
    volumes = np.array([c.get("volume", 0) for c in candles], dtype=float)
    avg_volume = float(np.mean(volumes[-20:-1])) if len(volumes) > 20 else float(np.mean(volumes))

    last_idx = len(candles) - 1
    body = abs(closes[last_idx] - opens[last_idx])
    candle_range = highs[last_idx] - lows[last_idx]

    if candle_range == 0:
        return None

    body_ratio = body / candle_range
    volume = float(volumes[last_idx])
    volume_spike = volume / avg_volume if avg_volume > 0 else 1.0

    if body_ratio >= 0.7 and volume_spike >= 1.5:
        direction = "bullish" if closes[last_idx] > opens[last_idx] else "bearish"
        return {
            "detected": True,
            "direction": direction,
            "body_ratio": round(body_ratio * 100, 1),
            "volume_spike": round(volume_spike, 2),
            "open": float(opens[last_idx]),
            "close": float(closes[last_idx]),
            "high": float(highs[last_idx]),
            "low": float(lows[last_idx]),
        }
    return None


class ICTEngine:
    def analyze(self, candles: List[Dict]) -> Dict:
        if len(candles) < 20:
            return {"error": "Insufficient candle data"}
        try:
            kill_zones = get_kill_zones()
            ote = detect_ote(candles)
            judas = detect_judas_swing(candles)
            silver_bullet = detect_silver_bullet(candles)
            power_of_3 = detect_power_of_3(candles)
            inst_candle = detect_institutional_candle(candles)

            return {
                "kill_zones": kill_zones,
                "ote": ote,
                "judas_swing": judas,
                "silver_bullet": silver_bullet,
                "power_of_3": power_of_3,
                "institutional_candle": inst_candle,
                "is_kill_zone": kill_zones.get("is_kill_zone", False),
                "active_session": kill_zones.get("active_session", "Off Hours"),
            }
        except Exception as e:
            logger.error(f"ICT analyze error: {e}")
            return {"error": str(e)}


ict_engine = ICTEngine()

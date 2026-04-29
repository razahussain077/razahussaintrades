"""
Walk-Forward Backtest Harness.

Slides a non-overlapping window of N days across a longer history (default
6 months) for one or more symbols, runs the existing backtest engine on each
window in isolation, and aggregates per-window stats so you can SEE whether
edge is consistent across regimes — not just averaged over a single window
where one trending leg can mask flat-or-losing performance everywhere else.

This module is intentionally light: it reuses `backtest_engine.run_backtest`
unchanged, just feeds it candle slices instead of letting it fetch its own.

Output shape:

    {
      "symbol": "BTCUSDT",
      "timeframe": "1h",
      "window_days": 30,
      "history_days": 180,
      "windows": [
          {"start_ts": ..., "end_ts": ..., "stats": { ... } },
          ...
      ],
      "aggregate": {
          "total_signals": ...,
          "win_rate": ...,
          "avg_R_multiple": ...,
          "ending_balance": ...,
          "consistency_score": 0..1   # fraction of windows with PF >= 1.0
      },
      "equity_curve": [...]            # concatenated across windows
    }
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from app.config import settings
from app.engines.backtest_engine import run_backtest, _bar_minutes  # noqa: PLC2701
from app.exchanges.binance_client import binance_client

logger = logging.getLogger(__name__)


# Binance public klines endpoint caps at 1500 per request. For deeper history
# we page by reducing limit / using the full 1500 windows; for typical
# walk-forward runs (180 days × 1h = 4320 candles) we must page.
_KLINE_PAGE_LIMIT = 1500


async def _fetch_history(
    symbol: str,
    timeframe: str,
    days: int,
) -> List[Dict]:
    """Fetch up to `days` of historical candles, paging through Binance if needed."""
    bar_min = _bar_minutes(timeframe)
    bars_needed = days * 24 * 60 // bar_min
    if bars_needed <= _KLINE_PAGE_LIMIT:
        return await binance_client.get_klines(symbol, timeframe, bars_needed)

    # Multi-page fetch — reuse the public klines endpoint.
    # We don't currently have a paged variant on `binance_client`; for now,
    # cap at the single-page limit and warn. PR 4 will add proper pagination
    # for the ML training data pipeline.
    logger.warning(
        "walkforward: history exceeds single-page kline limit (need %d, got %d). "
        "Capping to %d candles. Add pagination in binance_client for deeper runs.",
        bars_needed, _KLINE_PAGE_LIMIT, _KLINE_PAGE_LIMIT,
    )
    return await binance_client.get_klines(symbol, timeframe, _KLINE_PAGE_LIMIT)


def _slice_windows(
    candles: List[Dict],
    bars_per_window: int,
) -> List[List[Dict]]:
    if bars_per_window <= 0 or len(candles) < bars_per_window:
        return []
    out: List[List[Dict]] = []
    for start in range(0, len(candles) - bars_per_window + 1, bars_per_window):
        out.append(candles[start:start + bars_per_window])
    return out


def _aggregate(
    per_window: List[Dict],
    starting_balance: float,
) -> Dict:
    """Combine per-window stats into a single aggregate report."""
    if not per_window:
        return {
            "total_signals": 0,
            "win_rate": 0,
            "avg_R_multiple": 0,
            "profit_factor": 0,
            "max_drawdown_pct": 0,
            "starting_balance": round(starting_balance, 2),
            "ending_balance": round(starting_balance, 2),
            "consistency_score": 0.0,
            "window_count": 0,
        }

    total_signals = sum(w["stats"]["total_signals"] for w in per_window)
    total_wins = sum(w["stats"]["win_count"] for w in per_window)
    win_rate = total_wins / total_signals * 100 if total_signals > 0 else 0

    # Compound the ending balances across windows.
    balance = starting_balance
    equity_curve: List[float] = [round(balance, 2)]
    drawdowns: List[float] = []
    profitable_windows = 0

    for w in per_window:
        s = w["stats"]
        # Use total_pnl_pct (account-%) so we compound correctly across windows.
        pnl_pct = s.get("total_pnl_pct", 0.0)
        balance = balance * (1.0 + pnl_pct / 100.0)
        equity_curve.append(round(balance, 2))
        drawdowns.append(s.get("max_drawdown_pct", 0.0))
        # A window is "profitable" iff total account-% PnL is positive.
        # (Profit factor >= 1 is equivalent when computed from the same trades.)
        if pnl_pct > 0:
            profitable_windows += 1

    consistency_score = (
        profitable_windows / len(per_window) if per_window else 0.0
    )

    avg_R = (
        sum(w["stats"].get("avg_R_multiple", 0) * w["stats"].get("total_signals", 0)
            for w in per_window) / total_signals
        if total_signals > 0 else 0.0
    )

    # Aggregate profit factor across all windows' gross_profit / gross_loss
    # would require summing per-trade lists; approximate by averaging window PFs
    # weighted by trade count.
    weighted_pf = (
        sum(min(w["stats"].get("profit_factor", 0), 999) * w["stats"].get("total_signals", 0)
            for w in per_window) / total_signals
        if total_signals > 0 else 0.0
    )

    return {
        "total_signals": total_signals,
        "win_count": total_wins,
        "loss_count": total_signals - total_wins,
        "win_rate": round(win_rate, 1),
        "avg_R_multiple": round(avg_R, 3),
        "profit_factor": round(weighted_pf, 2),
        "max_drawdown_pct": round(max(drawdowns) if drawdowns else 0.0, 2),
        "starting_balance": round(starting_balance, 2),
        "ending_balance": round(balance, 2),
        "total_return_pct": round((balance / starting_balance - 1) * 100, 2),
        "consistency_score": round(consistency_score, 3),
        "window_count": len(per_window),
        "equity_curve": equity_curve,
    }


async def run_walkforward(
    symbol: str,
    timeframe: str = "1h",
    history_days: int = 180,
    window_days: int = 30,
    *,
    starting_balance: float = 1000.0,
    risk_per_trade_pct: Optional[float] = None,
    include_costs: Optional[bool] = None,
    fee_bps_per_side: Optional[float] = None,
    funding_rate_per_period: Optional[float] = None,
) -> Dict:
    """
    Run a walk-forward backtest over `history_days` of history, in
    non-overlapping `window_days` slices. Returns per-window stats plus a
    cross-window aggregate including a `consistency_score` (fraction of
    windows that were profitable).
    """
    if window_days <= 0 or history_days <= 0:
        return {"error": "history_days and window_days must be positive"}
    if window_days > history_days:
        return {"error": "window_days cannot exceed history_days"}

    candles = await _fetch_history(symbol, timeframe, history_days)
    if not candles:
        return {"error": f"No candles available for {symbol}"}

    bars_per_window = window_days * 24 * 60 // _bar_minutes(timeframe)
    windows = _slice_windows(candles, bars_per_window)
    if not windows:
        return {
            "error": f"Not enough history: have {len(candles)} bars, "
                     f"need {bars_per_window} per window"
        }

    per_window: List[Dict] = []
    for slice_candles in windows:
        result = await run_backtest(
            symbol=symbol,
            timeframe=timeframe,
            days=window_days,
            starting_balance=starting_balance,
            risk_per_trade_pct=risk_per_trade_pct,
            include_costs=include_costs,
            fee_bps_per_side=fee_bps_per_side,
            funding_rate_per_period=funding_rate_per_period,
            candles=slice_candles,
        )
        if result.get("error"):
            logger.debug("walkforward: window skipped (%s)", result["error"])
            continue
        per_window.append({
            "start_ts": slice_candles[0]["timestamp"],
            "end_ts": slice_candles[-1]["timestamp"],
            "stats": result["stats"],
            "trade_count": len(result.get("trades", [])),
        })

    aggregate = _aggregate(per_window, starting_balance)

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "history_days": history_days,
        "window_days": window_days,
        "include_costs": (
            include_costs
            if include_costs is not None
            else settings.BACKTEST_INCLUDE_COSTS
        ),
        "windows": per_window,
        "aggregate": aggregate,
    }


class WalkForwardEngine:
    """Thin OO handle for callers that prefer dependency-injection style."""

    async def run(self, *args, **kwargs) -> Dict:
        return await run_walkforward(*args, **kwargs)


walkforward_engine = WalkForwardEngine()

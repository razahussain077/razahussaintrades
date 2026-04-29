"""
Backtesting Engine — Feature 6
Runs historical analysis and tracks signal performance.
Paper trading mode also supported.

History note: prior to the foundation-fixes refactor this module had two
math bugs that made every reported equity curve essentially flat (PnL was
scaled by 1/10,000 instead of by the intended risk-per-trade fraction) and
double-negated PnL on SHORT-side stop-out paths. Both are fixed here. The
realized account return per trade is now computed via the canonical
fixed-fractional risk model in `fees_engine.compute_trade_costs`, which also
deducts round-trip exchange fees and funding cost when `include_costs=True`.
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

import numpy as np

from app.config import settings
from app.engines.fees_engine import (
    TradeCostInputs,
    compute_trade_costs,
)
from app.exchanges.binance_client import binance_client

logger = logging.getLogger(__name__)

# In-memory stores
_backtest_results: Optional[Dict] = None
_paper_trading: Dict = {
    "active": False,
    "starting_balance": 1000.0,
    "current_balance": 1000.0,
    "trades": [],
    "equity_curve": [],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_INTERVAL_TO_MINUTES = {
    "1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30,
    "1h": 60, "2h": 120, "4h": 240, "6h": 360, "8h": 480, "12h": 720,
    "1d": 1440, "3d": 4320, "1w": 10080,
}


def _bar_minutes(timeframe: str) -> int:
    return _INTERVAL_TO_MINUTES.get(timeframe.lower(), 60)


def _simulate_trade_outcome(
    signal_type: str,
    entry_price: float,
    stop_loss: float,
    tp1: float,
    tp2: float,
    tp3: float,
    future_candles: List[Dict],
) -> Dict:
    """
    Simulate trade outcome given future price candles.
    Returns: hit level (TP1/TP2/TP3/SL/EXPIRED), exit price, gross pnl_pct, bars_held.

    pnl_pct here is the *price-percent* signed move from entry to exit (NOT
    account-percent). Account-percent translation happens later in
    `_build_trade_record` so the price-space outcome is reusable.
    """
    side = signal_type.upper()

    for i, candle in enumerate(future_candles):
        high = candle["high"]
        low = candle["low"]

        if side == "LONG":
            if low <= stop_loss:
                pnl_pct = (stop_loss - entry_price) / entry_price * 100
                return {"result": "SL", "exit_price": stop_loss, "pnl_pct": round(pnl_pct, 4), "bars_held": i + 1}
            if high >= tp3:
                pnl_pct = (tp3 - entry_price) / entry_price * 100
                return {"result": "TP3", "exit_price": tp3, "pnl_pct": round(pnl_pct, 4), "bars_held": i + 1}
            if high >= tp2:
                pnl_pct = (tp2 - entry_price) / entry_price * 100
                return {"result": "TP2", "exit_price": tp2, "pnl_pct": round(pnl_pct, 4), "bars_held": i + 1}
            if high >= tp1:
                pnl_pct = (tp1 - entry_price) / entry_price * 100
                return {"result": "TP1", "exit_price": tp1, "pnl_pct": round(pnl_pct, 4), "bars_held": i + 1}
        else:  # SHORT
            if high >= stop_loss:
                # SL above entry on a SHORT = a loss; pnl in price-% space is negative.
                pnl_pct = (entry_price - stop_loss) / entry_price * 100
                return {"result": "SL", "exit_price": stop_loss, "pnl_pct": round(pnl_pct, 4), "bars_held": i + 1}
            if low <= tp3:
                pnl_pct = (entry_price - tp3) / entry_price * 100
                return {"result": "TP3", "exit_price": tp3, "pnl_pct": round(pnl_pct, 4), "bars_held": i + 1}
            if low <= tp2:
                pnl_pct = (entry_price - tp2) / entry_price * 100
                return {"result": "TP2", "exit_price": tp2, "pnl_pct": round(pnl_pct, 4), "bars_held": i + 1}
            if low <= tp1:
                pnl_pct = (entry_price - tp1) / entry_price * 100
                return {"result": "TP1", "exit_price": tp1, "pnl_pct": round(pnl_pct, 4), "bars_held": i + 1}

    # Expired
    last_price = future_candles[-1]["close"] if future_candles else entry_price
    if side == "LONG":
        pnl_pct = (last_price - entry_price) / entry_price * 100
    else:
        pnl_pct = (entry_price - last_price) / entry_price * 100
    return {"result": "EXPIRED", "exit_price": last_price, "pnl_pct": round(pnl_pct, 4), "bars_held": len(future_candles)}


def _build_trade_record(
    *,
    symbol: str,
    signal_type: str,
    entry_price: float,
    stop_loss: float,
    tp1: float,
    tp2: float,
    tp3: float,
    rr: float,
    candle_index: int,
    timestamp: int,
    outcome: Dict,
    timeframe: str,
    risk_per_trade_pct: float,
    include_costs: bool,
    fee_bps_per_side: float,
    taker_count: int,
    funding_rate_per_period: float,
) -> Dict:
    """Translate a price-space outcome dict into a fully-costed trade record."""
    bars_held = int(outcome.get("bars_held", 0))
    inp = TradeCostInputs(
        entry_price=entry_price,
        exit_price=float(outcome.get("exit_price", entry_price)),
        stop_loss_price=stop_loss,
        side=signal_type,
        bars_held=bars_held,
        bar_minutes=_bar_minutes(timeframe),
        risk_per_trade_pct=risk_per_trade_pct,
        fee_bps_per_side=fee_bps_per_side if include_costs else 0.0,
        taker_count=taker_count,
        funding_rate_per_period=funding_rate_per_period if include_costs else 0.0,
    )
    breakdown = compute_trade_costs(inp)

    return {
        "symbol": symbol,
        "signal_type": signal_type,
        "entry_price": round(entry_price, 8),
        "stop_loss": round(stop_loss, 8),
        "tp1": round(tp1, 8),
        "tp2": round(tp2, 8),
        "tp3": round(tp3, 8),
        "rr": round(rr, 2),
        "candle_index": candle_index,
        "timestamp": timestamp,
        "timeframe": timeframe,
        "result": outcome.get("result"),
        "exit_price": round(float(outcome.get("exit_price", entry_price)), 8),
        # Price-space PnL — kept for backwards compatibility with older callers.
        "pnl_pct": round(float(outcome.get("pnl_pct", 0)), 4),
        "bars_held": bars_held,
        # Account-space PnL — the numbers the equity curve uses.
        "gross_account_pct": round(breakdown.gross_account_pct, 4),
        "fee_drag_account_pct": round(breakdown.fee_drag_account_pct, 4),
        "funding_drag_account_pct": round(breakdown.funding_drag_account_pct, 4),
        "net_account_pct": round(breakdown.net_account_pct, 4),
        "R_multiple": round(breakdown.R_multiple, 3),
        "funding_periods": round(breakdown.funding_periods, 3),
    }


def _calculate_backtest_stats(
    trades: List[Dict],
    starting_balance: float,
    risk_per_trade_pct: float,
) -> Dict:
    """
    Calculate comprehensive backtest statistics on account-level (net) PnL.

    Important fixes vs the previous implementation:
      * Equity curve compounds the *account-level net % return* per trade
        (`net_account_pct`), not the price-% PnL scaled by 1/10,000.
      * Drawdown / Sharpe / final balance reflect realistic risk-of-ruin
        with fees and funding deducted.
    """
    if not trades:
        return {
            "total_signals": 0,
            "win_count": 0,
            "loss_count": 0,
            "win_rate": 0,
            "avg_rr": 0,
            "avg_R_multiple": 0,
            "profit_factor": 0,
            "max_drawdown_pct": 0,
            "best_trade_pct": 0,
            "worst_trade_pct": 0,
            "sharpe_ratio": 0,
            "total_pnl_pct": 0,
            "total_fee_drag_pct": 0,
            "total_funding_drag_pct": 0,
            "starting_balance": round(starting_balance, 2),
            "ending_balance": round(starting_balance, 2),
            "risk_per_trade_pct": risk_per_trade_pct,
            "equity_curve": [round(starting_balance, 2)],
        }

    # Account-level returns (already net of fees + funding for include_costs runs).
    net_returns = [t.get("net_account_pct", 0) for t in trades]
    gross_returns = [t.get("gross_account_pct", 0) for t in trades]
    fee_drags = [t.get("fee_drag_account_pct", 0) for t in trades]
    funding_drags = [t.get("funding_drag_account_pct", 0) for t in trades]

    win_count = sum(1 for t in trades if t.get("result") in ("TP1", "TP2", "TP3"))
    total = len(trades)
    win_rate = win_count / total * 100 if total > 0 else 0

    gross_profit = sum(p for p in net_returns if p > 0)
    gross_loss = abs(sum(p for p in net_returns if p < 0))
    profit_factor = (
        gross_profit / gross_loss if gross_loss > 0
        else (float("inf") if gross_profit > 0 else 0.0)
    )

    avg_rr = float(np.mean([t.get("rr", 0) for t in trades])) if trades else 0
    avg_R = float(np.mean([t.get("R_multiple", 0) for t in trades])) if trades else 0

    # Equity curve: compound the net account-% return.
    balance = starting_balance
    equity_curve = [round(balance, 2)]
    peak = balance
    max_drawdown = 0.0
    for r in net_returns:
        balance = balance * (1.0 + r / 100.0)
        equity_curve.append(round(balance, 2))
        if balance > peak:
            peak = balance
        if peak > 0:
            dd = (peak - balance) / peak * 100
            if dd > max_drawdown:
                max_drawdown = dd

    # Sharpe (annualized assuming 252 sample-days; this is approximate when the
    # trade rate isn't daily, but is the convention this dashboard already used).
    arr = np.array(net_returns)
    sharpe = float(np.mean(arr) / np.std(arr) * np.sqrt(252)) if np.std(arr) > 0 else 0.0

    return {
        "total_signals": total,
        "win_count": win_count,
        "loss_count": total - win_count,
        "win_rate": round(win_rate, 1),
        "avg_rr": round(avg_rr, 2),
        "avg_R_multiple": round(avg_R, 3),
        "profit_factor": round(profit_factor, 2) if profit_factor != float("inf") else 999,
        "max_drawdown_pct": round(max_drawdown, 2),
        "best_trade_pct": round(max(net_returns), 3) if net_returns else 0,
        "worst_trade_pct": round(min(net_returns), 3) if net_returns else 0,
        "sharpe_ratio": round(sharpe, 2),
        "total_pnl_pct": round(sum(net_returns), 3),
        "total_gross_pnl_pct": round(sum(gross_returns), 3),
        "total_fee_drag_pct": round(sum(fee_drags), 3),
        "total_funding_drag_pct": round(sum(funding_drags), 3),
        "starting_balance": round(starting_balance, 2),
        "ending_balance": round(balance, 2),
        "risk_per_trade_pct": risk_per_trade_pct,
        "equity_curve": equity_curve[-200:],  # last 200 points for chart
    }


# ---------------------------------------------------------------------------
# Backtest entry points
# ---------------------------------------------------------------------------

async def run_backtest(
    symbol: str,
    timeframe: str = "1h",
    days: int = 30,
    *,
    starting_balance: float = 1000.0,
    risk_per_trade_pct: Optional[float] = None,
    include_costs: Optional[bool] = None,
    fee_bps_per_side: Optional[float] = None,
    taker_count: int = 2,
    funding_rate_per_period: Optional[float] = None,
    candles: Optional[List[Dict]] = None,
) -> Dict:
    """
    Run a backtest on historical data for one symbol.

    The optional `candles` arg lets the walk-forward harness inject a specific
    historical slice without re-fetching from Binance every time.
    """
    global _backtest_results

    # Resolve config defaults lazily so unit tests can override settings.
    risk_pct = (
        risk_per_trade_pct
        if risk_per_trade_pct is not None
        else settings.BACKTEST_RISK_PER_TRADE_PCT
    )
    inc_costs = (
        include_costs
        if include_costs is not None
        else settings.BACKTEST_INCLUDE_COSTS
    )
    fee_bps = (
        fee_bps_per_side
        if fee_bps_per_side is not None
        else settings.FEE_BPS_TAKER
    )
    funding_rate = (
        funding_rate_per_period
        if funding_rate_per_period is not None
        else settings.BACKTEST_DEFAULT_FUNDING_RATE_PER_8H
    )

    try:
        if candles is None:
            limit = min(
                1500,
                days * (24 * 60 // _bar_minutes(timeframe)),
            )
            candles = await binance_client.get_klines(symbol, timeframe, limit)

        if not candles or len(candles) < 50:
            return {"error": f"Insufficient candles for {symbol}", "symbol": symbol}

        trades: List[Dict] = []
        window = 30
        future_horizon = 20

        for i in range(window, len(candles) - future_horizon):
            segment = candles[i - window:i]
            future = candles[i:i + future_horizon]

            close_prices = [c["close"] for c in segment]
            current_price = close_prices[-1]

            # Simple momentum signal detection (rules unchanged from prior).
            sma_short = float(np.mean(close_prices[-5:]))
            sma_long = float(np.mean(close_prices[-20:]))
            avg_vol = float(np.mean([c["volume"] for c in segment]))
            curr_vol = float(segment[-1]["volume"])
            volume_relative = curr_vol / avg_vol if avg_vol > 0 else 1.0

            signal_type = None
            if sma_short > sma_long * 1.01 and volume_relative > 1.2:
                signal_type = "LONG"
            elif sma_short < sma_long * 0.99 and volume_relative > 1.2:
                signal_type = "SHORT"
            if signal_type is None:
                continue

            # SL/TP from ATR.
            atr = float(np.mean([c["high"] - c["low"] for c in segment[-14:]]))
            if signal_type == "LONG":
                stop_loss = current_price - atr * 1.5
                tp1 = current_price + atr * 1.5
                tp2 = current_price + atr * 2.5
                tp3 = current_price + atr * 4.0
            else:
                stop_loss = current_price + atr * 1.5
                tp1 = current_price - atr * 1.5
                tp2 = current_price - atr * 2.5
                tp3 = current_price - atr * 4.0

            risk_dist = abs(current_price - stop_loss)
            rr = abs(tp2 - current_price) / risk_dist if risk_dist > 0 else 0

            outcome = _simulate_trade_outcome(
                signal_type, current_price, stop_loss, tp1, tp2, tp3, future
            )

            trades.append(_build_trade_record(
                symbol=symbol,
                signal_type=signal_type,
                entry_price=current_price,
                stop_loss=stop_loss,
                tp1=tp1,
                tp2=tp2,
                tp3=tp3,
                rr=rr,
                candle_index=i,
                timestamp=candles[i]["timestamp"],
                outcome=outcome,
                timeframe=timeframe,
                risk_per_trade_pct=risk_pct,
                include_costs=inc_costs,
                fee_bps_per_side=fee_bps,
                taker_count=taker_count,
                funding_rate_per_period=funding_rate,
            ))

        stats = _calculate_backtest_stats(trades, starting_balance, risk_pct)

        _backtest_results = {
            "symbol": symbol,
            "timeframe": timeframe,
            "days": days,
            "include_costs": inc_costs,
            "fee_bps_per_side": fee_bps,
            "funding_rate_per_period": funding_rate,
            "run_at": datetime.now(timezone.utc).isoformat(),
            "stats": stats,
            "trades": trades[-100:],  # last 100 for display
        }

        return _backtest_results

    except Exception as e:
        logger.error(f"run_backtest error for {symbol}: {e}")
        return {"error": str(e), "symbol": symbol}


def get_backtest_results() -> Optional[Dict]:
    return _backtest_results


def get_paper_trading_status() -> Dict:
    return dict(_paper_trading)


def update_paper_trade(
    signal_type: str,
    entry: float,
    exit_price: float,
    result: str,
    *,
    stop_loss: Optional[float] = None,
    bars_held: int = 0,
    timeframe: str = "1h",
) -> None:
    """
    Record a paper trade outcome.

    NOTE: when called from older code paths without `stop_loss`, the equity
    curve is updated with a *gross* approximation (no fees, no risk-fraction
    scaling) — newer callers should always pass `stop_loss` so that the same
    fee-aware equity model used by the backtest is applied here too.
    """
    if entry <= 0:
        return

    if signal_type == "LONG":
        gross_pnl_pct = (exit_price - entry) / entry * 100
    else:
        gross_pnl_pct = (entry - exit_price) / entry * 100

    if stop_loss is not None and stop_loss > 0:
        breakdown = compute_trade_costs(TradeCostInputs(
            entry_price=entry,
            exit_price=exit_price,
            stop_loss_price=stop_loss,
            side=signal_type,
            bars_held=bars_held,
            bar_minutes=_bar_minutes(timeframe),
            risk_per_trade_pct=settings.BACKTEST_RISK_PER_TRADE_PCT,
            fee_bps_per_side=settings.FEE_BPS_TAKER,
            funding_rate_per_period=settings.BACKTEST_DEFAULT_FUNDING_RATE_PER_8H,
        ))
        net_acct_pct = breakdown.net_account_pct
    else:
        # Legacy path: no SL provided, treat as un-leveraged spot-style PnL on
        # the *full* balance. Still correct unit-wise (just less realistic).
        net_acct_pct = gross_pnl_pct

    _paper_trading["trades"].append({
        "signal_type": signal_type,
        "entry": entry,
        "exit": exit_price,
        "result": result,
        "pnl_pct": round(gross_pnl_pct, 4),
        "net_account_pct": round(net_acct_pct, 4),
        "bars_held": bars_held,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    _paper_trading["current_balance"] *= (1 + net_acct_pct / 100.0)
    _paper_trading["equity_curve"].append(round(_paper_trading["current_balance"], 2))


class BacktestEngine:
    """Backtesting and paper trading engine."""

    async def run(
        self,
        symbol: str,
        timeframe: str = "1h",
        days: int = 30,
        **kwargs,
    ) -> Dict:
        return await run_backtest(symbol, timeframe, days, **kwargs)

    def get_results(self) -> Optional[Dict]:
        return get_backtest_results()

    def get_paper_status(self) -> Dict:
        return get_paper_trading_status()


backtest_engine = BacktestEngine()

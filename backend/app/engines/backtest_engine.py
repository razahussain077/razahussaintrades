"""
Backtesting Engine — Feature 6
Runs historical analysis and tracks signal performance.
Paper trading mode also supported.
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

import numpy as np

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
    Returns: hit level (TP1/TP2/TP3/SL), exit price, pnl_pct, bars_held.
    """
    for i, candle in enumerate(future_candles):
        high = candle["high"]
        low = candle["low"]

        if signal_type == "LONG":
            if low <= stop_loss:
                pnl_pct = (stop_loss - entry_price) / entry_price * 100
                return {"result": "SL", "exit_price": stop_loss, "pnl_pct": round(pnl_pct, 3), "bars_held": i + 1}
            if high >= tp3:
                pnl_pct = (tp3 - entry_price) / entry_price * 100
                return {"result": "TP3", "exit_price": tp3, "pnl_pct": round(pnl_pct, 3), "bars_held": i + 1}
            if high >= tp2:
                pnl_pct = (tp2 - entry_price) / entry_price * 100
                return {"result": "TP2", "exit_price": tp2, "pnl_pct": round(pnl_pct, 3), "bars_held": i + 1}
            if high >= tp1:
                pnl_pct = (tp1 - entry_price) / entry_price * 100
                return {"result": "TP1", "exit_price": tp1, "pnl_pct": round(pnl_pct, 3), "bars_held": i + 1}
        else:  # SHORT
            if high >= stop_loss:
                pnl_pct = (entry_price - stop_loss) / entry_price * 100
                return {"result": "SL", "exit_price": stop_loss, "pnl_pct": round(-abs(pnl_pct if False else (entry_price - stop_loss) / entry_price * 100), 3), "bars_held": i + 1}
            if low <= tp3:
                pnl_pct = (entry_price - tp3) / entry_price * 100
                return {"result": "TP3", "exit_price": tp3, "pnl_pct": round(pnl_pct, 3), "bars_held": i + 1}
            if low <= tp2:
                pnl_pct = (entry_price - tp2) / entry_price * 100
                return {"result": "TP2", "exit_price": tp2, "pnl_pct": round(pnl_pct, 3), "bars_held": i + 1}
            if low <= tp1:
                pnl_pct = (entry_price - tp1) / entry_price * 100
                return {"result": "TP1", "exit_price": tp1, "pnl_pct": round(pnl_pct, 3), "bars_held": i + 1}

    # Expired
    last_price = future_candles[-1]["close"] if future_candles else entry_price
    if signal_type == "LONG":
        pnl_pct = (last_price - entry_price) / entry_price * 100
    else:
        pnl_pct = (entry_price - last_price) / entry_price * 100
    return {"result": "EXPIRED", "exit_price": last_price, "pnl_pct": round(pnl_pct, 3), "bars_held": len(future_candles)}


def _calculate_backtest_stats(trades: List[Dict], starting_balance: float) -> Dict:
    """Calculate comprehensive backtest statistics."""
    if not trades:
        return {
            "total_signals": 0,
            "win_rate": 0,
            "avg_rr": 0,
            "profit_factor": 0,
            "max_drawdown_pct": 0,
            "best_trade_pct": 0,
            "worst_trade_pct": 0,
            "sharpe_ratio": 0,
            "equity_curve": [],
        }

    wins = [t for t in trades if t.get("result") not in ("SL",)]
    losses = [t for t in trades if t.get("result") == "SL"]

    win_count = len([t for t in trades if t.get("result") in ("TP1", "TP2", "TP3")])
    total = len(trades)
    win_rate = win_count / total * 100 if total > 0 else 0

    pnl_list = [t.get("pnl_pct", 0) for t in trades]
    gross_profit = sum(p for p in pnl_list if p > 0)
    gross_loss = abs(sum(p for p in pnl_list if p < 0))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    avg_rr = np.mean([t.get("rr", 0) for t in trades]) if trades else 0

    # Equity curve
    balance = starting_balance
    equity_curve = [balance]
    peak = balance
    max_drawdown = 0.0

    for t in trades:
        pnl_pct = t.get("pnl_pct", 0)
        balance = balance * (1 + pnl_pct / 100 * 0.01)  # 1% of balance per trade
        equity_curve.append(round(balance, 2))
        if balance > peak:
            peak = balance
        dd = (peak - balance) / peak * 100
        if dd > max_drawdown:
            max_drawdown = dd

    # Sharpe ratio (simplified)
    returns = np.array(pnl_list)
    sharpe = float(np.mean(returns) / np.std(returns) * np.sqrt(252)) if np.std(returns) > 0 else 0

    return {
        "total_signals": total,
        "win_count": win_count,
        "loss_count": len(losses),
        "win_rate": round(win_rate, 1),
        "avg_rr": round(float(avg_rr), 2),
        "profit_factor": round(float(profit_factor), 2) if profit_factor != float("inf") else 999,
        "max_drawdown_pct": round(float(max_drawdown), 2),
        "best_trade_pct": round(float(max(pnl_list)), 3) if pnl_list else 0,
        "worst_trade_pct": round(float(min(pnl_list)), 3) if pnl_list else 0,
        "sharpe_ratio": round(float(sharpe), 2),
        "total_pnl_pct": round(float(sum(pnl_list)), 3),
        "equity_curve": equity_curve[-50:],  # Last 50 points for chart
    }


async def run_backtest(
    symbol: str,
    timeframe: str = "1h",
    days: int = 30,
) -> Dict:
    """
    Run backtest on historical data for a symbol.
    Fetches historical klines and simulates signal detection.
    """
    global _backtest_results

    try:
        # Fetch historical candles (up to 500 for the timeframe)
        limit = min(500, days * 24 if timeframe == "1h" else days * 4 if timeframe == "4h" else days)
        candles = await binance_client.get_klines(symbol, timeframe, limit)

        if len(candles) < 50:
            return {"error": f"Insufficient candles for {symbol}", "symbol": symbol}

        # Simple backtesting: use moving signal patterns on historical data
        # We'll use a simple rule: RSI + price action to generate mock signals
        trades = []
        window = 30

        for i in range(window, len(candles) - 20):
            segment = candles[i - window:i]
            future = candles[i:i + 20]

            close_prices = [c["close"] for c in segment]
            current_price = close_prices[-1]

            # Simple momentum signal detection
            sma_short = np.mean(close_prices[-5:])
            sma_long = np.mean(close_prices[-20:])

            # Volume check
            avg_vol = np.mean([c["volume"] for c in segment])
            curr_vol = segment[-1]["volume"]
            volume_relative = curr_vol / avg_vol if avg_vol > 0 else 1.0

            signal_type = None
            if sma_short > sma_long * 1.01 and volume_relative > 1.2:
                signal_type = "LONG"
            elif sma_short < sma_long * 0.99 and volume_relative > 1.2:
                signal_type = "SHORT"

            if signal_type is None:
                continue

            # Calculate SL/TP
            atr = np.mean([c["high"] - c["low"] for c in segment[-14:]])
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

            rr = abs(tp2 - current_price) / abs(current_price - stop_loss) if abs(current_price - stop_loss) > 0 else 0

            outcome = _simulate_trade_outcome(
                signal_type, current_price, stop_loss, tp1, tp2, tp3, future
            )

            trades.append({
                "symbol": symbol,
                "signal_type": signal_type,
                "entry_price": round(current_price, 8),
                "stop_loss": round(stop_loss, 8),
                "tp1": round(tp1, 8),
                "tp2": round(tp2, 8),
                "tp3": round(tp3, 8),
                "rr": round(rr, 2),
                "candle_index": i,
                "timestamp": candles[i]["timestamp"],
                **outcome,
            })

        stats = _calculate_backtest_stats(trades, 1000.0)

        _backtest_results = {
            "symbol": symbol,
            "timeframe": timeframe,
            "days": days,
            "run_at": datetime.now(timezone.utc).isoformat(),
            "stats": stats,
            "trades": trades[-100:],  # Last 100 trades for display
        }

        return _backtest_results

    except Exception as e:
        logger.error(f"run_backtest error for {symbol}: {e}")
        return {"error": str(e), "symbol": symbol}


def get_backtest_results() -> Optional[Dict]:
    return _backtest_results


def get_paper_trading_status() -> Dict:
    return dict(_paper_trading)


def update_paper_trade(signal_type: str, entry: float, exit_price: float, result: str) -> None:
    """Record a paper trade outcome."""
    if signal_type == "LONG":
        pnl_pct = (exit_price - entry) / entry * 100
    else:
        pnl_pct = (entry - exit_price) / entry * 100

    _paper_trading["trades"].append({
        "signal_type": signal_type,
        "entry": entry,
        "exit": exit_price,
        "result": result,
        "pnl_pct": round(pnl_pct, 3),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    # Update balance (1% risk per trade)
    _paper_trading["current_balance"] *= (1 + pnl_pct / 100 * 0.01)
    _paper_trading["equity_curve"].append(round(_paper_trading["current_balance"], 2))


class BacktestEngine:
    """Backtesting and paper trading engine."""

    async def run(self, symbol: str, timeframe: str = "1h", days: int = 30) -> Dict:
        return await run_backtest(symbol, timeframe, days)

    def get_results(self) -> Optional[Dict]:
        return get_backtest_results()

    def get_paper_status(self) -> Dict:
        return get_paper_trading_status()


backtest_engine = BacktestEngine()

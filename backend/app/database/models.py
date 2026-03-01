"""
Database model helpers: CRUD operations for signals, portfolio settings, and signal history.
The actual schema is defined in db.py using CREATE TABLE statements.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import aiosqlite

from app.database.db import get_db

logger = logging.getLogger(__name__)


async def save_signal(signal_data: Dict) -> bool:
    """Insert a new signal into the database."""
    try:
        async with get_db() as db:
            db.row_factory = aiosqlite.Row
            await db.execute(
                """
                INSERT OR REPLACE INTO signals (
                    id, coin, exchange, signal_type, timeframe,
                    entry_low, entry_high, stop_loss, stop_loss_pct,
                    take_profit_1, take_profit_1_pct, take_profit_2, take_profit_2_pct,
                    take_profit_3, take_profit_3_pct,
                    recommended_leverage, liquidation_price, risk_reward,
                    confidence_score, setup_type, reasoning, invalidation,
                    kill_zone, created_at, is_active, taken, result
                ) VALUES (
                    :id, :coin, :exchange, :signal_type, :timeframe,
                    :entry_low, :entry_high, :stop_loss, :stop_loss_pct,
                    :take_profit_1, :take_profit_1_pct, :take_profit_2, :take_profit_2_pct,
                    :take_profit_3, :take_profit_3_pct,
                    :recommended_leverage, :liquidation_price, :risk_reward,
                    :confidence_score, :setup_type, :reasoning, :invalidation,
                    :kill_zone, :created_at, :is_active, :taken, :result
                )
                """,
                {
                    **signal_data,
                    "reasoning": json.dumps(signal_data.get("reasoning", [])),
                    "is_active": 1 if signal_data.get("is_active", True) else 0,
                    "taken": 1 if signal_data.get("taken", False) else 0,
                    "result": signal_data.get("result"),
                },
            )
            await db.commit()
            return True
    except Exception as e:
        logger.error(f"save_signal error: {e}")
        return False


async def get_signals(
    is_active: Optional[bool] = True,
    coin: Optional[str] = None,
    signal_type: Optional[str] = None,
    limit: int = 50,
) -> List[Dict]:
    """Fetch signals from database with optional filters."""
    try:
        conditions = []
        params: List[Any] = []

        if is_active is not None:
            conditions.append("is_active = ?")
            params.append(1 if is_active else 0)
        if coin:
            conditions.append("coin = ?")
            params.append(coin)
        if signal_type:
            conditions.append("signal_type = ?")
            params.append(signal_type)

        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        query = f"SELECT * FROM signals {where} ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        async with get_db() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
            result = []
            for row in rows:
                d = dict(row)
                d["reasoning"] = json.loads(d.get("reasoning", "[]"))
                d["is_active"] = bool(d.get("is_active", 1))
                d["taken"] = bool(d.get("taken", 0))
                result.append(d)
            return result
    except Exception as e:
        logger.error(f"get_signals error: {e}")
        return []


async def get_signal_by_id(signal_id: str) -> Optional[Dict]:
    """Fetch a single signal by ID."""
    try:
        async with get_db() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM signals WHERE id = ?", (signal_id,))
            row = await cursor.fetchone()
            if row:
                d = dict(row)
                d["reasoning"] = json.loads(d.get("reasoning", "[]"))
                d["is_active"] = bool(d.get("is_active", 1))
                d["taken"] = bool(d.get("taken", 0))
                return d
            return None
    except Exception as e:
        logger.error(f"get_signal_by_id error: {e}")
        return None


async def mark_signal_taken(signal_id: str) -> bool:
    """Mark a signal as taken by the user."""
    try:
        async with get_db() as db:
            db.row_factory = aiosqlite.Row
            await db.execute(
                "UPDATE signals SET taken = 1 WHERE id = ?", (signal_id,)
            )
            await db.commit()
            return True
    except Exception as e:
        logger.error(f"mark_signal_taken error: {e}")
        return False


async def deactivate_signal(signal_id: str) -> bool:
    """Deactivate a signal."""
    try:
        async with get_db() as db:
            db.row_factory = aiosqlite.Row
            await db.execute(
                "UPDATE signals SET is_active = 0 WHERE id = ?", (signal_id,)
            )
            await db.commit()
            return True
    except Exception as e:
        logger.error(f"deactivate_signal error: {e}")
        return False


async def save_portfolio_settings(settings_data: Dict) -> bool:
    """Upsert portfolio settings (single row, id=1)."""
    try:
        async with get_db() as db:
            db.row_factory = aiosqlite.Row
            # Check if row exists
            cursor = await db.execute("SELECT id FROM portfolio_settings WHERE id = 1")
            existing = await cursor.fetchone()
            now = datetime.now(timezone.utc).isoformat()
            if existing:
                await db.execute(
                    """
                    UPDATE portfolio_settings SET
                        budget = :budget,
                        risk_tolerance = :risk_tolerance,
                        preferred_timeframes = :preferred_timeframes,
                        max_positions = :max_positions,
                        max_leverage = :max_leverage,
                        updated_at = :updated_at
                    WHERE id = 1
                    """,
                    {
                        **settings_data,
                        "preferred_timeframes": json.dumps(settings_data.get("preferred_timeframes", ["1h", "4h"])),
                        "updated_at": now,
                    },
                )
            else:
                await db.execute(
                    """
                    INSERT INTO portfolio_settings (id, budget, risk_tolerance, preferred_timeframes, max_positions, max_leverage, updated_at)
                    VALUES (1, :budget, :risk_tolerance, :preferred_timeframes, :max_positions, :max_leverage, :updated_at)
                    """,
                    {
                        **settings_data,
                        "preferred_timeframes": json.dumps(settings_data.get("preferred_timeframes", ["1h", "4h"])),
                        "updated_at": now,
                    },
                )
            await db.commit()
            return True
    except Exception as e:
        logger.error(f"save_portfolio_settings error: {e}")
        return False


async def get_portfolio_settings() -> Optional[Dict]:
    """Retrieve portfolio settings."""
    try:
        async with get_db() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM portfolio_settings WHERE id = 1")
            row = await cursor.fetchone()
            if row:
                d = dict(row)
                d["preferred_timeframes"] = json.loads(d.get("preferred_timeframes", '["1h","4h"]'))
                return d
            return None
    except Exception as e:
        logger.error(f"get_portfolio_settings error: {e}")
        return None


async def save_signal_history(history_data: Dict) -> bool:
    """Save a signal result to history."""
    try:
        async with get_db() as db:
            db.row_factory = aiosqlite.Row
            now = datetime.now(timezone.utc).isoformat()
            await db.execute(
                """
                INSERT INTO signal_history (signal_id, result, pnl, closed_at)
                VALUES (:signal_id, :result, :pnl, :closed_at)
                """,
                {
                    "signal_id": history_data["signal_id"],
                    "result": history_data["result"],
                    "pnl": history_data.get("pnl", 0),
                    "closed_at": history_data.get("closed_at", now),
                },
            )
            # Also update the signal record
            await db.execute(
                "UPDATE signals SET result = ?, is_active = 0 WHERE id = ?",
                (history_data["result"], history_data["signal_id"]),
            )
            await db.commit()
            return True
    except Exception as e:
        logger.error(f"save_signal_history error: {e}")
        return False


async def get_signal_stats() -> Dict:
    """Get win/loss statistics from signal history."""
    try:
        async with get_db() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT result, COUNT(*) as count, SUM(pnl) as total_pnl
                FROM signal_history
                GROUP BY result
                """
            )
            rows = await cursor.fetchall()
            stats = {"WIN": 0, "LOSS": 0, "BE": 0, "total_pnl": 0.0}
            for row in rows:
                d = dict(row)
                result = d["result"]
                stats[result] = d["count"]
                stats["total_pnl"] += d.get("total_pnl") or 0

            total = stats["WIN"] + stats["LOSS"] + stats["BE"]
            stats["total_trades"] = total
            stats["win_rate"] = round(stats["WIN"] / total * 100, 1) if total > 0 else 0
            return stats
    except Exception as e:
        logger.error(f"get_signal_stats error: {e}")
        return {"WIN": 0, "LOSS": 0, "BE": 0, "total_trades": 0, "win_rate": 0, "total_pnl": 0}

import aiosqlite
import logging
import os

from app.config import settings

logger = logging.getLogger(__name__)

DB_PATH = settings.DATABASE_PATH


def get_db() -> aiosqlite.Connection:
    """Return an aiosqlite context-managed connection (use with `async with`)."""
    os.makedirs(os.path.dirname(DB_PATH) if os.path.dirname(DB_PATH) else ".", exist_ok=True)
    return aiosqlite.connect(DB_PATH)


async def init_db() -> None:
    """Initialize all database tables."""
    os.makedirs(os.path.dirname(DB_PATH) if os.path.dirname(DB_PATH) else ".", exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")

        # Signals table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id TEXT PRIMARY KEY,
                coin TEXT NOT NULL,
                exchange TEXT NOT NULL DEFAULT 'binance',
                signal_type TEXT NOT NULL CHECK(signal_type IN ('LONG', 'SHORT')),
                timeframe TEXT NOT NULL DEFAULT '1h',
                entry_low REAL NOT NULL,
                entry_high REAL NOT NULL,
                stop_loss REAL NOT NULL,
                stop_loss_pct REAL NOT NULL DEFAULT 0,
                take_profit_1 REAL NOT NULL,
                take_profit_1_pct REAL NOT NULL DEFAULT 0,
                take_profit_2 REAL NOT NULL,
                take_profit_2_pct REAL NOT NULL DEFAULT 0,
                take_profit_3 REAL NOT NULL,
                take_profit_3_pct REAL NOT NULL DEFAULT 0,
                recommended_leverage REAL NOT NULL DEFAULT 1,
                liquidation_price REAL NOT NULL DEFAULT 0,
                risk_reward REAL NOT NULL DEFAULT 0,
                confidence_score REAL NOT NULL,
                setup_type TEXT NOT NULL,
                reasoning TEXT NOT NULL DEFAULT '[]',
                invalidation TEXT NOT NULL DEFAULT '',
                kill_zone TEXT NOT NULL DEFAULT 'Off Hours',
                created_at TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                taken INTEGER NOT NULL DEFAULT 0,
                result TEXT CHECK(result IN ('WIN', 'LOSS', 'BE', NULL))
            )
        """)

        # Portfolio settings table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS portfolio_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                budget REAL NOT NULL DEFAULT 1000.0,
                risk_tolerance REAL NOT NULL DEFAULT 1.0,
                preferred_timeframes TEXT NOT NULL DEFAULT '["1h","4h"]',
                max_positions INTEGER NOT NULL DEFAULT 5,
                max_leverage REAL NOT NULL DEFAULT 10.0,
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

        # Signal history table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS signal_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id TEXT NOT NULL,
                result TEXT NOT NULL CHECK(result IN ('WIN', 'LOSS', 'BE')),
                pnl REAL NOT NULL DEFAULT 0,
                closed_at TEXT NOT NULL,
                FOREIGN KEY (signal_id) REFERENCES signals(id)
            )
        """)

        # Indexes
        await db.execute("CREATE INDEX IF NOT EXISTS idx_signals_coin ON signals(coin)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_signals_active ON signals(is_active)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_signals_created ON signals(created_at)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_history_signal ON signal_history(signal_id)")

        await db.commit()
        logger.info("Database initialized successfully")

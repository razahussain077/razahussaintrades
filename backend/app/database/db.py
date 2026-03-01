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

        # Funding rate history table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS funding_rate_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                rate REAL NOT NULL,
                mark_price REAL NOT NULL DEFAULT 0,
                recorded_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

        # Liquidation events table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS liquidation_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                quantity REAL NOT NULL,
                price REAL NOT NULL,
                usd_value REAL NOT NULL DEFAULT 0,
                occurred_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

        # Backtest results table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS backtest_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL DEFAULT '1h',
                days INTEGER NOT NULL DEFAULT 30,
                win_rate REAL NOT NULL DEFAULT 0,
                total_signals INTEGER NOT NULL DEFAULT 0,
                profit_factor REAL NOT NULL DEFAULT 0,
                max_drawdown_pct REAL NOT NULL DEFAULT 0,
                sharpe_ratio REAL NOT NULL DEFAULT 0,
                result_json TEXT NOT NULL DEFAULT '{}',
                run_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

        # Paper trading table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS paper_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                entry_price REAL NOT NULL,
                exit_price REAL NOT NULL DEFAULT 0,
                result TEXT,
                pnl_pct REAL NOT NULL DEFAULT 0,
                balance_after REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                closed_at TEXT
            )
        """)

        # Economic events cache table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS economic_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                impact TEXT NOT NULL DEFAULT 'LOW',
                currency TEXT NOT NULL DEFAULT 'USD',
                event_datetime TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'scheduled',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

        # Signal lifecycle tracking (Phase 3 enhancement)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS signal_lifecycle (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                tp1_hit INTEGER NOT NULL DEFAULT 0,
                tp2_hit INTEGER NOT NULL DEFAULT 0,
                tp3_hit INTEGER NOT NULL DEFAULT 0,
                sl_hit INTEGER NOT NULL DEFAULT 0,
                current_pnl_pct REAL NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (signal_id) REFERENCES signals(id)
            )
        """)

        # Risk settings table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS risk_settings (
                id INTEGER PRIMARY KEY DEFAULT 1,
                balance REAL NOT NULL DEFAULT 1000.0,
                risk_pct REAL NOT NULL DEFAULT 1.0,
                max_trades INTEGER NOT NULL DEFAULT 5,
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

        # Indexes
        await db.execute("CREATE INDEX IF NOT EXISTS idx_signals_coin ON signals(coin)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_signals_active ON signals(is_active)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_signals_created ON signals(created_at)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_history_signal ON signal_history(signal_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_funding_symbol ON funding_rate_history(symbol)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_liq_symbol ON liquidation_events(symbol)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_lifecycle_signal ON signal_lifecycle(signal_id)")

        await db.commit()
        logger.info("Database initialized successfully")

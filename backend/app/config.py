from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    PKT_TIMEZONE: str = "Asia/Karachi"

    # Exchange base URLs
    BINANCE_BASE_URL: str = "https://api.binance.com"
    BINANCE_FUTURES_URL: str = "https://fapi.binance.com"
    BYBIT_BASE_URL: str = "https://api.bybit.com"
    OKX_BASE_URL: str = "https://www.okx.com"
    COINGECKO_BASE_URL: str = "https://api.coingecko.com/api/v3"

    # Database
    SQLITE_URL: str = "sqlite:///./data/trades.db"
    DATABASE_PATH: str = "./data/trades.db"

    # WebSocket endpoints
    WS_BINANCE: str = "wss://stream.binance.com:9443/ws"
    WS_BINANCE_FUTURES: str = "wss://fstream.binance.com/ws"

    # App settings
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    # Cache TTL in seconds
    PRICE_CACHE_TTL: int = 5
    CANDLE_CACHE_TTL: int = 30
    MARKET_CACHE_TTL: int = 60

    # Risk defaults
    DEFAULT_RISK_PCT: float = 1.0
    # Cap leverage at 10x for safety; the anti-liquidation formula may recommend
    # up to 20x in low-volatility markets, but 10x is a safer default ceiling.
    MAX_LEVERAGE: float = 10.0
    MIN_CONFIDENCE_SCORE: float = 60.0

    # Trading cost defaults — used to model realistic PnL in backtest and to show
    # fee-adjusted R/R on live signals. Defaults are Binance USDⓂ-Futures retail
    # tier (taker 0.04%, maker 0.02%); override via env for VIP/maker rebate tiers.
    FEE_BPS_TAKER: float = 4.0   # 0.04% per side
    FEE_BPS_MAKER: float = 2.0   # 0.02% per side
    # Default per-trade account risk used by backtest equity simulation.
    BACKTEST_RISK_PER_TRADE_PCT: float = 1.0
    # Funding rate to assume for backtests when no historical funding data is
    # available, expressed per 8h period. 0.0001 == 0.01% per 8h ≈ neutral.
    BACKTEST_DEFAULT_FUNDING_RATE_PER_8H: float = 0.0001
    # Whether to subtract round-trip fees + funding from backtest PnL by default.
    BACKTEST_INCLUDE_COSTS: bool = True

    # Comma-separated list of allowed CORS origins. Defaults to "*" only when
    # ENVIRONMENT == "development". In production, set this explicitly.
    ALLOWED_ORIGINS: str = "*"

    # Lower-timeframe entry refinement (PR5).
    # When enabled, signal_generator computes a 5m sweep+reclaim trigger and a
    # 1h/4h higher-timeframe bias confirmation, and adds a +5 / -5 bonus to
    # the confidence score depending on alignment. When `LTF_ENTRY_REQUIRED`
    # is true, signals are dropped if the trigger has not fired or HTF bias
    # disagrees, regardless of rule-based confidence.
    LTF_ENTRY_REQUIRED: bool = False
    LTF_TRIGGER_TIMEFRAME: str = "5m"
    LTF_TRIGGER_LOOKBACK: int = 24    # bars on the trigger TF to scan for sweep
    LTF_TRIGGER_RECLAIM_BARS: int = 3  # close-back-above must happen within N bars

    # Telegram push notifications (PR6).
    # Both token and chat id must be set to enable; the client is a no-op
    # otherwise. NOTIFICATIONS_ENABLED is the master kill — separate from
    # the user-facing kill switch (kill_switch.py) which is a runtime toggle.
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""
    NOTIFICATIONS_ENABLED: bool = True
    DASHBOARD_URL: str = ""  # public URL used for inline-keyboard buttons

    # ------------------------------------------------------------------
    # Auto-execution (PR7) — DANGEROUS. Off by default, dry-run by default.
    # ------------------------------------------------------------------
    # Master kill: even if everything else is configured, no order is placed
    # unless this is explicitly true.
    AUTO_EXECUTION_ENABLED: bool = False
    # When true the executor walks the full code path (sizing, formatting,
    # idempotency) but never sends to the exchange — instead it returns a
    # deterministic "dry-{signal_id}" order id. Stays true by default to
    # protect users who flip ENABLED without realizing they hadn't set this.
    AUTO_EXECUTION_DRY_RUN: bool = True
    # Confidence floor for *automatic* placement (the manual /place endpoint
    # uses the guardian's own min). Higher than the 60 confidence shown in
    # cards, by design — auto-trading should be selective.
    AUTO_EXECUTION_MIN_CONFIDENCE: float = 80.0
    # Hard caps applied by the AccountGuardian. Override only if you really
    # know what you're doing.
    AUTO_EXECUTION_MAX_RISK_PCT: float = 0.005   # 0.5% per trade
    AUTO_EXECUTION_MAX_LEVERAGE: float = 5.0
    AUTO_EXECUTION_MAX_CONCURRENT: int = 3
    AUTO_EXECUTION_DAILY_LOSS_LIMIT_PCT: float = 0.03
    AUTO_EXECUTION_MIN_RR_NET: float = 1.5
    # If we cannot read account equity (no creds, ccxt unreachable), fall back
    # to this number for sizing math. Defaults to 0 so the guardian rejects.
    AUTO_EXECUTION_FALLBACK_EQUITY_USD: float = 0.0
    # Length of an arming window before auto-disarm, in minutes.
    AUTO_EXECUTION_ARM_DURATION_MIN: int = 240   # 4 hours

    # Exchange credentials (CCXT). Only consumed by app/execution/.
    EXCHANGE_NAME: str = "binanceusdm"            # ccxt class name
    EXCHANGE_API_KEY: str = ""
    EXCHANGE_API_SECRET: str = ""
    # Base32 TOTP secret used to arm auto-execution. NOT the same as your
    # exchange's withdrawal-2FA secret.
    EXECUTION_TOTP_SECRET: str = ""

    TOP_50_COINS: List[str] = [
        "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
        "ADAUSDT", "AVAXUSDT", "DOGEUSDT", "DOTUSDT", "TRXUSDT",
        "LINKUSDT", "MATICUSDT", "LTCUSDT", "SHIBUSDT", "UNIUSDT",
        "ATOMUSDT", "ETCUSDT", "XLMUSDT", "BCHUSDT", "ALGOUSDT",
        "VETUSDT", "FILUSDT", "NEARUSDT", "ICPUSDT", "AAVEUSDT",
        "GRTUSDT", "FTMUSDT", "SANDUSDT", "MANAUSDT", "AXSUSDT",
        "CHZUSDT", "ENJUSDT", "CRVUSDT", "COMPUSDT", "MKRUSDT",
        "YFIUSDT", "SUSHIUSDT", "1INCHUSDT", "SNXUSDT", "UMAUSDT",
        "RUNEUSDT", "KAVAUSDT", "BANDUSDT", "STORJUSDT", "SKLUSDT",
        "ARPAUSDT", "CTKUSDT", "IOTAUSDT", "ZILUSDT", "ONTUSDT",
    ]

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()

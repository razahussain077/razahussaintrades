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

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

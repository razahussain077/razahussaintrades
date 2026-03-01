from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class Signal(BaseModel):
    id: str
    coin: str
    exchange: str
    signal_type: Literal["LONG", "SHORT"]
    timeframe: str
    entry_low: float
    entry_high: float
    stop_loss: float
    stop_loss_pct: float
    take_profit_1: float
    take_profit_1_pct: float
    take_profit_2: float
    take_profit_2_pct: float
    take_profit_3: float
    take_profit_3_pct: float
    recommended_leverage: float
    liquidation_price: float
    risk_reward: float
    confidence_score: float
    setup_type: str
    reasoning: List[str]
    invalidation: str
    kill_zone: str
    created_at: datetime
    is_active: bool = True
    taken: bool = False
    result: Optional[Literal["WIN", "LOSS", "BE"]] = None


class SignalCreate(BaseModel):
    coin: str
    exchange: str = "binance"
    signal_type: Literal["LONG", "SHORT"]
    timeframe: str = "1h"
    entry_low: float
    entry_high: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    take_profit_3: float
    confidence_score: float
    setup_type: str
    reasoning: List[str]
    invalidation: str
    kill_zone: str = "Off Hours"


class SignalFilter(BaseModel):
    min_confidence: float = 60.0
    signal_type: Optional[Literal["LONG", "SHORT"]] = None
    coin: Optional[str] = None
    is_active: Optional[bool] = True
    limit: int = Field(default=50, le=200)


class PortfolioSettings(BaseModel):
    budget: float = Field(default=1000.0, gt=0)
    risk_tolerance: float = Field(default=1.0, ge=0.1, le=5.0)
    preferred_timeframes: List[str] = Field(default=["1h", "4h"])
    max_positions: int = Field(default=5, ge=1, le=20)
    max_leverage: float = Field(default=10.0, ge=1.0, le=50.0)


class RiskCalculationRequest(BaseModel):
    portfolio: float = Field(gt=0)
    risk_pct: float = Field(default=1.0, ge=0.1, le=10.0)
    entry_price: float = Field(gt=0)
    stop_loss: float = Field(gt=0)
    nearest_liquidity: Optional[float] = None
    side: Literal["LONG", "SHORT"] = "LONG"


class RiskCalculationResponse(BaseModel):
    position_size: float
    position_value: float
    risk_amount: float
    recommended_leverage: float
    liquidation_price: float
    risk_reward: Optional[float] = None
    max_loss: float
    margin_required: float


class MarketOverview(BaseModel):
    total_market_cap_usd: float
    total_volume_usd: float
    btc_dominance: float
    eth_dominance: float
    market_cap_change_pct_24h: float
    fear_greed_score: float
    fear_greed_label: str
    btc_funding_rate: float
    eth_funding_rate: float
    active_cryptocurrencies: int


class CoinData(BaseModel):
    symbol: str
    exchange: str = "binance"
    price: float
    price_change_pct_24h: float = 0.0
    volume_24h: float = 0.0
    high_24h: float = 0.0
    low_24h: float = 0.0
    funding_rate: float = 0.0
    open_interest: float = 0.0
    sources: List[str] = []
    active_signals: int = 0
    market_cap_category: Optional[str] = None

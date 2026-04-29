"""
Fees & Funding Cost Engine.

Centralizes the math for realistic trading-cost deductions so that:
  - The backtest engine produces an equity curve that reflects real net PnL.
  - Live signal cards can show "gross R/R" alongside "net R/R after costs".
  - Future auto-execution can size positions with cost-aware expectations.

All math is done in *price-percent* space (the same space the rule engines use)
and translated into *account-percent* space using the canonical fixed-fractional
risk model:

    R_multiple   = pnl_pct / sl_pct                        (signed, +N for N R win)
    realized_pct = R_multiple * risk_per_trade_pct         (account % per trade)

Round-trip fees & funding scale with notional (=size / margin = leverage), so
when expressed as a fraction of the account they scale by 1/sl_pct in exactly
the same way:

    fee_drag_acct_pct     = round_trip_fee_pct / sl_pct * risk_per_trade_pct
    funding_drag_acct_pct = funding_rate_per_period * periods / sl_pct * risk_per_trade_pct

This file is pure functions + a small class — easy to unit-test without I/O.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# Pure math primitives
# ---------------------------------------------------------------------------

def round_trip_fee_pct(fee_bps_per_side: float, taker_count: int = 2) -> float:
    """
    Round-trip exchange fee, in % of notional.

    Args:
        fee_bps_per_side: Per-side fee in basis points (e.g. 4.0 = 0.04%).
        taker_count: How many sides are taker fills (0, 1, or 2).
                     2 = market in + market out, 1 = limit in + market out,
                     0 = limit in + limit out (maker rebate territory).

    Returns:
        Total round-trip cost as a percentage (e.g. 0.08 for 8 bps).
    """
    if fee_bps_per_side < 0:
        fee_bps_per_side = 0.0
    taker_count = max(0, min(2, int(taker_count)))
    # Mixed: assume taker_count sides at the given fee, the other sides at half
    # (a maker fee is typically half a taker fee on Binance retail tier).
    other_sides = 2 - taker_count
    bps_total = fee_bps_per_side * taker_count + (fee_bps_per_side * 0.5) * other_sides
    return bps_total / 100.0  # bps -> percent


def funding_drag_pct(
    funding_rate_per_period: float,
    periods_held: float,
    side: str,
) -> float:
    """
    Cost (or income) from holding a perpetual position across funding events,
    expressed as % of notional.

    Convention: positive funding rate ⇒ longs pay shorts. So a LONG position
    held across N positive-funding periods *loses* `rate * N` in notional %,
    while a SHORT *gains* the same amount.

    Args:
        funding_rate_per_period: Decimal rate per 8h period (0.0001 = 0.01%).
        periods_held: Number of 8h periods position was open (can be fractional).
        side: 'LONG' or 'SHORT'.
    """
    if periods_held <= 0:
        return 0.0
    side_u = side.upper()
    sign = 1.0 if side_u == "LONG" else -1.0
    return sign * funding_rate_per_period * periods_held * 100.0  # decimal -> %


def bars_to_funding_periods(bars_held: int, bar_minutes: int) -> float:
    """Convert a holding time in bars (of `bar_minutes` each) to 8h funding periods."""
    if bars_held <= 0 or bar_minutes <= 0:
        return 0.0
    minutes = bars_held * bar_minutes
    return minutes / (8 * 60)


def r_multiple(pnl_pct: float, sl_pct: float) -> float:
    """
    Convert a price-percent PnL to an R-multiple (+N for an N-R winner,
    -1 for a SL-hit loser).

    sl_pct is the *positive* magnitude of the SL distance. For a LONG with
    entry=100, SL=98, sl_pct = 2. A move to 106 has pnl_pct = 6, R = 3.
    """
    if sl_pct <= 0:
        return 0.0
    return pnl_pct / sl_pct


def account_pct_from_R(
    R: float,
    risk_per_trade_pct: float,
) -> float:
    """Realized % move on the *account*, given R-multiple and fixed-fractional risk."""
    return R * risk_per_trade_pct


# ---------------------------------------------------------------------------
# High-level dataclass used by the backtest engine and by live signal cards.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TradeCostInputs:
    """Everything needed to compute net realized account % for one trade."""
    entry_price: float
    exit_price: float
    stop_loss_price: float
    side: str                            # "LONG" or "SHORT"
    bars_held: int
    bar_minutes: int                     # 60 for 1h, 240 for 4h, etc.
    risk_per_trade_pct: float = 1.0
    fee_bps_per_side: float = 4.0
    taker_count: int = 2                 # 0..2
    funding_rate_per_period: float = 0.0001  # 0.01%/8h default neutral


@dataclass(frozen=True)
class TradeCostBreakdown:
    """Full fee-aware PnL breakdown — every field is account-level percent."""
    gross_pnl_pct: float        # price-% move, signed (+ for winning direction)
    sl_pct: float               # positive magnitude
    R_multiple: float           # gross_pnl_pct / sl_pct
    gross_account_pct: float    # R * risk_per_trade_pct
    fee_drag_account_pct: float
    funding_drag_account_pct: float
    net_account_pct: float
    funding_periods: float

    def as_dict(self) -> dict:
        return {
            "gross_pnl_pct": round(self.gross_pnl_pct, 6),
            "sl_pct": round(self.sl_pct, 6),
            "R_multiple": round(self.R_multiple, 4),
            "gross_account_pct": round(self.gross_account_pct, 6),
            "fee_drag_account_pct": round(self.fee_drag_account_pct, 6),
            "funding_drag_account_pct": round(self.funding_drag_account_pct, 6),
            "net_account_pct": round(self.net_account_pct, 6),
            "funding_periods": round(self.funding_periods, 4),
        }


def compute_trade_costs(inp: TradeCostInputs) -> TradeCostBreakdown:
    """
    Full fee-aware PnL calculation for a single closed trade.

    Returns a breakdown where `net_account_pct` is the number you should add
    to your equity curve.
    """
    side = inp.side.upper()
    direction = 1.0 if side == "LONG" else -1.0

    if inp.entry_price <= 0:
        # Defensive: zero-size trade.
        return TradeCostBreakdown(0, 0, 0, 0, 0, 0, 0, 0)

    gross_pnl_pct = direction * (inp.exit_price - inp.entry_price) / inp.entry_price * 100.0
    sl_pct = abs(inp.entry_price - inp.stop_loss_price) / inp.entry_price * 100.0

    R = r_multiple(gross_pnl_pct, sl_pct)
    gross_account = account_pct_from_R(R, inp.risk_per_trade_pct)

    rt_fee_pct = round_trip_fee_pct(inp.fee_bps_per_side, inp.taker_count)
    # Fees scale with notional, which (under fixed-fractional sizing) scales as
    # 1/sl_pct. Express the drag in account-% terms.
    fee_drag_account = (rt_fee_pct / sl_pct) * inp.risk_per_trade_pct if sl_pct > 0 else 0.0

    periods = bars_to_funding_periods(inp.bars_held, inp.bar_minutes)
    fund_pct_of_notional = funding_drag_pct(inp.funding_rate_per_period, periods, side)
    # `funding_drag_pct` returns positive cost for LONG-on-positive-rate; for the
    # *account* we subtract it, so we treat it as drag (positive number = cost).
    fund_drag_account = (fund_pct_of_notional / sl_pct) * inp.risk_per_trade_pct if sl_pct > 0 else 0.0

    net_account = gross_account - fee_drag_account - fund_drag_account

    return TradeCostBreakdown(
        gross_pnl_pct=gross_pnl_pct,
        sl_pct=sl_pct,
        R_multiple=R,
        gross_account_pct=gross_account,
        fee_drag_account_pct=fee_drag_account,
        funding_drag_account_pct=fund_drag_account,
        net_account_pct=net_account,
        funding_periods=periods,
    )


# ---------------------------------------------------------------------------
# Convenience for live signal cards: gross vs net R/R.
# ---------------------------------------------------------------------------

def adjust_rr_for_costs(
    gross_rr: float,
    sl_pct: float,
    fee_bps_per_side: float = 4.0,
    taker_count: int = 2,
    funding_rate_per_period: float = 0.0001,
    expected_funding_periods: float = 1.0,
) -> float:
    """
    Convert a quoted R/R (e.g. 2.0 for a 1:2 setup) into a cost-adjusted R/R.

    `sl_pct` here is the SL distance in % of price (positive). The cost drag is
    computed in price-% space and subtracted from the reward leg.
    """
    if gross_rr <= 0 or sl_pct <= 0:
        return 0.0
    rt_fee_pct = round_trip_fee_pct(fee_bps_per_side, taker_count)
    fund_pct = abs(funding_rate_per_period) * expected_funding_periods * 100.0
    cost_drag_pct = rt_fee_pct + fund_pct
    # Reward leg in price-% = gross_rr * sl_pct; subtract drag from it.
    reward_pct = gross_rr * sl_pct - cost_drag_pct
    risk_pct = sl_pct + cost_drag_pct  # losing side also pays costs
    if risk_pct <= 0:
        return 0.0
    return max(0.0, reward_pct / risk_pct)


# Module-level singleton so other modules can import a stable handle if useful.
class FeesEngine:
    """Thin OO wrapper for code that prefers an injectable handle."""

    def round_trip_fee_pct(self, *args, **kwargs) -> float:
        return round_trip_fee_pct(*args, **kwargs)

    def compute_trade_costs(self, inp: TradeCostInputs) -> TradeCostBreakdown:
        return compute_trade_costs(inp)

    def adjust_rr_for_costs(self, *args, **kwargs) -> float:
        return adjust_rr_for_costs(*args, **kwargs)


fees_engine = FeesEngine()

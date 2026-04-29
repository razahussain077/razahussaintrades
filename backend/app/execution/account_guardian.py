"""
Account guardian: pure-Python policy layer that decides whether a signal is
permitted to execute and computes a safely-sized order plan.

This is intentionally exchange-agnostic and side-effect free — it never talks
to ccxt, the database, or the network. The CCXT executor calls
`AccountGuardian.evaluate(...)` and either gets back a `GuardianDecision` with
`approved=True` (and a fully-specified `OrderPlan`), or a rejection with a
human-readable reason. The armed-state, kill-switch, and idempotency layers
sit *outside* the guardian — keeping the math here and the I/O elsewhere
makes both halves trivially testable.

Caps that are enforced (all configurable; defaults are conservative):
  * max_risk_pct           — hard cap on per-trade account risk (default 0.5%)
  * max_leverage           — hard cap regardless of signal recommendation (5x)
  * max_concurrent_positions
  * daily_loss_limit_pct   — circuit breaker; rejects new entries once tripped
  * min_confidence_score   — only auto-execute high-conviction signals (default 80)
  * min_risk_reward_net    — require fee-adjusted edge (default 1.5)

All capacity checks fail closed — if any guard rejects, no order is placed.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# Default split of TP exit volume — front-loaded so the trade pays for itself
# before chasing the runner. Sums to 1.0.
DEFAULT_TP_SPLIT: Tuple[float, float, float] = (0.4, 0.4, 0.2)


@dataclass
class GuardianConfig:
    """Hard caps applied by the guardian. Override via app config / env."""
    max_risk_pct: float = 0.005           # 0.5% account risk per trade
    max_leverage: float = 5.0             # 5x — independent of signal recommendation
    max_concurrent_positions: int = 3
    daily_loss_limit_pct: float = 0.03    # 3% daily drawdown trips the breaker
    min_confidence_score: float = 80.0
    min_risk_reward_net: float = 1.5
    min_notional_usd: float = 10.0        # exchange-side minimums; reject below
    tp_split: Tuple[float, float, float] = DEFAULT_TP_SPLIT


@dataclass
class OrderPlan:
    """Fully-specified bracket plan, denominated in base/quote units.

    The CCXT executor consumes this directly to place the entry + SL + TP1/2/3
    orders. All values are post-cap — the guardian has already clamped
    leverage and trimmed quantity so simply executing this plan respects every
    risk limit.
    """
    coin: str
    side: str                       # "LONG" / "SHORT"
    entry_low: float
    entry_high: float
    entry_mid: float                # midpoint used for the limit price
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    take_profit_3: float
    leverage: float                 # post-cap leverage actually used
    quantity: float                 # base-asset quantity
    notional_usd: float             # quantity * entry_mid (USD-quoted approximation)
    risk_usd: float                 # max loss if SL is hit (≈ equity * risk_pct)
    margin_required_usd: float      # notional / leverage
    tp_split: Tuple[float, float, float] = DEFAULT_TP_SPLIT
    risk_reward_net: float = 0.0
    confidence_score: float = 0.0
    signal_id: str = ""

    def as_dict(self) -> Dict:
        return {
            "coin": self.coin,
            "side": self.side,
            "entry_low": self.entry_low,
            "entry_high": self.entry_high,
            "entry_mid": self.entry_mid,
            "stop_loss": self.stop_loss,
            "take_profit_1": self.take_profit_1,
            "take_profit_2": self.take_profit_2,
            "take_profit_3": self.take_profit_3,
            "leverage": self.leverage,
            "quantity": self.quantity,
            "notional_usd": self.notional_usd,
            "risk_usd": self.risk_usd,
            "margin_required_usd": self.margin_required_usd,
            "tp_split": list(self.tp_split),
            "risk_reward_net": self.risk_reward_net,
            "confidence_score": self.confidence_score,
            "signal_id": self.signal_id,
        }


@dataclass
class GuardianDecision:
    approved: bool
    reason: str                              # short machine reason; empty when approved
    detail: str = ""                         # human-readable detail
    plan: Optional[OrderPlan] = None
    notes: List[str] = field(default_factory=list)


class AccountGuardian:
    """Pure-policy decision engine. No I/O — feed it a snapshot of state."""

    def __init__(self, config: Optional[GuardianConfig] = None) -> None:
        self.cfg = config or GuardianConfig()

    # ------------------------------------------------------------------
    # Position sizing math
    # ------------------------------------------------------------------
    @staticmethod
    def _entry_mid(signal: Dict) -> Optional[float]:
        lo = signal.get("entry_low")
        hi = signal.get("entry_high")
        if lo is None or hi is None:
            return None
        try:
            lo_f = float(lo)
            hi_f = float(hi)
        except (TypeError, ValueError):
            return None
        if lo_f <= 0 or hi_f <= 0:
            return None
        return (lo_f + hi_f) / 2.0

    @staticmethod
    def _risk_per_unit(side: str, entry_mid: float, stop_loss: float) -> float:
        """Absolute distance between entry and SL, in quote terms per base unit."""
        if side == "LONG":
            return max(entry_mid - stop_loss, 0.0)
        if side == "SHORT":
            return max(stop_loss - entry_mid, 0.0)
        return 0.0

    def compute_plan(
        self,
        signal: Dict,
        equity_usd: float,
    ) -> Tuple[Optional[OrderPlan], Optional[str]]:
        """Translate a signal into a sized OrderPlan or return (None, reason).

        Reasons returned here are *math* failures (missing fields, zero-risk SL,
        sub-minimum notional). Policy rejections (cap exceeded, daily-loss
        breaker tripped) come from `evaluate()` which calls this and then
        layers caps on top.
        """
        side = signal.get("signal_type")
        if side not in ("LONG", "SHORT"):
            return None, "invalid_side"

        entry_mid = self._entry_mid(signal)
        if entry_mid is None:
            return None, "missing_entry"

        try:
            sl = float(signal.get("stop_loss"))
        except (TypeError, ValueError):
            return None, "missing_stop_loss"
        if sl <= 0:
            return None, "missing_stop_loss"

        risk_per_unit = self._risk_per_unit(side, entry_mid, sl)
        if risk_per_unit <= 0:
            return None, "stop_loss_wrong_side"

        # Recommended leverage from signal, clamped to our cap.
        signal_lev = (
            signal.get("recommended_leverage")
            or signal.get("leverage")
            or self.cfg.max_leverage
        )
        try:
            signal_lev = float(signal_lev)
        except (TypeError, ValueError):
            signal_lev = self.cfg.max_leverage
        leverage = max(1.0, min(signal_lev, self.cfg.max_leverage))

        # Risk in quote currency (USD): equity * risk_pct.
        risk_usd = max(0.0, equity_usd) * self.cfg.max_risk_pct
        if risk_usd <= 0:
            return None, "zero_equity_or_risk"

        quantity = risk_usd / risk_per_unit
        notional = quantity * entry_mid
        margin = notional / leverage

        if notional < self.cfg.min_notional_usd:
            return None, "below_min_notional"

        # Confidence-weighted TP fields with fallback chain matching telegram.py.
        tp1 = signal.get("take_profit_1") or signal.get("tp1")
        tp2 = signal.get("take_profit_2") or signal.get("tp2")
        tp3 = signal.get("take_profit_3") or signal.get("tp3")
        if tp1 is None or tp2 is None or tp3 is None:
            return None, "missing_take_profit"

        try:
            tp1_f, tp2_f, tp3_f = float(tp1), float(tp2), float(tp3)
        except (TypeError, ValueError):
            return None, "invalid_take_profit"

        rr_net = signal.get("risk_reward_net") or signal.get("rr_net") or 0.0
        try:
            rr_net = float(rr_net)
        except (TypeError, ValueError):
            rr_net = 0.0
        confidence = signal.get("confidence_score") or 0.0
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = 0.0

        plan = OrderPlan(
            coin=str(signal.get("coin") or ""),
            side=side,
            entry_low=float(signal.get("entry_low")),
            entry_high=float(signal.get("entry_high")),
            entry_mid=entry_mid,
            stop_loss=sl,
            take_profit_1=tp1_f,
            take_profit_2=tp2_f,
            take_profit_3=tp3_f,
            leverage=leverage,
            quantity=quantity,
            notional_usd=notional,
            risk_usd=risk_usd,
            margin_required_usd=margin,
            tp_split=self.cfg.tp_split,
            risk_reward_net=rr_net,
            confidence_score=confidence,
            signal_id=str(signal.get("id") or ""),
        )
        return plan, None

    # ------------------------------------------------------------------
    # Policy gates
    # ------------------------------------------------------------------
    def evaluate(
        self,
        signal: Dict,
        equity_usd: float,
        open_positions_count: int,
        today_pnl_usd: float,
        kill_switch_active: bool,
    ) -> GuardianDecision:
        """Apply *all* policy gates. Order matters: kill switch first, then
        circuit breakers, then per-signal quality gates, then sizing math.
        """
        notes: List[str] = []

        if kill_switch_active:
            return GuardianDecision(False, "kill_switch_active",
                                    "Kill switch is engaged; no new orders.",
                                    notes=notes)

        if equity_usd <= 0:
            return GuardianDecision(False, "zero_equity",
                                    "Account equity is zero or unreadable.",
                                    notes=notes)

        if open_positions_count >= self.cfg.max_concurrent_positions:
            return GuardianDecision(
                False, "max_positions_reached",
                f"Already at {open_positions_count} open positions "
                f"(cap {self.cfg.max_concurrent_positions}).",
                notes=notes,
            )

        loss_limit_usd = -abs(equity_usd * self.cfg.daily_loss_limit_pct)
        if today_pnl_usd <= loss_limit_usd:
            return GuardianDecision(
                False, "daily_loss_limit",
                f"Daily loss limit hit (PnL {today_pnl_usd:.2f} ≤ "
                f"{loss_limit_usd:.2f}).",
                notes=notes,
            )

        confidence = float(signal.get("confidence_score") or 0.0)
        if confidence < self.cfg.min_confidence_score:
            return GuardianDecision(
                False, "below_min_confidence",
                f"Signal confidence {confidence:.1f} < "
                f"{self.cfg.min_confidence_score:.1f}.",
                notes=notes,
            )

        rr_net = signal.get("risk_reward_net") or signal.get("rr_net") or 0.0
        try:
            rr_net = float(rr_net)
        except (TypeError, ValueError):
            rr_net = 0.0
        if rr_net < self.cfg.min_risk_reward_net:
            return GuardianDecision(
                False, "below_min_rr_net",
                f"Net R:R {rr_net:.2f} < {self.cfg.min_risk_reward_net:.2f}.",
                notes=notes,
            )

        plan, math_reason = self.compute_plan(signal, equity_usd)
        if plan is None:
            return GuardianDecision(False, math_reason or "sizing_failed",
                                    "Could not size the order.",
                                    notes=notes)

        # Final sanity: required margin must not exceed equity.
        if plan.margin_required_usd > equity_usd:
            return GuardianDecision(
                False, "insufficient_margin",
                f"Required margin {plan.margin_required_usd:.2f} > equity "
                f"{equity_usd:.2f}. Reduce leverage or risk pct.",
                notes=notes,
            )

        if plan.leverage < (signal.get("recommended_leverage") or 0):
            notes.append(
                f"leverage clamped from {signal.get('recommended_leverage')} → "
                f"{plan.leverage}"
            )

        return GuardianDecision(True, "", "approved", plan=plan, notes=notes)


def _config_from_settings() -> GuardianConfig:
    """Build a GuardianConfig that reflects current `app.config.settings`.

    Lazy import: keeps `account_guardian.py` importable when settings haven't
    been initialised yet (e.g. from isolated unit tests).
    """
    try:
        from app.config import settings  # local import to avoid cycle
    except Exception:  # pragma: no cover
        return GuardianConfig()
    return GuardianConfig(
        max_risk_pct=settings.AUTO_EXECUTION_MAX_RISK_PCT,
        max_leverage=settings.AUTO_EXECUTION_MAX_LEVERAGE,
        max_concurrent_positions=settings.AUTO_EXECUTION_MAX_CONCURRENT,
        daily_loss_limit_pct=settings.AUTO_EXECUTION_DAILY_LOSS_LIMIT_PCT,
        min_confidence_score=settings.AUTO_EXECUTION_MIN_CONFIDENCE,
        min_risk_reward_net=settings.AUTO_EXECUTION_MIN_RR_NET,
    )


# Module-level singleton — reads live settings on first import. Tests that
# need different caps instantiate their own AccountGuardian(GuardianConfig(...)).
account_guardian = AccountGuardian(_config_from_settings())

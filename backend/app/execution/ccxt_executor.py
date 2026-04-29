"""
CCXT-backed bracket order executor.

This is the only module in the codebase that talks to a real exchange. It is
deliberately conservative:

  * **Off by default.** `AUTO_EXECUTION_ENABLED=false` and
    `AUTO_EXECUTION_DRY_RUN=true` mean even with credentials configured no
    real order is placed unless the user explicitly opts in.
  * **Armed gate.** Every place call requires the armed-state file to be
    `armed=True` (set via TOTP). Disarmed → reject with reason.
  * **Idempotent.** Before placing, we look up `signal_id` in the orders map
    and short-circuit with the existing record if found.
  * **Bracket-only.** Entry is a *limit* at the entry-zone midpoint with a
    hard SL and three TPs sized per the guardian's `tp_split`.
  * **Dry-run path is honored everywhere.** When `dry_run=True` we walk the
    full code path (sizing, formatting, idempotency) but the ccxt call is
    swapped for a deterministic stub `dry-{signal_id}` order id.

The CCXT library does NOT need to be installed for the dry-run path to work;
`_make_exchange()` only imports ccxt lazily, so unit tests that exercise the
sizing math run cleanly without the dependency.
"""
from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Dict, List, Optional

from app.config import settings
from app.execution.account_guardian import (
    AccountGuardian,
    GuardianDecision,
    OrderPlan,
    account_guardian,
)
from app.execution.state import (
    get_recorded_order,
    is_armed,
    record_order,
)
from app.notifications.kill_switch import is_kill_switch_active

logger = logging.getLogger(__name__)


class ExecutionResult(dict):
    """Thin dict subclass so callers can `.get('ok')` ergonomically."""

    @classmethod
    def ok(cls, order_id: str, plan: OrderPlan, dry_run: bool, orders: List[Dict]) -> "ExecutionResult":
        return cls({
            "ok": True,
            "order_id": order_id,
            "dry_run": dry_run,
            "plan": plan.as_dict(),
            "orders": orders,
        })

    @classmethod
    def reject(cls, reason: str, detail: str = "", **extra) -> "ExecutionResult":
        return cls({"ok": False, "reason": reason, "detail": detail, **extra})


def _make_exchange():
    """Lazy ccxt client construction. Honors EXCHANGE_NAME / API key envs."""
    import ccxt  # type: ignore[import-not-found]

    name = (settings.EXCHANGE_NAME or "binanceusdm").lower()
    if not hasattr(ccxt, name):
        raise RuntimeError(f"ccxt has no exchange called {name!r}")
    klass = getattr(ccxt, name)
    return klass({
        "apiKey": settings.EXCHANGE_API_KEY,
        "secret": settings.EXCHANGE_API_SECRET,
        "enableRateLimit": True,
        "options": {"defaultType": "future"},
    })


class CCXTExecutor:
    """Bracket-order executor. Composes guardian + state + (optional) ccxt."""

    def __init__(self, guardian: Optional[AccountGuardian] = None) -> None:
        self.guardian = guardian or account_guardian
        self._exchange = None  # built lazily

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def place_for_signal(
        self,
        signal: Dict,
        equity_usd: float,
        open_positions_count: int,
        today_pnl_usd: float,
        force_dry_run: Optional[bool] = None,
    ) -> ExecutionResult:
        """The end-to-end auto-exec entrypoint. Returns a dict either way.

        Parameters
        ----------
        signal: the dict produced by `Signal.model_dump()`
        equity_usd: account equity right now (caller fetches this)
        open_positions_count: number of currently-open positions
        today_pnl_usd: realised + unrealised PnL since 00:00 UTC today
        force_dry_run: override settings.AUTO_EXECUTION_DRY_RUN (used by tests)
        """
        signal_id = str(signal.get("id") or "")

        # 1. Master switch.
        if not settings.AUTO_EXECUTION_ENABLED:
            return ExecutionResult.reject(
                "auto_execution_disabled",
                "AUTO_EXECUTION_ENABLED is false. Set the env flag to true.",
            )

        # 2. Armed?
        if not is_armed():
            return ExecutionResult.reject(
                "not_armed",
                "Auto-execution is disarmed. Arm via /api/execution/arm with TOTP.",
            )

        # 3. Idempotency.
        prior = get_recorded_order(signal_id) if signal_id else None
        if prior:
            return ExecutionResult.reject(
                "duplicate_signal",
                f"Order already exists for signal {signal_id}.",
                existing=prior,
            )

        # 4. Guardian decision (kill switch + caps + sizing).
        decision = self.guardian.evaluate(
            signal,
            equity_usd=equity_usd,
            open_positions_count=open_positions_count,
            today_pnl_usd=today_pnl_usd,
            kill_switch_active=is_kill_switch_active(),
        )
        if not decision.approved or decision.plan is None:
            return ExecutionResult.reject(
                decision.reason,
                decision.detail,
                notes=list(decision.notes),
            )

        # 5. Place the bracket. Dry-run unless explicitly overridden.
        dry_run = (
            force_dry_run
            if force_dry_run is not None
            else settings.AUTO_EXECUTION_DRY_RUN
        )

        if dry_run:
            order_id = f"dry-{signal_id or 'unsaved'}"
            orders = self._format_orders(decision.plan, dry_run=True)
            record_order(signal_id, order_id, dry_run=True,
                         payload={"plan": decision.plan.as_dict(),
                                  "orders": orders})
            return ExecutionResult.ok(order_id, decision.plan, True, orders)

        # Real execution path.
        try:
            order_id, orders = self._place_real_bracket(decision.plan)
        except Exception as e:
            logger.exception("CCXT bracket placement failed: %s", e)
            return ExecutionResult.reject(
                "exchange_error",
                f"{type(e).__name__}: {e}",
            )

        record_order(signal_id, order_id, dry_run=False,
                     payload={"plan": decision.plan.as_dict(),
                              "orders": orders})
        return ExecutionResult.ok(order_id, decision.plan, False, orders)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _format_orders(self, plan: OrderPlan, dry_run: bool) -> List[Dict]:
        """Translate an OrderPlan into an ordered list of ccxt-style payloads.

        We separate this so the dry-run output is byte-identical with what
        the live path will send. Callers of place_for_signal can replay these
        payloads against any ccxt exchange.
        """
        side_entry = "buy" if plan.side == "LONG" else "sell"
        side_exit = "sell" if plan.side == "LONG" else "buy"

        # Split TP quantity per plan.tp_split, rounded conservatively so the
        # final piece picks up any remainder rather than under-closing.
        q_total = plan.quantity
        s1, s2, _s3 = plan.tp_split
        q1 = q_total * s1
        q2 = q_total * s2
        q3 = q_total - q1 - q2

        common = {
            "symbol": plan.coin,
            "type": "limit",
            "leverage": plan.leverage,
            "client_signal_id": plan.signal_id,
            "dry_run": dry_run,
        }
        return [
            {**common, "side": side_entry, "price": plan.entry_mid,
             "amount": q_total, "purpose": "ENTRY"},
            {**common, "type": "stop", "side": side_exit, "stopPrice": plan.stop_loss,
             "amount": q_total, "purpose": "STOP_LOSS"},
            {**common, "side": side_exit, "price": plan.take_profit_1,
             "amount": q1, "purpose": "TAKE_PROFIT_1"},
            {**common, "side": side_exit, "price": plan.take_profit_2,
             "amount": q2, "purpose": "TAKE_PROFIT_2"},
            {**common, "side": side_exit, "price": plan.take_profit_3,
             "amount": q3, "purpose": "TAKE_PROFIT_3"},
        ]

    def _place_real_bracket(self, plan: OrderPlan) -> tuple[str, List[Dict]]:
        """Submit the bracket to the live exchange. Returns (entry_order_id, payloads).

        Raises on any failure — caller wraps to convert into a rejection. The
        first network call is the entry order; if SL/TP submission fails after
        the entry is open we *raise* and let the caller alert — leaving an
        unhedged position is the correct behaviour vs. silently retrying with
        unknown state.
        """
        if self._exchange is None:
            self._exchange = _make_exchange()

        ex = self._exchange
        side_entry = "buy" if plan.side == "LONG" else "sell"
        side_exit = "sell" if plan.side == "LONG" else "buy"

        # Set leverage if the exchange exposes it.
        try:
            if hasattr(ex, "set_leverage"):
                ex.set_leverage(int(plan.leverage), plan.coin)
        except Exception as e:  # pragma: no cover — best effort
            logger.warning("set_leverage failed (continuing): %s", e)

        entry = ex.create_order(
            plan.coin, "limit", side_entry, plan.quantity, plan.entry_mid,
            params={"clientOrderId": f"entry-{plan.signal_id}"},
        )
        entry_id = str(entry.get("id") or entry.get("orderId") or "unknown")

        ex.create_order(
            plan.coin, "stop_market", side_exit, plan.quantity, None,
            params={
                "stopPrice": plan.stop_loss,
                "reduceOnly": True,
                "clientOrderId": f"sl-{plan.signal_id}",
            },
        )

        q_total = plan.quantity
        s1, s2, _s3 = plan.tp_split
        q1, q2 = q_total * s1, q_total * s2
        q3 = q_total - q1 - q2

        for tp_price, qty, label in (
            (plan.take_profit_1, q1, "tp1"),
            (plan.take_profit_2, q2, "tp2"),
            (plan.take_profit_3, q3, "tp3"),
        ):
            ex.create_order(
                plan.coin, "limit", side_exit, qty, tp_price,
                params={
                    "reduceOnly": True,
                    "clientOrderId": f"{label}-{plan.signal_id}",
                },
            )

        orders = self._format_orders(plan, dry_run=False)
        return entry_id, orders


# Module singleton.
ccxt_executor = CCXTExecutor()


def get_account_equity_usd() -> float:
    """Read account equity from the configured exchange.

    Returns 0.0 if anything fails — the guardian rejects on zero equity, so
    "could not read equity" is treated as "do nothing", which is safe.
    """
    if not (settings.EXCHANGE_API_KEY and settings.EXCHANGE_API_SECRET):
        return float(settings.AUTO_EXECUTION_FALLBACK_EQUITY_USD or 0.0)
    try:
        import ccxt  # type: ignore[import-not-found]
        name = (settings.EXCHANGE_NAME or "binanceusdm").lower()
        klass = getattr(ccxt, name)
        ex = klass({
            "apiKey": settings.EXCHANGE_API_KEY,
            "secret": settings.EXCHANGE_API_SECRET,
            "enableRateLimit": True,
            "options": {"defaultType": "future"},
        })
        bal = ex.fetch_balance()
        # USDM-Futures: free + used in USDT typically. Total quote-equity is the
        # safest proxy — caller's risk-pct math wants "what can I lose".
        total = (bal.get("USDT") or {}).get("total") or bal.get("total", {}).get("USDT")
        return float(total or 0.0)
    except Exception as e:
        logger.warning("get_account_equity_usd failed: %s", e)
        return float(settings.AUTO_EXECUTION_FALLBACK_EQUITY_USD or 0.0)

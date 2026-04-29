"""
REST endpoints for opt-in CCXT auto-execution.

All routes here are gated on the user explicitly arming auto-execution with a
TOTP code. The arm endpoint is the only way to flip the armed flag — there is
deliberately no `?force=true` escape hatch.

Endpoints:
  GET    /api/execution/status     — armed?, dry-run?, caps, last orders
  POST   /api/execution/arm        — body: {totp, duration_minutes?}
  POST   /api/execution/disarm     — body: {set_by?}
  GET    /api/execution/orders     — recorded order map (idempotency log)
  POST   /api/execution/place      — body: {signal_id} → manual single-shot
  POST   /api/execution/preview    — body: signal | dry sizing without arming
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import settings
from app.execution.account_guardian import account_guardian
from app.execution.ccxt_executor import ccxt_executor, get_account_equity_usd
from app.execution.state import (
    all_recorded_orders,
    count_open_executed_positions,
    get_armed_state,
    set_armed,
    today_realised_pnl_usd,
)
from app.execution.totp import verify_totp
from app.notifications.kill_switch import is_kill_switch_active

logger = logging.getLogger(__name__)

execution_router = APIRouter(prefix="/api/execution", tags=["Execution"])


class ArmRequest(BaseModel):
    totp: str = Field(min_length=6, max_length=8)
    duration_minutes: Optional[int] = Field(default=None, ge=1, le=1440)
    set_by: str = "user"


class DisarmRequest(BaseModel):
    set_by: str = "user"


class PlaceRequest(BaseModel):
    signal_id: str
    force_dry_run: Optional[bool] = None  # override settings.AUTO_EXECUTION_DRY_RUN


class PreviewRequest(BaseModel):
    signal: dict
    equity_usd: Optional[float] = None
    open_positions_count: int = 0
    today_pnl_usd: float = 0.0


@execution_router.get("/status")
async def execution_status() -> dict:
    """Snapshot of the current execution subsystem."""
    cfg = account_guardian.cfg
    armed = get_armed_state()
    return {
        "auto_execution_enabled": settings.AUTO_EXECUTION_ENABLED,
        "dry_run": settings.AUTO_EXECUTION_DRY_RUN,
        "armed": armed,
        "kill_switch_active": is_kill_switch_active(),
        "exchange": settings.EXCHANGE_NAME,
        "exchange_credentials_set": bool(
            settings.EXCHANGE_API_KEY and settings.EXCHANGE_API_SECRET,
        ),
        "totp_configured": bool(settings.EXECUTION_TOTP_SECRET),
        "caps": {
            "max_risk_pct": cfg.max_risk_pct,
            "max_leverage": cfg.max_leverage,
            "max_concurrent_positions": cfg.max_concurrent_positions,
            "daily_loss_limit_pct": cfg.daily_loss_limit_pct,
            "min_confidence_score": cfg.min_confidence_score,
            "min_risk_reward_net": cfg.min_risk_reward_net,
            "min_notional_usd": cfg.min_notional_usd,
            "tp_split": list(cfg.tp_split),
        },
    }


@execution_router.post("/arm")
async def execution_arm(body: ArmRequest) -> dict:
    """Verify TOTP and flip the armed flag for the configured duration."""
    if not settings.AUTO_EXECUTION_ENABLED:
        raise HTTPException(
            status_code=400,
            detail="AUTO_EXECUTION_ENABLED is false. Set it before arming.",
        )
    if not settings.EXECUTION_TOTP_SECRET:
        raise HTTPException(
            status_code=400,
            detail="EXECUTION_TOTP_SECRET is not configured.",
        )

    last_step = (get_armed_state() or {}).get("last_totp_step")
    ok, reason, step = verify_totp(
        settings.EXECUTION_TOTP_SECRET, body.totp, last_used_step=last_step,
    )
    if not ok:
        raise HTTPException(status_code=401, detail=f"TOTP rejected: {reason}")

    duration = body.duration_minutes or settings.AUTO_EXECUTION_ARM_DURATION_MIN
    armed_until = datetime.now(timezone.utc) + timedelta(minutes=duration)
    state = set_armed(True, armed_until=armed_until,
                      last_totp_step=step, set_by=body.set_by)
    return {"ok": True, "armed": state}


@execution_router.post("/disarm")
async def execution_disarm(body: DisarmRequest) -> dict:
    """Disarm immediately. No TOTP needed — disarming should be friction-free."""
    state = set_armed(False, set_by=body.set_by)
    return {"ok": True, "armed": state}


@execution_router.get("/orders")
async def execution_orders() -> dict:
    return {"orders": all_recorded_orders()}


@execution_router.post("/place")
async def execution_place(body: PlaceRequest) -> dict:
    """Manually trigger placement for a single signal id (must already exist)."""
    import asyncio as _aio

    from app.database.models import get_signals  # local import to avoid cycle

    rows = await get_signals(limit=200, is_active=None)
    signal = next((s for s in rows if str(s.get("id")) == body.signal_id), None)
    if signal is None:
        raise HTTPException(status_code=404,
                            detail=f"signal {body.signal_id} not found")

    # ccxt's fetch_balance is synchronous and may block several seconds, so
    # we run it off-thread. open_positions_count and today_pnl_usd come from
    # our own DB / state and are already async.
    equity = await _aio.to_thread(get_account_equity_usd)
    open_count = await count_open_executed_positions()
    today_pnl = await today_realised_pnl_usd()

    # `place_for_signal` itself may issue blocking ccxt orders in non-dry-run
    # mode; wrap to keep the event loop free.
    result = await _aio.to_thread(
        ccxt_executor.place_for_signal,
        signal, equity, open_count, today_pnl, body.force_dry_run,
    )
    return result


@execution_router.post("/preview")
async def execution_preview(body: PreviewRequest) -> dict:
    """Run the guardian against an arbitrary signal dict without placing.

    Useful for testing what *would* happen for a given signal — independent of
    the armed flag and the real exchange. Always safe.
    """
    equity = (
        body.equity_usd
        if body.equity_usd is not None
        else (get_account_equity_usd() or 1000.0)
    )
    decision = account_guardian.evaluate(
        body.signal,
        equity_usd=equity,
        open_positions_count=body.open_positions_count,
        today_pnl_usd=body.today_pnl_usd,
        kill_switch_active=is_kill_switch_active(),
    )
    return {
        "approved": decision.approved,
        "reason": decision.reason,
        "detail": decision.detail,
        "notes": decision.notes,
        "plan": decision.plan.as_dict() if decision.plan else None,
        "equity_used": equity,
    }

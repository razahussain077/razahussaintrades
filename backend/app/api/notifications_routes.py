"""HTTP routes for Telegram push + global kill switch (PR6)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import settings
from app.notifications import (
    is_kill_switch_active,
    kill_switch_status,
    set_kill_switch,
    telegram_client,
)

notifications_router = APIRouter(prefix="/api/notifications", tags=["Notifications"])


@notifications_router.get(
    "/status",
    summary="Diagnostic — Telegram + kill-switch state",
)
async def get_status():
    """Return whether Telegram is configured / enabled and kill-switch state."""
    return {
        "telegram_configured": telegram_client.configured,
        "notifications_enabled": settings.NOTIFICATIONS_ENABLED,
        "dashboard_url": settings.DASHBOARD_URL,
        "kill_switch": kill_switch_status(),
    }


@notifications_router.post(
    "/test",
    summary="Send a Telegram test message",
)
async def post_test():
    """Send a Telegram test message to the configured chat. Useful for
    verifying TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID without waiting for a
    real signal."""
    if not telegram_client.configured:
        return {
            "ok": False,
            "reason": "not_configured",
            "hint": "Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in env.",
        }
    return await telegram_client.send_alert(
        "Razahussain Trades", "Test notification — bot is online and configured.",
    )


class KillSwitchUpdate(BaseModel):
    active: bool
    reason: Optional[str] = None
    set_by: Optional[str] = "user"


@notifications_router.get("/kill-switch", summary="Kill-switch status")
async def get_kill_switch():
    return kill_switch_status()


@notifications_router.post("/kill-switch", summary="Toggle the global kill switch")
async def post_kill_switch(payload: KillSwitchUpdate):
    """Engage or release the global kill switch.

    When engaged:
      * Telegram client returns `{ok:false, reason:"kill_switch_active"}`
        instead of pushing.
      * PR7 auto-execution will refuse to place new orders.
      * The signal scan loop logs the suppression but keeps running.
    """
    state = set_kill_switch(payload.active, reason=payload.reason, set_by=payload.set_by or "user")
    if telegram_client.configured and not payload.active:
        # Notify the user when the kill switch is released so they know push
        # will resume (the engage path is suppressed by the switch itself).
        await telegram_client.send_alert(
            "Kill switch released", f"by {payload.set_by or 'user'}",
        )
    return state


@notifications_router.get(
    "/active",
    summary="Quick boolean — is the kill switch active right now?",
)
async def get_active():
    return {"active": is_kill_switch_active()}

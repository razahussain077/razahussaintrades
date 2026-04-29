"""
Telegram outbound notifier.

Outgoing-only by design — we don't run a polling loop, so the bot can run
without any inbound webhook setup. Inline-keyboard buttons attached to
signal cards point at the dashboard's URL (configurable) and a webhook
endpoint that the user can wire to a public URL when they want command
support; until then the buttons just open the dashboard.

Behaviour is fully gated:
  * If `TELEGRAM_BOT_TOKEN` or `TELEGRAM_CHAT_ID` is empty, every send is a
    no-op (returns `{ok: False, reason: "not_configured"}`).
  * Kill switch (see kill_switch.py) suppresses sends with a non-error
    response so callers don't need to special-case it.
  * Network failures log a warning and return `{ok: False, reason: ...}` —
    they never raise into the signal-generation loop.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

import httpx

from app.config import settings
from app.notifications.kill_switch import is_kill_switch_active

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org"


def _esc(text: Any) -> str:
    """Minimal HTML escape for Telegram parse_mode=HTML."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def format_signal_card(signal: Dict) -> str:
    """Format a signal dict as a Telegram HTML message body.

    Public so tests can verify formatting without hitting the network.
    """
    sig_type = signal.get("signal_type", "?")
    arrow = "🟢 LONG" if sig_type == "LONG" else "🔴 SHORT" if sig_type == "SHORT" else sig_type
    coin = signal.get("coin", "?")
    confidence = signal.get("confidence_score", 0)
    # Field-name compatibility: prefer the canonical Signal model fields
    # (recommended_leverage / take_profit_N / risk_reward[_net]) but fall
    # back to short aliases for tests / synthetic dicts that still use them.
    leverage = signal.get("recommended_leverage") or signal.get("leverage", 0)
    setup = signal.get("setup_type", "—")

    entry_low = signal.get("entry_low")
    entry_high = signal.get("entry_high")
    entry = (
        f"{entry_low:g} – {entry_high:g}"
        if entry_low is not None and entry_high is not None
        else "—"
    )
    sl = signal.get("stop_loss", "—")
    tp1 = signal.get("take_profit_1") or signal.get("tp1", "—")
    tp2 = signal.get("take_profit_2") or signal.get("tp2", "—")
    tp3 = signal.get("take_profit_3") or signal.get("tp3", "—")
    def _fmt_num(x: Any) -> str:
        if isinstance(x, (int, float)):
            return f"{x:g}"
        return _esc(x) if x is not None else "—"

    rr_gross = (
        signal.get("risk_reward")
        or signal.get("rr_ratio")
        or signal.get("rr_gross")
        or "—"
    )
    rr_net = signal.get("risk_reward_net") or signal.get("rr_net") or rr_gross

    reasoning: List[str] = signal.get("reasoning") or []
    reasons_block = "\n".join(f"• {_esc(r)}" for r in reasoning[:6]) or "—"

    return (
        f"<b>{arrow}</b>  <b>{_esc(coin)}</b>   "
        f"<i>conf {_fmt_num(confidence)} · {_fmt_num(leverage)}x</i>\n"
        f"<i>{_esc(setup)}</i>\n"
        f"\n"
        f"<b>Entry:</b> {_esc(entry)}\n"
        f"<b>SL:</b> {_fmt_num(sl)}\n"
        f"<b>TP1 / TP2 / TP3:</b> {_fmt_num(tp1)} / {_fmt_num(tp2)} / {_fmt_num(tp3)}\n"
        f"<b>R:R</b> gross {_fmt_num(rr_gross)} · net {_fmt_num(rr_net)}\n"
        f"\n"
        f"<b>Why:</b>\n{reasons_block}"
    )


def _signal_keyboard(signal: Dict) -> Dict:
    """Inline keyboard with a 'View on dashboard' link + Acknowledge callback."""
    coin = signal.get("coin", "")
    sid = signal.get("id", "")
    dashboard = settings.DASHBOARD_URL.rstrip("/") if settings.DASHBOARD_URL else ""
    rows = []
    if dashboard:
        rows.append([{"text": f"📊 Open {coin}", "url": f"{dashboard}/signals?focus={sid}"}])
    rows.append([
        {"text": "✅ Acknowledge", "callback_data": f"ack:{sid}"},
        {"text": "🛑 Kill switch", "callback_data": "kill:on"},
    ])
    return {"inline_keyboard": rows}


class TelegramClient:
    """Async Telegram bot HTTP client."""

    def __init__(self) -> None:
        self._client: Optional[httpx.AsyncClient] = None
        self._lock = asyncio.Lock()

    @property
    def configured(self) -> bool:
        return bool(settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_CHAT_ID)

    async def _http(self) -> httpx.AsyncClient:
        async with self._lock:
            if self._client is None or self._client.is_closed:
                self._client = httpx.AsyncClient(timeout=15.0)
        return self._client

    async def aclose(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _post(self, method: str, payload: Dict) -> Dict:
        if not self.configured:
            return {"ok": False, "reason": "not_configured"}
        if not settings.NOTIFICATIONS_ENABLED:
            return {"ok": False, "reason": "notifications_disabled"}
        if is_kill_switch_active():
            return {"ok": False, "reason": "kill_switch_active"}
        url = f"{TELEGRAM_API_BASE}/bot{settings.TELEGRAM_BOT_TOKEN}/{method}"
        try:
            client = await self._http()
            resp = await client.post(url, json=payload)
            data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            if resp.status_code != 200 or not data.get("ok", False):
                logger.warning(
                    "Telegram %s failed: status=%s body=%s",
                    method, resp.status_code, str(data)[:200],
                )
                return {"ok": False, "reason": "http_error", "status": resp.status_code, "body": data}
            return {"ok": True, "result": data.get("result")}
        except Exception as e:
            logger.warning("Telegram %s exception: %s", method, e)
            return {"ok": False, "reason": "exception", "error": str(e)}

    async def send_text(self, text: str, parse_mode: str = "HTML",
                        disable_preview: bool = True) -> Dict:
        return await self._post("sendMessage", {
            "chat_id": settings.TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": disable_preview,
        })

    async def send_signal(self, signal: Dict) -> Dict:
        text = format_signal_card(signal)
        return await self._post("sendMessage", {
            "chat_id": settings.TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
            "reply_markup": _signal_keyboard(signal),
        })

    async def send_alert(self, title: str, body: str) -> Dict:
        text = f"<b>⚠️ {_esc(title)}</b>\n{_esc(body)}"
        return await self.send_text(text)

    async def get_me(self) -> Dict:
        return await self._post("getMe", {})


telegram_client = TelegramClient()

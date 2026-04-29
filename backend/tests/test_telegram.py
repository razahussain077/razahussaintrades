"""Tests for Telegram client + kill switch (PR6)."""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.notifications import kill_switch as ks
from app.notifications import telegram as tg


@pytest.fixture(autouse=True)
def _clean_kill_switch_state():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "kill.json")
        prev = os.environ.get("KILL_SWITCH_PATH")
        os.environ["KILL_SWITCH_PATH"] = path
        yield path
        if prev is None:
            os.environ.pop("KILL_SWITCH_PATH", None)
        else:
            os.environ["KILL_SWITCH_PATH"] = prev


# ---------------------------------------------------------------------------
# kill_switch
# ---------------------------------------------------------------------------

class TestKillSwitch:
    def test_default_is_inactive(self):
        assert ks.is_kill_switch_active() is False
        assert ks.kill_switch_status()["active"] is False

    def test_engage_persists_to_disk(self, _clean_kill_switch_state):
        ks.set_kill_switch(True, reason="panic", set_by="test")
        assert ks.is_kill_switch_active() is True
        with open(_clean_kill_switch_state) as f:
            blob = json.load(f)
        assert blob["active"] is True
        assert blob["reason"] == "panic"
        assert blob["set_by"] == "test"

    def test_release_clears_reason(self):
        ks.set_kill_switch(True, reason="panic")
        ks.set_kill_switch(False)
        s = ks.kill_switch_status()
        assert s["active"] is False
        assert s["reason"] is None


# ---------------------------------------------------------------------------
# format_signal_card
# ---------------------------------------------------------------------------

class TestFormatSignalCard:
    def test_long_signal_renders_html(self):
        body = tg.format_signal_card({
            "id": "sig-1",
            "coin": "BTCUSDT",
            "signal_type": "LONG",
            "confidence_score": 78.5,
            "leverage": 5,
            "setup_type": "OB Retest",
            "entry_low": 65000.0, "entry_high": 65200.0,
            "stop_loss": 64500.0, "tp1": 66000, "tp2": 67000, "tp3": 68500,
            "rr_gross": 2.4, "rr_net": 1.9,
            "reasoning": ["bullish OB retest", "CVD divergence", "kill zone active"],
        })
        assert "<b>🟢 LONG</b>" in body
        assert "BTCUSDT" in body
        assert "65000 – 65200" in body
        # HTML escape sanity — angle brackets in user-facing text get encoded.
        body2 = tg.format_signal_card({"coin": "<script>", "signal_type": "LONG"})
        assert "<script>" not in body2
        assert "&lt;script&gt;" in body2

    def test_missing_fields_render_dashes(self):
        body = tg.format_signal_card({"coin": "ETHUSDT", "signal_type": "SHORT"})
        assert "<b>🔴 SHORT</b>" in body
        assert "ETHUSDT" in body
        assert "—" in body  # missing entry/SL

    def test_canonical_signal_model_field_names(self):
        """Regression: signal_scan_loop dumps a Signal model where the keys
        are `take_profit_1` / `recommended_leverage` / `risk_reward[_net]`.
        The card must render those, not silently fall back to placeholders."""
        body = tg.format_signal_card({
            "id": "s1",
            "coin": "BTCUSDT",
            "signal_type": "LONG",
            "confidence_score": 80,
            "recommended_leverage": 7,
            "setup_type": "OB Retest",
            "entry_low": 50000.0, "entry_high": 50100.0,
            "stop_loss": 49500.0,
            "take_profit_1": 51000.0,
            "take_profit_2": 52000.0,
            "take_profit_3": 53000.0,
            "risk_reward": 2.5,
            "risk_reward_net": 2.0,
            "reasoning": ["test"],
        })
        assert "7x" in body
        assert "51000" in body
        assert "52000" in body
        assert "53000" in body
        assert "gross 2.5" in body
        assert "net 2" in body


# ---------------------------------------------------------------------------
# TelegramClient.send_text
# ---------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, status: int, body: dict):
        self.status_code = status
        self.headers = {"content-type": "application/json"}
        self._body = body

    def json(self):
        return self._body


class TestTelegramClient:
    @pytest.mark.asyncio
    async def test_no_op_when_unconfigured(self, monkeypatch):
        monkeypatch.setattr(tg.settings, "TELEGRAM_BOT_TOKEN", "")
        monkeypatch.setattr(tg.settings, "TELEGRAM_CHAT_ID", "")
        result = await tg.TelegramClient().send_text("hi")
        assert result == {"ok": False, "reason": "not_configured"}

    @pytest.mark.asyncio
    async def test_disabled_when_notifications_off(self, monkeypatch):
        monkeypatch.setattr(tg.settings, "TELEGRAM_BOT_TOKEN", "tkn")
        monkeypatch.setattr(tg.settings, "TELEGRAM_CHAT_ID", "123")
        monkeypatch.setattr(tg.settings, "NOTIFICATIONS_ENABLED", False)
        result = await tg.TelegramClient().send_text("hi")
        assert result["ok"] is False
        assert result["reason"] == "notifications_disabled"

    @pytest.mark.asyncio
    async def test_kill_switch_suppresses(self, monkeypatch):
        monkeypatch.setattr(tg.settings, "TELEGRAM_BOT_TOKEN", "tkn")
        monkeypatch.setattr(tg.settings, "TELEGRAM_CHAT_ID", "123")
        monkeypatch.setattr(tg.settings, "NOTIFICATIONS_ENABLED", True)
        ks.set_kill_switch(True, reason="test")
        try:
            result = await tg.TelegramClient().send_text("hi")
            assert result["ok"] is False
            assert result["reason"] == "kill_switch_active"
        finally:
            ks.set_kill_switch(False)

    @pytest.mark.asyncio
    async def test_send_text_round_trip(self, monkeypatch):
        monkeypatch.setattr(tg.settings, "TELEGRAM_BOT_TOKEN", "tkn")
        monkeypatch.setattr(tg.settings, "TELEGRAM_CHAT_ID", "123")
        monkeypatch.setattr(tg.settings, "NOTIFICATIONS_ENABLED", True)
        ks.set_kill_switch(False)

        client = tg.TelegramClient()
        fake_http = AsyncMock()
        fake_http.post = AsyncMock(return_value=_FakeResponse(200, {"ok": True, "result": {"message_id": 7}}))
        fake_http.is_closed = False
        client._client = fake_http

        result = await client.send_text("hi", parse_mode="HTML")
        assert result == {"ok": True, "result": {"message_id": 7}}
        # Ensure the API path embedded the bot token.
        call_url = fake_http.post.call_args.args[0]
        assert "/bottkn/sendMessage" in call_url
        payload = fake_http.post.call_args.kwargs["json"]
        assert payload == {
            "chat_id": "123", "text": "hi",
            "parse_mode": "HTML", "disable_web_page_preview": True,
        }

    @pytest.mark.asyncio
    async def test_http_error_returns_structured_failure(self, monkeypatch):
        monkeypatch.setattr(tg.settings, "TELEGRAM_BOT_TOKEN", "tkn")
        monkeypatch.setattr(tg.settings, "TELEGRAM_CHAT_ID", "123")
        monkeypatch.setattr(tg.settings, "NOTIFICATIONS_ENABLED", True)
        ks.set_kill_switch(False)

        client = tg.TelegramClient()
        fake_http = AsyncMock()
        fake_http.post = AsyncMock(return_value=_FakeResponse(401, {"ok": False, "description": "Unauthorized"}))
        fake_http.is_closed = False
        client._client = fake_http

        result = await client.send_text("hi")
        assert result["ok"] is False
        assert result["reason"] == "http_error"
        assert result["status"] == 401

    @pytest.mark.asyncio
    async def test_send_signal_includes_keyboard(self, monkeypatch):
        monkeypatch.setattr(tg.settings, "TELEGRAM_BOT_TOKEN", "tkn")
        monkeypatch.setattr(tg.settings, "TELEGRAM_CHAT_ID", "123")
        monkeypatch.setattr(tg.settings, "NOTIFICATIONS_ENABLED", True)
        monkeypatch.setattr(tg.settings, "DASHBOARD_URL", "https://example.com")
        ks.set_kill_switch(False)

        client = tg.TelegramClient()
        fake_http = AsyncMock()
        fake_http.post = AsyncMock(return_value=_FakeResponse(200, {"ok": True, "result": {}}))
        fake_http.is_closed = False
        client._client = fake_http

        await client.send_signal({
            "id": "sig-9", "coin": "BTCUSDT", "signal_type": "LONG",
            "confidence_score": 70, "leverage": 3,
            "entry_low": 100.0, "entry_high": 101.0, "stop_loss": 95,
            "tp1": 105, "tp2": 110, "tp3": 115, "rr_gross": 2.0,
            "reasoning": ["test reason"],
        })
        kb = fake_http.post.call_args.kwargs["json"]["reply_markup"]["inline_keyboard"]
        # First row should be the "Open BTCUSDT" link button.
        assert kb[0][0]["url"].startswith("https://example.com/signals?focus=sig-9")
        # Second row should have ack + kill switch.
        callbacks = [b.get("callback_data") for b in kb[1]]
        assert "ack:sig-9" in callbacks
        assert "kill:on" in callbacks

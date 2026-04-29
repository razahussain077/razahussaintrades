"""HTTP-level tests for /api/execution endpoints."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import pyotp
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.execution_routes import execution_router
from app.config import settings
from app.execution import state as exec_state


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("EXECUTION_ARMED_PATH", str(tmp_path / "armed.json"))
    monkeypatch.setenv("EXECUTION_ORDERS_PATH", str(tmp_path / "orders.json"))
    monkeypatch.setenv("KILL_SWITCH_PATH", str(tmp_path / "kill.json"))
    app = FastAPI()
    app.include_router(execution_router)
    return TestClient(app)


def _signal(**overrides) -> Dict[str, Any]:
    base = {
        "id": "sig-route-1",
        "coin": "BTCUSDT",
        "signal_type": "LONG",
        "confidence_score": 88.0,
        "entry_low": 100.0,
        "entry_high": 102.0,
        "stop_loss": 98.0,
        "take_profit_1": 105.0,
        "take_profit_2": 108.0,
        "take_profit_3": 112.0,
        "recommended_leverage": 7.0,
        "risk_reward_net": 2.0,
    }
    base.update(overrides)
    return base


class TestStatus:
    def test_status_reports_caps_and_flags(self, client, monkeypatch):
        monkeypatch.setattr(settings, "AUTO_EXECUTION_ENABLED", False)
        r = client.get("/api/execution/status")
        assert r.status_code == 200
        body = r.json()
        assert body["auto_execution_enabled"] is False
        assert body["armed"]["armed"] is False
        assert "max_risk_pct" in body["caps"]


class TestArm:
    def test_arm_requires_enabled(self, client, monkeypatch):
        monkeypatch.setattr(settings, "AUTO_EXECUTION_ENABLED", False)
        r = client.post("/api/execution/arm", json={"totp": "123456"})
        assert r.status_code == 400
        assert "ENABLED" in r.json()["detail"]

    def test_arm_requires_totp_secret(self, client, monkeypatch):
        monkeypatch.setattr(settings, "AUTO_EXECUTION_ENABLED", True)
        monkeypatch.setattr(settings, "EXECUTION_TOTP_SECRET", "")
        r = client.post("/api/execution/arm", json={"totp": "123456"})
        assert r.status_code == 400
        assert "TOTP_SECRET" in r.json()["detail"]

    def test_arm_with_valid_totp_succeeds(self, client, monkeypatch):
        secret = pyotp.random_base32()
        monkeypatch.setattr(settings, "AUTO_EXECUTION_ENABLED", True)
        monkeypatch.setattr(settings, "EXECUTION_TOTP_SECRET", secret)
        code = pyotp.TOTP(secret).now()

        r = client.post("/api/execution/arm",
                        json={"totp": code, "duration_minutes": 30})
        assert r.status_code == 200, r.json()
        body = r.json()
        assert body["ok"] is True
        assert body["armed"]["armed"] is True
        assert body["armed"]["last_totp_step"] is not None

    def test_arm_replay_rejected(self, client, monkeypatch):
        secret = pyotp.random_base32()
        monkeypatch.setattr(settings, "AUTO_EXECUTION_ENABLED", True)
        monkeypatch.setattr(settings, "EXECUTION_TOTP_SECRET", secret)
        code = pyotp.TOTP(secret).now()

        r1 = client.post("/api/execution/arm", json={"totp": code})
        assert r1.status_code == 200
        # Same code, same step → must be rejected.
        r2 = client.post("/api/execution/arm", json={"totp": code})
        assert r2.status_code == 401
        assert "replay" in r2.json()["detail"]


class TestDisarm:
    def test_disarm_clears_flag(self, client, monkeypatch):
        until = datetime.now(timezone.utc) + timedelta(minutes=5)
        exec_state.set_armed(True, armed_until=until)
        r = client.post("/api/execution/disarm", json={"set_by": "test"})
        assert r.status_code == 200
        assert r.json()["armed"]["armed"] is False


class TestPreview:
    def test_preview_returns_plan_for_good_signal(self, client):
        r = client.post("/api/execution/preview", json={
            "signal": _signal(),
            "equity_usd": 10000.0,
        })
        assert r.status_code == 200, r.json()
        body = r.json()
        assert body["approved"] is True
        assert body["plan"]["coin"] == "BTCUSDT"
        assert body["plan"]["leverage"] <= 5.0  # cap honoured

    def test_preview_returns_reason_for_bad_signal(self, client):
        r = client.post("/api/execution/preview", json={
            "signal": _signal(confidence_score=50.0),
            "equity_usd": 10000.0,
        })
        assert r.status_code == 200
        body = r.json()
        assert body["approved"] is False
        assert body["reason"] == "below_min_confidence"
        assert body["plan"] is None


class TestOrders:
    def test_orders_endpoint_returns_map(self, client):
        exec_state.record_order("sig-route-orders", "ord-1", dry_run=True)
        r = client.get("/api/execution/orders")
        assert r.status_code == 200
        body = r.json()
        assert "sig-route-orders" in body["orders"]

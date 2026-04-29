"""Tests for app/execution/totp.py and app/execution/state.py."""
from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone

import pyotp
import pytest

from app.execution import state as exec_state
from app.execution.totp import _step_for_now, verify_totp


# ---------------------------------------------------------------------------
# TOTP
# ---------------------------------------------------------------------------
class TestTOTP:
    def test_valid_code_accepted(self):
        secret = pyotp.random_base32()
        code = pyotp.TOTP(secret).now()
        ok, reason, step = verify_totp(secret, code)
        assert ok is True
        assert reason == "ok"
        assert step == _step_for_now()

    def test_missing_secret_rejected(self):
        ok, reason, step = verify_totp("", "123456")
        assert ok is False and reason == "totp_secret_not_configured"

    def test_non_digit_code_rejected(self):
        secret = pyotp.random_base32()
        ok, reason, _ = verify_totp(secret, "abcdef")
        assert ok is False and reason == "invalid_code_format"

    def test_wrong_code_rejected(self):
        secret = pyotp.random_base32()
        ok, reason, _ = verify_totp(secret, "000000")
        # Highly unlikely to collide with a real code; if it ever does the
        # next assertion documents that we also reject random digits.
        assert ok is False
        assert reason in ("code_mismatch", "ok")
        if reason == "ok":
            pytest.skip("000000 happened to be a valid code")

    def test_replay_blocked(self):
        secret = pyotp.random_base32()
        code = pyotp.TOTP(secret).now()
        ok, _, step = verify_totp(secret, code)
        assert ok and step is not None
        # Same code, same step → must be rejected as replay.
        ok2, reason2, _ = verify_totp(secret, code, last_used_step=step)
        assert ok2 is False and reason2 == "code_replay_blocked"

    def test_clock_skew_window_accepted(self):
        secret = pyotp.random_base32()
        # Code from one step in the past should still verify.
        past = time.time() - 30
        code = pyotp.TOTP(secret).at(past)
        ok, reason, step = verify_totp(secret, code)
        assert ok is True
        assert step == _step_for_now() - 1


# ---------------------------------------------------------------------------
# State (armed flag + idempotency map)
# ---------------------------------------------------------------------------
class TestArmedState:
    def setup_method(self):
        self.armed_path = "/tmp/test_exec_armed.json"
        self.orders_path = "/tmp/test_exec_orders.json"
        os.environ["EXECUTION_ARMED_PATH"] = self.armed_path
        os.environ["EXECUTION_ORDERS_PATH"] = self.orders_path
        for p in (self.armed_path, self.orders_path):
            if os.path.exists(p):
                os.remove(p)

    def teardown_method(self):
        for p in (self.armed_path, self.orders_path):
            if os.path.exists(p):
                os.remove(p)
        os.environ.pop("EXECUTION_ARMED_PATH", None)
        os.environ.pop("EXECUTION_ORDERS_PATH", None)

    def test_default_disarmed(self):
        assert exec_state.is_armed() is False
        assert exec_state.get_armed_state()["armed"] is False

    def test_arm_and_persist(self):
        until = datetime.now(timezone.utc) + timedelta(minutes=5)
        exec_state.set_armed(True, armed_until=until, last_totp_step=42, set_by="test")
        s = exec_state.get_armed_state()
        assert s["armed"] is True
        assert s["last_totp_step"] == 42
        assert s["set_by"] == "test"
        assert exec_state.is_armed() is True

    def test_auto_disarm_after_until(self):
        past = datetime.now(timezone.utc) - timedelta(minutes=1)
        exec_state.set_armed(True, armed_until=past, last_totp_step=10)
        # On read, lazy auto-disarm.
        assert exec_state.is_armed() is False

    def test_disarm_clears_until(self):
        until = datetime.now(timezone.utc) + timedelta(minutes=5)
        exec_state.set_armed(True, armed_until=until)
        exec_state.set_armed(False)
        s = exec_state.get_armed_state()
        assert s["armed"] is False
        assert s["armed_until"] is None

    def test_disarm_preserves_last_totp_step(self):
        """Replay protection regression — disarming and re-arming with the
        same TOTP code (within the 30s window) must remain blocked."""
        until = datetime.now(timezone.utc) + timedelta(minutes=5)
        exec_state.set_armed(True, armed_until=until, last_totp_step=12345)
        # Disarm without passing last_totp_step.
        exec_state.set_armed(False, set_by="user-panic-button")
        s = exec_state.get_armed_state()
        assert s["armed"] is False
        # Step is preserved so the next arm() call's verify_totp call still
        # rejects code reuse.
        assert s["last_totp_step"] == 12345


class TestIdempotencyMap:
    def setup_method(self):
        self.path = "/tmp/test_exec_orders_idem.json"
        os.environ["EXECUTION_ORDERS_PATH"] = self.path
        if os.path.exists(self.path):
            os.remove(self.path)

    def teardown_method(self):
        if os.path.exists(self.path):
            os.remove(self.path)
        os.environ.pop("EXECUTION_ORDERS_PATH", None)

    def test_record_then_lookup(self):
        assert exec_state.get_recorded_order("sig-1") is None
        exec_state.record_order("sig-1", "order-99", dry_run=True)
        rec = exec_state.get_recorded_order("sig-1")
        assert rec is not None
        assert rec["order_id"] == "order-99"
        assert rec["dry_run"] is True
        assert "placed_at" in rec

    def test_empty_signal_id_no_op(self):
        exec_state.record_order("", "order-x", dry_run=False)
        assert exec_state.all_recorded_orders() == {}

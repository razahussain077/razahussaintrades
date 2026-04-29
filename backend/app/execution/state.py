"""
Persistent execution state — armed flag (with TOTP replay-step), and an
idempotency map of `signal_id → exchange_order_id` to make the
"never place the same trade twice" guarantee survive uvicorn reloads and
process crashes.

Both files live under `./data/`:
  * `execution_armed.json` — `{armed, armed_until, last_totp_step, set_at}`
  * `execution_orders.json` — `{signal_id: {order_id, placed_at, dry_run}}`
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from typing import Dict, Optional

logger = logging.getLogger(__name__)

_ARMED_DEFAULT_PATH = "./data/execution_armed.json"
_ORDERS_DEFAULT_PATH = "./data/execution_orders.json"

_lock = threading.Lock()


def _armed_path() -> str:
    return os.environ.get("EXECUTION_ARMED_PATH", _ARMED_DEFAULT_PATH)


def _orders_path() -> str:
    return os.environ.get("EXECUTION_ORDERS_PATH", _ORDERS_DEFAULT_PATH)


def _load(path: str, default: Dict) -> Dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return dict(default)
    except Exception as e:  # pragma: no cover — corrupt file
        logger.warning("execution-state read failed (%s): %s", path, e)
        return dict(default)


def _save(path: str, state: Dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, default=str)


# ---------------------------------------------------------------------------
# Armed state
# ---------------------------------------------------------------------------
def _armed_default() -> Dict:
    return {
        "armed": False,
        "armed_until": None,
        "last_totp_step": None,
        "set_at": None,
        "set_by": None,
    }


def get_armed_state() -> Dict:
    """Read the current armed state. Auto-disarms if `armed_until` is past."""
    with _lock:
        state = _load(_armed_path(), _armed_default())

    if state.get("armed") and state.get("armed_until"):
        try:
            until = datetime.fromisoformat(state["armed_until"])
        except Exception:
            until = None
        if until is not None and datetime.now(timezone.utc) >= until:
            # Lazily disarm — caller observes a not-armed state without
            # rewriting the file (cheap; rewrite happens on next set_armed).
            state = {
                **state,
                "armed": False,
                "armed_until": None,
            }
    return state


def is_armed() -> bool:
    return bool(get_armed_state().get("armed"))


def set_armed(
    armed: bool,
    armed_until: Optional[datetime] = None,
    last_totp_step: Optional[int] = None,
    set_by: str = "system",
) -> Dict:
    """Persist a new armed state. `armed_until` is only honored when armed=True."""
    with _lock:
        state = _armed_default()
        state["armed"] = bool(armed)
        if armed and armed_until is not None:
            state["armed_until"] = armed_until.astimezone(timezone.utc).isoformat()
        if last_totp_step is not None:
            state["last_totp_step"] = int(last_totp_step)
        state["set_at"] = datetime.now(timezone.utc).isoformat()
        state["set_by"] = set_by
        _save(_armed_path(), state)
    logger.warning(
        "Auto-execution %s by %s (armed_until=%s)",
        "ARMED" if armed else "DISARMED", set_by, state.get("armed_until"),
    )
    return state


# ---------------------------------------------------------------------------
# Idempotency map
# ---------------------------------------------------------------------------
def get_recorded_order(signal_id: str) -> Optional[Dict]:
    """Return the previously-recorded order for this signal, or None."""
    if not signal_id:
        return None
    with _lock:
        state = _load(_orders_path(), {})
    rec = state.get(signal_id)
    return dict(rec) if isinstance(rec, dict) else None


def record_order(signal_id: str, order_id: str, dry_run: bool, payload: Optional[Dict] = None) -> None:
    """Persist an order record; idempotent — repeated calls overwrite, but
    callers must check `get_recorded_order` first to avoid double-placing."""
    if not signal_id:
        return
    with _lock:
        state = _load(_orders_path(), {})
        state[signal_id] = {
            "order_id": str(order_id),
            "placed_at": datetime.now(timezone.utc).isoformat(),
            "dry_run": bool(dry_run),
            "payload": payload or {},
        }
        _save(_orders_path(), state)


def all_recorded_orders() -> Dict:
    with _lock:
        return _load(_orders_path(), {})

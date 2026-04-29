"""
Global kill-switch state. When active, signal generation, Telegram push, and
auto-execution (PR7) all short-circuit.

State is persisted to a small JSON file so it survives backend restarts —
flipping the switch from a panic moment shouldn't be lost when uvicorn
reloads.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from typing import Dict, Optional

logger = logging.getLogger(__name__)

_DEFAULT_PATH = "./data/kill_switch.json"
_lock = threading.Lock()


def _path() -> str:
    return os.environ.get("KILL_SWITCH_PATH", _DEFAULT_PATH)


def _load() -> Dict:
    try:
        with open(_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"active": False, "reason": None, "set_at": None, "set_by": None}
    except Exception as e:
        logger.warning("kill_switch read failed: %s", e)
        return {"active": False, "reason": None, "set_at": None, "set_by": None}


def _save(state: Dict) -> None:
    p = _path()
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def kill_switch_status() -> Dict:
    """Return the current kill-switch state dict."""
    with _lock:
        return _load()


def is_kill_switch_active() -> bool:
    """True iff the kill switch is currently engaged."""
    return bool(kill_switch_status().get("active"))


def set_kill_switch(active: bool, reason: Optional[str] = None, set_by: str = "system") -> Dict:
    """Engage or release the kill switch and persist the new state."""
    with _lock:
        new_state = {
            "active": bool(active),
            "reason": reason if active else None,
            "set_at": datetime.now(timezone.utc).isoformat(),
            "set_by": set_by,
        }
        _save(new_state)
    logger.warning(
        "Kill switch %s by %s (reason: %s)",
        "ENGAGED" if active else "RELEASED", set_by, reason,
    )
    return new_state

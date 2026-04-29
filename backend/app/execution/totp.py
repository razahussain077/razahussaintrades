"""
TOTP (RFC 6238) verification for arming auto-execution.

Auto-execution is **off by default** and must be explicitly armed by the user.
Arming requires a current TOTP code computed from a secret only the user
holds. The secret is read from `EXECUTION_TOTP_SECRET` (base32) — it is *not*
the same as any exchange-2FA secret.

Replay protection: we record the time-step (counter) of the last successfully
used code in the armed-state file. Re-using the same code within its 30s
window after arming is rejected, even if you somehow grabbed the file.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

try:
    import pyotp
    _HAS_PYOTP = True
except ImportError:  # pragma: no cover — pyotp is in requirements.txt
    pyotp = None  # type: ignore
    _HAS_PYOTP = False

logger = logging.getLogger(__name__)

_TOTP_INTERVAL = 30
_VALID_WINDOW = 1  # accept codes within ±30s to allow for clock skew


def _step_for_now(at: Optional[float] = None) -> int:
    """Return the integer time-step (counter) that pyotp would use right now."""
    t = at if at is not None else time.time()
    return int(t // _TOTP_INTERVAL)


def verify_totp(
    secret: str,
    code: str,
    last_used_step: Optional[int] = None,
    at: Optional[float] = None,
) -> tuple[bool, str, Optional[int]]:
    """Verify a TOTP code against the secret.

    Returns `(ok, reason, step_used)`. On success, `step_used` is the integer
    time-step that matched — callers must persist it so the same code cannot be
    replayed from a stolen state file. Returns `(False, "...", None)` on any
    failure.
    """
    if not _HAS_PYOTP:
        return False, "pyotp_not_installed", None
    if not secret:
        return False, "totp_secret_not_configured", None
    if not code or not str(code).strip().isdigit():
        return False, "invalid_code_format", None

    code = str(code).strip()
    totp = pyotp.TOTP(secret)
    now = at if at is not None else time.time()

    # Walk a small window manually so we can identify *which* step matched
    # and thus reject replay.
    current_step = _step_for_now(now)
    for delta in range(-_VALID_WINDOW, _VALID_WINDOW + 1):
        step = current_step + delta
        candidate = totp.at(step * _TOTP_INTERVAL)
        if candidate == code:
            if last_used_step is not None and step <= last_used_step:
                return False, "code_replay_blocked", None
            return True, "ok", step

    return False, "code_mismatch", None

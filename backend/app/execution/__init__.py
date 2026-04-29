"""Auto-execution package — opt-in, off-by-default CCXT bracket order placement."""
from app.execution.account_guardian import (  # noqa: F401
    AccountGuardian,
    GuardianConfig,
    GuardianDecision,
    OrderPlan,
    account_guardian,
)
from app.execution.ccxt_executor import (  # noqa: F401
    CCXTExecutor,
    ExecutionResult,
    ccxt_executor,
    get_account_equity_usd,
)
from app.execution.state import (  # noqa: F401
    all_recorded_orders,
    get_armed_state,
    get_recorded_order,
    is_armed,
    record_order,
    set_armed,
)
from app.execution.totp import verify_totp  # noqa: F401

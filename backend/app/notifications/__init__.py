"""Notifications package — outgoing Telegram push + global kill switch."""
from app.notifications.kill_switch import (
    is_kill_switch_active,
    kill_switch_status,
    set_kill_switch,
)
from app.notifications.telegram import (
    TelegramClient,
    format_signal_card,
    telegram_client,
)

__all__ = [
    "TelegramClient",
    "telegram_client",
    "format_signal_card",
    "is_kill_switch_active",
    "set_kill_switch",
    "kill_switch_status",
]

"""Shared runtime state for the Discord bot."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .bot import ForkliftBot

_running_bot: "ForkliftBot | None" = None
_running_loop: asyncio.AbstractEventLoop | None = None


def register_bot(
    bot: "ForkliftBot", *, loop: asyncio.AbstractEventLoop | None = None
) -> None:
    """Record the active Discord bot and optional loop for cross-thread calls."""
    global _running_bot, _running_loop
    _running_bot = bot
    if loop is not None:
        _running_loop = loop


def get_running_bot() -> "ForkliftBot | None":
    return _running_bot


def get_running_loop() -> asyncio.AbstractEventLoop | None:
    if _running_loop is not None:
        return _running_loop
    if _running_bot is not None:
        try:
            return _running_bot.loop  # type: ignore[return-value]
        except AttributeError:
            return None
    return None

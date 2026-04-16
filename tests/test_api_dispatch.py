"""Tests for _dispatch_to_cog in asu_discord/api.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from asu_discord.api import DiscordAPIError, _dispatch_to_cog


def _make_cog():
    cog = MagicMock()
    cog.some_action = AsyncMock(return_value=None)
    return cog


def _make_bot(cog=None):
    bot = MagicMock()
    bot.get_cog.return_value = cog
    return bot


def _running_loop():
    import asyncio
    loop = asyncio.new_event_loop()
    return loop


class TestDispatchToCog:
    def test_raises_when_bot_not_running(self):
        with patch("asu_discord.api.get_running_bot", return_value=None), \
             patch("asu_discord.api.get_running_loop", return_value=None):
            with pytest.raises(DiscordAPIError, match="not running"):
                _dispatch_to_cog("123", lambda cog, uid: cog.some_action(uid), action="test")

    def test_raises_when_loop_closed(self):
        import asyncio
        closed_loop = asyncio.new_event_loop()
        closed_loop.close()
        bot = _make_bot()

        with patch("asu_discord.api.get_running_bot", return_value=bot), \
             patch("asu_discord.api.get_running_loop", return_value=closed_loop):
            with pytest.raises(DiscordAPIError, match="not running"):
                _dispatch_to_cog("123", lambda cog, uid: cog.some_action(uid), action="test")

    def test_raises_on_invalid_user_id(self):
        import asyncio
        loop = asyncio.new_event_loop()
        bot = _make_bot()

        with patch("asu_discord.api.get_running_bot", return_value=bot), \
             patch("asu_discord.api.get_running_loop", return_value=loop):
            try:
                with pytest.raises(DiscordAPIError, match="Invalid Discord user id"):
                    _dispatch_to_cog("not-a-number", lambda cog, uid: cog.some_action(uid), action="test")
            finally:
                loop.close()

    def test_raises_when_cog_not_loaded(self):
        import asyncio
        loop = asyncio.new_event_loop()
        bot = _make_bot(cog=None)

        with patch("asu_discord.api.get_running_bot", return_value=bot), \
             patch("asu_discord.api.get_running_loop", return_value=loop):
            try:
                with pytest.raises(DiscordAPIError, match="not loaded"):
                    _dispatch_to_cog("123", lambda cog, uid: cog.some_action(uid), action="test")
            finally:
                loop.close()

    def test_raises_when_cog_wrong_type(self):
        import asyncio
        loop = asyncio.new_event_loop()
        bot = _make_bot(cog=MagicMock())

        with patch("asu_discord.api.get_running_bot", return_value=bot), \
             patch("asu_discord.api.get_running_loop", return_value=loop):
            try:
                with pytest.raises(DiscordAPIError, match="not loaded"):
                    _dispatch_to_cog("123", lambda cog, uid: cog.some_action(uid), action="test")
            finally:
                loop.close()

    def test_error_message_includes_action(self):
        with patch("asu_discord.api.get_running_bot", return_value=None), \
             patch("asu_discord.api.get_running_loop", return_value=None):
            with pytest.raises(DiscordAPIError) as exc_info:
                _dispatch_to_cog("123", lambda cog, uid: cog.some_action(uid), action="assign verified role")
            assert "assign verified role" in str(exc_info.value)

"""Tests for the QnA cog's chatbot follow-ups — Discord and CreateAI mocked."""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from asu_discord.cogs.forklift_qna import RATING_PROMPT
from asu_discord.cogs.qna import MAX_USER_TURNS, QnACog, _split_message

BOT_ID, OWNER_ID, THREAD_ID, FORUM_ID = 1, 2, 100, 50


def test_split_message():
    assert _split_message("short") == ["short"]
    chunks = _split_message("a" * 1500 + "\n" + "b" * 1500)
    assert chunks == ["a" * 1500, "b" * 1500]
    assert [len(c) for c in _split_message("x" * 4500)] == [2000, 2000, 500]


def _msg(author_id: int, content: str, *, buttons: bool = False) -> MagicMock:
    msg = MagicMock()
    msg.author.id = author_id
    msg.content = content
    msg.edit = AsyncMock()
    component = SimpleNamespace(custom_id="qna:satisfied")
    msg.components = [SimpleNamespace(children=[component])] if buttons else []
    return msg


def _thread(history_newest_first: list) -> MagicMock:
    thread = MagicMock(spec=discord.Thread)
    thread.id = THREAD_ID
    thread.name = "Housing"
    thread.parent_id = FORUM_ID
    thread.owner_id = OWNER_ID
    thread.guild.id = 9
    thread.send = AsyncMock(side_effect=lambda *a, **k: _msg(BOT_ID, a[0] if a else ""))

    async def history(**_):
        for m in history_newest_first:
            yield m

    thread.history = history
    thread.typing = MagicMock(return_value=AsyncMock())
    return thread


@contextmanager
def _cog(status: str | None = "satisfied", answer: str = "Tempe has dorms."):
    record = SimpleNamespace(status=status) if status else None
    db = MagicMock()
    db.query.return_value.filter_by.return_value.one_or_none.return_value = record

    @contextmanager
    def session_scope():
        yield db

    bot = MagicMock()
    bot.user.id = BOT_ID
    cog = QnACog(bot)
    with (
        patch("asu_discord.cogs.qna.session_scope", session_scope),
        patch.object(QnACog, "forum_channel_id", FORUM_ID),
        patch.object(QnACog, "helper_role_id", None),
        patch.object(cog, "_is_ready", return_value=True),
        patch.object(cog, "_is_enabled", return_value=True),
        patch("asu_discord.cogs.qna.ForkmanQNA") as qna_cls,
    ):
        qna_cls.return_value.get_answer.return_value = {
            "ok": True, "answer": answer, "rating_prompt": RATING_PROMPT,
        }
        yield cog, qna_cls.return_value.get_answer, record


async def test_owner_follow_up_gets_answer_with_history():
    previous = _msg(BOT_ID, f"Dorms open in August.\n\n{RATING_PROMPT}", buttons=True)
    thread = _thread([
        previous,
        _msg(BOT_ID, f"Hi <@{OWNER_ID}>, I'm Forkman"),  # greeting, skipped
        _msg(OWNER_ID, "When do dorms open?"),
    ])
    message = _msg(OWNER_ID, "Which campus?")
    message.channel = thread
    message.author.bot = False

    with _cog() as (cog, get_answer, _):
        await cog.on_message(message)

    kwargs = get_answer.call_args.kwargs
    assert kwargs["message_content"] == "Which campus?"
    assert kwargs["history"] == [
        ("User", "When do dorms open?"),
        ("Forkman", "Dorms open in August."),
    ]
    sent = thread.send.call_args
    assert sent.args[0].startswith("Tempe has dorms.")
    assert sent.kwargs["view"] is not None
    previous.edit.assert_awaited_once_with(view=None)


@pytest.mark.parametrize("author_id,status", [(3, "satisfied"), (OWNER_ID, "needs_help"), (OWNER_ID, None)])
async def test_follow_up_ignored(author_id, status):
    thread = _thread([])
    message = _msg(author_id, "hello?")
    message.channel = thread
    message.author.bot = False

    with _cog(status=status) as (cog, get_answer, _):
        await cog.on_message(message)

    get_answer.assert_not_called()
    thread.send.assert_not_called()


async def test_long_thread_hands_off_to_staff():
    thread = _thread([_msg(OWNER_ID, f"q{i}") for i in range(MAX_USER_TURNS)])
    message = _msg(OWNER_ID, "one more")
    message.channel = thread
    message.author.bot = False

    with _cog() as (cog, get_answer, record):
        await cog.on_message(message)

    get_answer.assert_not_called()
    assert "Assistance requested" in thread.send.call_args.args[0]
    assert record.status == "needs_help"

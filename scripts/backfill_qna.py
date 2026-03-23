#!/usr/bin/env python3
"""
Backfill QnaPost records and GoldGuideContribution records from Discord history.

For every thread in the QnA forum channel (all time, no date restriction):
  - Create or update a QnaPost row with status, tags, answer metadata
  - For every message by a current Gold Guide member: insert a GoldGuideContribution row

Run once after deploying the schema changes. Safe to re-run — all inserts are
idempotent (skips existing rows by thread_id / message_id).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

ENV_PATH = PROJECT_ROOT / ".env"

GUILD_ID = 1187144343400751234
GOLD_GUIDE_ROLE_ID = 1187156709597270157

SATISFACTORY_CUSTOM_ID = "qna:satisfied"
ASSISTANCE_CUSTOM_ID = "qna:assist"

CONFIRMATION_KEYWORDS = (
    "correct", "that's right", "that is right", "you're right",
    "forkman is right", "bot is right", "bot got it", "exactly right",
    "exactly", "spot on", "confirmed", "this is accurate", "this is correct",
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("\"'")
        if key:
            os.environ.setdefault(key, value)


def _has_feedback_buttons(msg) -> bool:
    for action_row in msg.components:
        for component in action_row.children:
            if getattr(component, "custom_id", None) in (SATISFACTORY_CUSTOM_ID, ASSISTANCE_CUSTOM_ID):
                return True
    return False


async def _classify_and_extract(thread, bot_id: int, gold_guide_ids: set[int]) -> dict:
    """
    Returns:
      status          – 'satisfied' | 'needs_help' | 'pending' | 'no_bot_msg'
      tags            – list[str]
      answer_text     – str | None
      assistant_msg_id– str | None
      gold_guide_msgs – list of (message_id, author_id, author_name, created_at)
    """
    result = {
        "status": "no_bot_msg",
        "answer_text": None,
        "assistant_msg_id": None,
        "gold_guide_msgs": [],
    }

    messages = []
    try:
        async for msg in thread.history(limit=None, oldest_first=True):
            messages.append(msg)
    except Exception as exc:
        logger.warning("Could not read thread %s: %s", thread.id, exc)
        return result

    original_poster_id = messages[0].author.id if messages else None
    assistance_idx = None

    for i, msg in enumerate(messages):
        if msg.author.id == bot_id:
            if "Assistance requested" in msg.content:
                assistance_idx = i
                result["status"] = "needs_help"
                result["answer_text"] = result.get("answer_text")  # keep existing
            elif _has_feedback_buttons(msg):
                if result["status"] not in ("needs_help",):
                    result["status"] = "pending"
                if result["assistant_msg_id"] is None:
                    result["assistant_msg_id"] = str(msg.id)
                    result["answer_text"] = msg.content or None
            else:
                if result["assistant_msg_id"] is None and "Hi <@" not in msg.content:
                    result["assistant_msg_id"] = str(msg.id)
                    result["answer_text"] = msg.content or None
                if result["status"] == "no_bot_msg":
                    result["status"] = "satisfied"
        elif msg.author.id in gold_guide_ids:
            # Only record after assistance was requested, or any message in the thread
            result["gold_guide_msgs"].append((
                str(msg.id),
                str(msg.author.id),
                msg.author.name,
                msg.created_at.replace(tzinfo=None),
            ))

    return result


async def run(*, forum_channel_id: int) -> None:
    try:
        import discord
    except ImportError as exc:
        raise SystemExit("discord.py is not installed.") from exc

    # Import DB after env is loaded so DATABASE_URL is set
    from utils.database import GoldGuideContribution, QnaPost, init_db, session_scope

    init_db()

    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        raise SystemExit("DISCORD_BOT_TOKEN not set.")

    intents = discord.Intents.default()
    intents.guilds = True
    intents.message_content = True
    intents.members = True

    client = discord.Client(intents=intents)
    posts_upserted = 0
    contributions_inserted = 0

    @client.event
    async def on_ready() -> None:
        nonlocal posts_upserted, contributions_inserted
        logger.info("Connected as %s", client.user)

        guild = client.get_guild(GUILD_ID)
        if guild is None:
            logger.error("Guild %d not found.", GUILD_ID)
            await client.close()
            return

        # Build Gold Guide member ID set from current role members
        gold_guide_role = guild.get_role(GOLD_GUIDE_ROLE_ID)
        if gold_guide_role is None:
            logger.warning("Gold Guide role %d not found — no contribution records will be created.", GOLD_GUIDE_ROLE_ID)
            gold_guide_ids: set[int] = set()
        else:
            gold_guide_ids = {m.id for m in gold_guide_role.members}
            logger.info("Gold Guide members found: %d", len(gold_guide_ids))

        forum_channel = guild.get_channel(forum_channel_id)
        if not isinstance(forum_channel, discord.ForumChannel):
            logger.error("Channel %d is not a ForumChannel.", forum_channel_id)
            await client.close()
            return

        tag_name_by_id = {t.id: t.name for t in forum_channel.available_tags}
        logger.info("Forum: #%s — fetching all threads...", forum_channel.name)

        seen: dict[int, discord.Thread] = {}
        async for thread in forum_channel.archived_threads(limit=None):
            seen[thread.id] = thread
        for thread in forum_channel.threads:
            seen[thread.id] = thread

        all_threads = list(seen.values())
        logger.info("Total threads: %d", len(all_threads))

        bot_id = client.user.id

        for i, thread in enumerate(all_threads):
            tag_names = [tag_name_by_id.get(t.id, str(t.id)) for t in thread.applied_tags]
            has_gold_guide_tag = any("gold guide" in n.lower() for n in tag_names)

            info = await _classify_and_extract(thread, bot_id, gold_guide_ids)
            created_at = thread.created_at.replace(tzinfo=None) if thread.created_at else datetime.utcnow()

            with session_scope() as db_session:
                record = db_session.query(QnaPost).filter_by(thread_id=str(thread.id)).one_or_none()
                if record is None:
                    record = QnaPost(
                        guild_id=str(guild.id),
                        channel_id=str(forum_channel.id),
                        thread_id=str(thread.id),
                        title=thread.name,
                        tags=json.dumps(tag_names),
                        status=info["status"],
                        answer=info["answer_text"],
                        assistant_message_id=info["assistant_msg_id"],
                        gold_guide_pinged=has_gold_guide_tag,
                        created_at=created_at,
                    )
                    db_session.add(record)
                    posts_upserted += 1
                else:
                    # Update fields that may have been missing
                    if record.tags is None:
                        record.tags = json.dumps(tag_names)
                    if record.status in (None, "pending") and info["status"] != "no_bot_msg":
                        record.status = info["status"]
                    if record.answer is None and info["answer_text"]:
                        record.answer = info["answer_text"]
                    if record.assistant_message_id is None and info["assistant_msg_id"]:
                        record.assistant_message_id = info["assistant_msg_id"]
                    if not record.gold_guide_pinged and has_gold_guide_tag:
                        record.gold_guide_pinged = True
                    posts_upserted += 1

                # Insert Gold Guide contributions (deduplicated by message_id)
                parent_name = forum_channel.name
                for msg_id, author_id, author_name, responded_at in info["gold_guide_msgs"]:
                    if not db_session.query(GoldGuideContribution).filter_by(message_id=msg_id).one_or_none():
                        db_session.add(GoldGuideContribution(
                            guild_id=str(guild.id),
                            channel_id=str(forum_channel.id),
                            channel_name=parent_name,
                            thread_id=str(thread.id),
                            thread_title=thread.name,
                            message_id=msg_id,
                            responder_discord_id=author_id,
                            responder_username=author_name,
                            responded_at=responded_at,
                        ))
                        contributions_inserted += 1

            if (i + 1) % 25 == 0:
                logger.info("Processed %d / %d threads...", i + 1, len(all_threads))

        logger.info("Done. Posts upserted: %d  |  Contributions inserted: %d", posts_upserted, contributions_inserted)
        await client.close()

    await client.start(token)


def main() -> None:
    load_env(ENV_PATH)

    raw = os.environ.get("QNA_FORUM_CHANNEL_ID", "")
    try:
        forum_channel_id = int(raw)
    except (TypeError, ValueError):
        raise SystemExit(f"QNA_FORUM_CHANNEL_ID is not set or invalid: {raw!r}")

    asyncio.run(run(forum_channel_id=forum_channel_id))


if __name__ == "__main__":
    main()

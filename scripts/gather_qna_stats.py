#!/usr/bin/env python3
"""
Gather QnA forum channel statistics (November 2025 – February 2026):
  - Posts per forum tag
  - Posts answered by bot   (bot answer message buttons removed, no "Assistance requested" message)
  - Posts where user called for staff (bot sent a visible "Assistance requested." message)
  - Posts pending (bot answer message still has feedback buttons)

Standalone script — no database, no project imports.

Status detection mirrors qna.py cog behaviour:
  - On "It was great!":     bot edits answer msg to remove buttons (ephemeral thank-you, not in history)
  - On "I still need help": bot edits answer msg to remove buttons AND posts visible "Assistance requested."
  - Pending:                answer message still carries the two feedback buttons
"""
from __future__ import annotations

import asyncio
import logging
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"

GUILD_ID = 1187144343400751234
SINCE = datetime(2025, 11, 1, tzinfo=timezone.utc)
UNTIL = datetime(2026, 3, 1, tzinfo=timezone.utc)  # exclusive — covers through end of Feb 2026

# Custom IDs used by QnAFeedbackView in qna.py
SATISFACTORY_CUSTOM_ID = "qna:satisfied"
ASSISTANCE_CUSTOM_ID = "qna:assist"

# Additional forum channel to report tag usage stats for
EXTRA_FORUM_ID = 1435339065720311849

# Campus channels to track post counts for the same date range
CAMPUS_CHANNELS: dict[str, int] = {
    "Tempe":         1435709161064103966,
    "Downtown":      1435710270755442748,
    "Poly":          1435710785287356546,
    "West Valley":   1435711047578419290,
    "LA":            1435711441452798003,
    "Off Campus":    1435703689015853097,
}

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("\"'")
        if key:
            env[key] = value
    return env


def apply_env(env: dict[str, str]) -> None:
    for key, value in env.items():
        os.environ.setdefault(key, value)


DISCORD_EPOCH_MS = 1420070400000  # Discord snowflake epoch in milliseconds


def _snowflake_time(snowflake_id: int) -> datetime:
    """Derive UTC creation time from a Discord snowflake ID."""
    ms = (snowflake_id >> 22) + DISCORD_EPOCH_MS
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


async def _fetch_all_threads_in_range(http, channel_id: int) -> list[int]:
    """
    Fetch all public archived thread IDs for a channel via raw REST API,
    filtered to SINCE <= created_at < UNTIL using snowflake time.
    Handles pagination automatically.
    """
    thread_ids: list[int] = []
    before: str | None = None

    while True:
        kwargs: dict = {"limit": 100}
        if before:
            kwargs["before"] = before

        data = await http.get_public_archived_threads(channel_id, **kwargs)
        threads = data.get("threads", [])

        logger.debug(
            "  channel=%d page has_more=%s thread_count=%d",
            channel_id, data.get("has_more"), len(threads),
        )

        if not threads:
            break

        for t in threads:
            tid = int(t["id"])
            created_at = _snowflake_time(tid)
            logger.debug("    thread id=%s created_at=%s type=%s", t["id"], created_at, t.get("type"))
            if created_at < SINCE:
                logger.debug("    -> before SINCE, stopping pagination")
                return thread_ids
            if created_at < UNTIL:
                thread_ids.append(tid)
            else:
                logger.debug("    -> after UNTIL, skipping")

        if not data.get("has_more", False):
            break

        before = threads[-1]["id"]

    return thread_ids


def _has_feedback_buttons(msg) -> bool:
    """Return True if the message still carries the QnA feedback buttons."""
    for action_row in msg.components:
        for component in action_row.children:
            if getattr(component, "custom_id", None) in (
                SATISFACTORY_CUSTOM_ID,
                ASSISTANCE_CUSTOM_ID,
            ):
                return True
    return False


async def classify_thread(thread, bot_id: int) -> str:
    """
    Scan the thread's message history and return one of:
      'satisfied'  – bot answered, user was happy (buttons removed, no assistance msg)
      'needs_help' – user called for staff (bot posted visible "Assistance requested.")
      'pending'    – feedback buttons still present on bot's answer
      'no_bot_msg' – bot never posted (thread predates cog or cog was off)
    """
    try:
        async for msg in thread.history(limit=50, oldest_first=True):
            if msg.author.id != bot_id:
                continue

            # Visible "Assistance requested." = user clicked needs_help
            if "Assistance requested" in msg.content:
                return "needs_help"

            # Still has feedback buttons = pending
            if _has_feedback_buttons(msg):
                return "pending"

        # Bot posted but buttons are gone and no assistance message = satisfied
        # (Check whether the bot posted at all)
        async for msg in thread.history(limit=50, oldest_first=True):
            if msg.author.id == bot_id:
                return "satisfied"

    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not read history for thread %s: %s", thread.id, exc)

    return "no_bot_msg"


async def run(*, forum_channel_id: int) -> None:
    try:
        import discord
    except ImportError as exc:
        raise SystemExit("discord.py is not installed.") from exc

    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        raise SystemExit("DISCORD_BOT_TOKEN is not set in the environment or .env.")

    intents = discord.Intents.default()
    intents.guilds = True
    intents.message_content = True

    client = discord.Client(intents=intents)

    tag_counts: dict[str, int] = defaultdict(int)
    status_counts: dict[str, int] = defaultdict(int)
    campus_counts: dict[str, int] = {}
    extra_forum_tag_counts: dict[str, int] = defaultdict(int)
    extra_forum_total = 0
    total_threads = 0

    @client.event
    async def on_ready() -> None:
        nonlocal total_threads, campus_counts, extra_forum_tag_counts, extra_forum_total
        logger.info("Connected to Discord as %s.", client.user)

        guild = client.get_guild(GUILD_ID)
        if guild is None:
            logger.error("Guild %d not found.", GUILD_ID)
            await client.close()
            return

        forum_channel = guild.get_channel(forum_channel_id)
        if not isinstance(forum_channel, discord.ForumChannel):
            logger.error(
                "Channel %d is not a ForumChannel (got %s).",
                forum_channel_id,
                type(forum_channel).__name__,
            )
            await client.close()
            return

        logger.info("Forum channel: #%s (%d).", forum_channel.name, forum_channel.id)

        tag_name_by_id: dict[int, str] = {
            t.id: t.name for t in forum_channel.available_tags
        }
        logger.info("Available tags: %s", list(tag_name_by_id.values()))

        logger.info("Fetching archived threads (may take a while)...")
        seen_qna: dict[int, discord.Thread] = {}
        async for thread in forum_channel.archived_threads(limit=None):
            if thread.created_at and SINCE <= thread.created_at < UNTIL:
                seen_qna[thread.id] = thread
        for thread in forum_channel.threads:
            if thread.created_at and SINCE <= thread.created_at < UNTIL:
                seen_qna[thread.id] = thread
        all_threads = list(seen_qna.values())

        total_threads = len(all_threads)
        logger.info("Total threads to process: %d", total_threads)

        bot_id = client.user.id

        for i, thread in enumerate(all_threads):
            status = await classify_thread(thread, bot_id)
            status_counts[status] += 1

            thread_tags = [
                tag_name_by_id.get(t.id, str(t.id)) for t in thread.applied_tags
            ]
            for tag_name in thread_tags:
                tag_counts[tag_name] += 1
            if not thread_tags:
                tag_counts["(no tag)"] += 1

            if (i + 1) % 25 == 0:
                logger.info("Processed %d / %d threads...", i + 1, total_threads)

        # Tag usage stats for the extra forum channel
        logger.info("Fetching tag stats for extra forum %d...", EXTRA_FORUM_ID)
        extra_forum = guild.get_channel(EXTRA_FORUM_ID)
        if isinstance(extra_forum, discord.ForumChannel):
            extra_tag_name_by_id = {t.id: t.name for t in extra_forum.available_tags}
            seen_extra: dict[int, discord.Thread] = {}
            async for thread in extra_forum.archived_threads(limit=None):
                if thread.created_at and SINCE <= thread.created_at < UNTIL:
                    seen_extra[thread.id] = thread
            for thread in extra_forum.threads:
                if thread.created_at and SINCE <= thread.created_at < UNTIL:
                    seen_extra[thread.id] = thread
            extra_threads = list(seen_extra.values())
            for thread in extra_threads:
                thread_tags = [
                    extra_tag_name_by_id.get(t.id, str(t.id)) for t in thread.applied_tags
                ]
                for tag_name in thread_tags:
                    extra_forum_tag_counts[tag_name] += 1
                if not thread_tags:
                    extra_forum_tag_counts["(no tag)"] += 1
            extra_forum_total = len(extra_threads)
            logger.info("Extra forum total threads: %d", extra_forum_total)
        else:
            logger.warning(
                "Extra forum channel %d not found or not a ForumChannel.", EXTRA_FORUM_ID
            )

        # Count posts in each campus channel over the same date range
        logger.info("Counting posts in campus channels...")
        for campus_name, channel_id in CAMPUS_CHANNELS.items():
            try:
                channel = await guild.fetch_channel(channel_id)
            except discord.NotFound:
                logger.warning("Campus channel '%s' (%d) not found.", campus_name, channel_id)
                campus_counts[f"{campus_name} ({channel_id})"] = -1
                continue
            except discord.HTTPException as exc:
                logger.warning("Failed to fetch campus channel '%s': %s", campus_name, exc)
                campus_counts[f"{campus_name} ({channel_id})"] = -1
                continue

            display_name = channel.name

            # Use raw REST API to fetch archived threads — bypasses py-cord type classification
            archived_ids = set(await _fetch_all_threads_in_range(client.http, channel_id))

            # Also check active threads via the cache (derived creation time from snowflake)
            active_ids = {
                t.id for t in getattr(channel, "threads", [])
                if SINCE <= _snowflake_time(t.id) < UNTIL
            }

            count = len(archived_ids | active_ids)
            campus_counts[display_name] = count
            logger.info("  %s: %d posts", display_name, count)

        await client.close()

    await client.start(token)

    status_labels = {
        "satisfied": "Answered by bot (user satisfied)",
        "needs_help": "Called for staff assistance (user not satisfied)",
        "pending": "Pending (feedback buttons still active)",
        "no_bot_msg": "No bot message found",
    }

    print(f"\n{'=' * 45}")
    print("  QnA Forum Statistics")
    print("  November 2025 – February 2026")
    print(f"{'=' * 45}")
    print(f"Total posts: {total_threads}")

    print("\n-- By Status --")
    for status, count in sorted(status_counts.items(), key=lambda x: -x[1]):
        label = status_labels.get(status, status)
        pct = (count / total_threads * 100) if total_threads else 0
        print(f"  {label}: {count} ({pct:.1f}%)")

    print("\n-- By Tag --")
    for tag, count in sorted(tag_counts.items(), key=lambda x: -x[1]):
        pct = (count / total_threads * 100) if total_threads else 0
        print(f"  {tag}: {count} ({pct:.1f}%)")

    print(f"\n-- Forum {EXTRA_FORUM_ID} — Tag Usage ({extra_forum_total} total posts) --")
    if extra_forum_tag_counts:
        for tag, count in sorted(extra_forum_tag_counts.items(), key=lambda x: -x[1]):
            pct = (count / extra_forum_total * 100) if extra_forum_total else 0
            print(f"  {tag}: {count} ({pct:.1f}%)")
    else:
        print("  (no data — channel not found or no posts in range)")

    print("\n-- Posts by Campus Channel --")
    for campus_name, count in campus_counts.items():
        if count == -1:
            print(f"  {campus_name} - (channel not found)")
        else:
            print(f"  {campus_name} - {count}")

    print()


def main() -> None:
    env = load_env(ENV_PATH)
    apply_env(env)

    raw_channel_id = os.environ.get("QNA_FORUM_CHANNEL_ID", "")
    try:
        forum_channel_id = int(raw_channel_id)
    except (TypeError, ValueError):
        raise SystemExit(
            f"QNA_FORUM_CHANNEL_ID is not set or invalid: {raw_channel_id!r}"
        )

    asyncio.run(run(forum_channel_id=forum_channel_id))


if __name__ == "__main__":
    main()

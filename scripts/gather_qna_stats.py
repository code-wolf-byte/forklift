#!/usr/bin/env python3
"""
Gather QnA forum channel statistics (November 2025 – February 2026).

Four primary metrics
--------------------
1. Total posts created
2. Total messages sent (across all threads)
3. Questions answered by the bot
   - User clicked "It was great!" (satisfied)
   - OR staff replied and confirmed the bot was correct
4. Questions answered by ASU Staff
   - Staff posted a substantive reply after "Assistance requested."
   - (i.e. staff replied but did NOT just confirm the bot)

Staff confirmation heuristic
-----------------------------
After the "Assistance requested." message, if a non-bot / non-OP member posts a
message whose text contains one of CONFIRMATION_KEYWORDS the reply is counted as
"staff confirmed bot" (credit goes to the bot); otherwise it is counted as
"staff answered".

Standalone script — no database, no project imports.
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

# Campus text channels to track message counts for the same date range
CAMPUS_CHANNELS: dict[str, int] = {
    "Tempe":         1435709161064103966,
    "Downtown":      1435710270755442748,
    "Poly":          1435710785287356546,
    "West Valley":   1435711047578419290,
    "LA":            1435711441452798003,
}

# Category whose forum channels are all counted for thread posts
CAMPUS_FORUMS_CATEGORY_ID = 1435690325917175928

# Keywords that indicate a staff member is confirming the bot rather than providing a new answer.
# Matched case-insensitively against the full message content.
CONFIRMATION_KEYWORDS = (
    "correct",
    "that's right",
    "that is right",
    "you're right",
    "forkman is right",
    "bot is right",
    "bot got it",
    "exactly right",
    "exactly",
    "spot on",
    "confirmed",
    "this is accurate",
    "this is correct",
)

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


async def classify_thread(thread, bot_id: int) -> dict:
    """
    Fetch all messages in the thread once and return:

      msg_count       – total number of messages in the thread
      bot_answered    – bot posted an answer (buttons present or removed)
      status          – 'satisfied' | 'needs_help' | 'pending' | 'no_bot_msg'
      staff_replied   – a non-bot non-OP member replied after "Assistance requested."
      staff_confirmed – that staff reply confirmed the bot (keyword match)

    Final credit buckets (computed in caller):
      bot_credit   = satisfied  OR  (needs_help AND staff_confirmed)
      staff_credit = needs_help AND staff_replied AND NOT staff_confirmed
    """
    result: dict = {
        "msg_count": 0,
        "bot_answered": False,
        "status": "no_bot_msg",
        "staff_replied": False,
        "staff_confirmed": False,
    }

    messages: list = []
    try:
        async for msg in thread.history(limit=None, oldest_first=True):
            messages.append(msg)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not read history for thread %s: %s", thread.id, exc)
        return result

    result["msg_count"] = len(messages)

    # Original poster = author of the first message
    original_poster_id: int | None = messages[0].author.id if messages else None

    assistance_idx: int | None = None

    for i, msg in enumerate(messages):
        if msg.author.id != bot_id:
            continue

        if "Assistance requested" in msg.content:
            assistance_idx = i
            result["status"] = "needs_help"
            result["bot_answered"] = True
            continue

        if _has_feedback_buttons(msg):
            if result["status"] not in ("needs_help",):
                result["status"] = "pending"
            result["bot_answered"] = True
            continue

        # Bot message without buttons and without "Assistance requested" = satisfied answer
        result["bot_answered"] = True
        if result["status"] == "no_bot_msg":
            result["status"] = "satisfied"

    # Look for staff replies after "Assistance requested."
    if assistance_idx is not None:
        for msg in messages[assistance_idx + 1:]:
            if msg.author.id == bot_id:
                continue
            if msg.author.id == original_poster_id:
                continue  # original poster following up — not staff

            # Non-bot, non-OP member → treat as staff
            result["staff_replied"] = True

            content_lower = msg.content.lower()
            if any(kw in content_lower for kw in CONFIRMATION_KEYWORDS):
                result["staff_confirmed"] = True
            # Keep scanning — a later message may override to confirmed

    return result


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

    # aggregates
    total_threads = 0
    total_messages = 0
    bot_credit_count = 0           # satisfied + staff confirmed bot
    bot_satisfied_count = 0        # user clicked "It was great!"
    bot_staff_confirmed_count = 0  # staff confirmed bot was correct
    staff_answered_count = 0       # staff provided a new answer
    needs_help_unanswered = 0      # assistance requested, no staff reply yet
    pending_count = 0
    no_bot_msg_count = 0

    tag_counts: dict[str, int] = defaultdict(int)
    tag_bot_credit: dict[str, int] = defaultdict(int)
    tag_staff_answered: dict[str, int] = defaultdict(int)

    campus_counts: dict[str, int] = {}
    extra_forum_tag_counts: dict[str, int] = defaultdict(int)
    extra_forum_total = 0

    @client.event
    async def on_ready() -> None:
        nonlocal total_threads, total_messages, bot_credit_count, bot_satisfied_count, bot_staff_confirmed_count, staff_answered_count, needs_help_unanswered, pending_count, no_bot_msg_count, campus_counts, extra_forum_tag_counts, extra_forum_total
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
            info = await classify_thread(thread, bot_id)

            total_messages += info["msg_count"]

            status = info["status"]
            staff_replied = info["staff_replied"]
            staff_confirmed = info["staff_confirmed"]

            is_bot_credit = False
            is_staff_credit = False

            if status == "satisfied":
                bot_credit_count += 1
                bot_satisfied_count += 1
                is_bot_credit = True
            elif status == "needs_help":
                if staff_replied:
                    if staff_confirmed:
                        bot_credit_count += 1
                        bot_staff_confirmed_count += 1
                        is_bot_credit = True
                    else:
                        staff_answered_count += 1
                        is_staff_credit = True
                else:
                    needs_help_unanswered += 1
            elif status == "pending":
                pending_count += 1
            else:
                no_bot_msg_count += 1

            # Per-tag breakdown
            thread_tags = [
                tag_name_by_id.get(t.id, str(t.id)) for t in thread.applied_tags
            ]
            if not thread_tags:
                thread_tags = ["(no tag)"]
            for tag_name in thread_tags:
                tag_counts[tag_name] += 1
                if is_bot_credit:
                    tag_bot_credit[tag_name] += 1
                if is_staff_credit:
                    tag_staff_answered[tag_name] += 1

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
            if isinstance(channel, discord.TextChannel):
                count = 0
                async for _ in channel.history(limit=None, after=SINCE, before=UNTIL):
                    count += 1
            else:
                archived_ids = set(await _fetch_all_threads_in_range(client.http, channel_id))
                active_ids = {
                    t.id for t in getattr(channel, "threads", [])
                    if SINCE <= _snowflake_time(t.id) < UNTIL
                }
                count = len(archived_ids | active_ids)

            campus_counts[display_name] = count
            logger.info("  %s: %d posts", display_name, count)

        # Count threads in all forum channels belonging to the campus forums category
        logger.info(
            "Counting threads in campus forum channels (category %d)...",
            CAMPUS_FORUMS_CATEGORY_ID,
        )
        campus_forum_channels = [
            ch for ch in guild.channels
            if isinstance(ch, discord.ForumChannel)
            and getattr(ch, "category_id", None) == CAMPUS_FORUMS_CATEGORY_ID
        ]
        logger.info("Found %d forum channels in category.", len(campus_forum_channels))
        for forum in campus_forum_channels:
            archived_ids = set(await _fetch_all_threads_in_range(client.http, forum.id))
            seen: dict[int, discord.Thread] = {}
            async for thread in forum.archived_threads(limit=None):
                if thread.created_at and SINCE <= thread.created_at < UNTIL:
                    seen[thread.id] = thread
            for thread in forum.threads:
                if thread.created_at and SINCE <= thread.created_at < UNTIL:
                    seen[thread.id] = thread
            count = len(archived_ids | set(seen.keys()))
            campus_counts[forum.name] = count
            logger.info("  %s: %d threads", forum.name, count)

        await client.close()

    await client.start(token)

    # ------------------------------------------------------------------ #
    #  Report                                                              #
    # ------------------------------------------------------------------ #
    W = 54

    def pct(n: int, total: int) -> str:
        return f"{n / total * 100:.1f}%" if total else "—"

    print(f"\n{'=' * W}")
    print("  QnA Forum Statistics")
    print("  November 2025 – February 2026")
    print(f"{'=' * W}")

    print(f"\n  {'Total posts created:':<38} {total_threads:>5}")
    print(f"  {'Total messages sent:':<38} {total_messages:>5}")

    print(f"\n  {'Questions answered by bot:':<38} {bot_credit_count:>5}  ({pct(bot_credit_count, total_threads)})")
    print(f"    {'User confirmed satisfied:':<36} {bot_satisfied_count:>5}")
    print(f"    {'Staff confirmed bot was correct:':<36} {bot_staff_confirmed_count:>5}")

    print(f"\n  {'Questions answered by ASU staff:':<38} {staff_answered_count:>5}  ({pct(staff_answered_count, total_threads)})")

    print(f"\n  {'Needs help — awaiting staff reply:':<38} {needs_help_unanswered:>5}  ({pct(needs_help_unanswered, total_threads)})")
    print(f"  {'Pending (feedback buttons active):':<38} {pending_count:>5}  ({pct(pending_count, total_threads)})")
    print(f"  {'No bot message found:':<38} {no_bot_msg_count:>5}  ({pct(no_bot_msg_count, total_threads)})")

    print(f"\n{'-' * W}")
    print("  Posts by Tag")
    print(f"{'-' * W}")
    print(f"  {'Tag':<28} {'Posts':>5}  {'Bot':>5}  {'Staff':>5}")
    print(f"  {'-' * 28}  {'-----'}  {'-----'}  {'-----'}")
    for tag, count in sorted(tag_counts.items(), key=lambda x: -x[1]):
        bc = tag_bot_credit.get(tag, 0)
        sc = tag_staff_answered.get(tag, 0)
        print(f"  {tag:<28} {count:>5}  {bc:>5}  {sc:>5}")

    print(f"\n{'-' * W}")
    print(f"  Forum {EXTRA_FORUM_ID} — Tag Usage  ({extra_forum_total} total posts)")
    print(f"{'-' * W}")
    if extra_forum_tag_counts:
        for tag, count in sorted(extra_forum_tag_counts.items(), key=lambda x: -x[1]):
            print(f"  {tag:<28} {count:>5}  ({pct(count, extra_forum_total)})")
    else:
        print("  (no data — channel not found or no posts in range)")

    print(f"\n{'-' * W}")
    print("  Posts by Campus Channel")
    print(f"{'-' * W}")
    for campus_name, count in campus_counts.items():
        if count == -1:
            print(f"  {campus_name} — (channel not found)")
        else:
            print(f"  {campus_name:<32} {count:>5}")

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

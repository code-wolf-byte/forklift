"""MessageLoggerCog — logs Discord message metadata for activity analytics.

No message content is stored; only the snowflake ID, channel, author, and
timestamp are persisted. The cog also supports a one-time historical backfill
going back up to BACKFILL_LOOKBACK_DAYS from the moment it is triggered.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import discord
from discord.ext import commands

from utils.database import MessageBackfill, MessageLog, session_scope

logger = logging.getLogger(__name__)

BACKFILL_LOOKBACK_DAYS = 365
_BATCH_SIZE = 200

# Discord's history endpoint allows ~5 requests/5 s per channel bucket.
# We deliberately yield control between batches so other bot tasks aren't starved
# and the rate-limit headroom is shared more evenly across channels.
_BATCH_SLEEP_S = 1.0   # pause between 200-msg flushes within a channel
_CHANNEL_SLEEP_S = 2.0  # pause between channels


class MessageLoggerCog(commands.Cog):
    def __init__(self, bot: commands.Bot, *, guild_id: int) -> None:
        self.bot = bot
        self.guild_id = guild_id
        self._backfill_task: Optional[asyncio.Task] = None

    # ── Auto-start on ready ──────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Auto-trigger backfill once the bot is fully connected and guild data is available."""
        logger.info(
            "MessageLoggerCog ready — checking whether historical backfill is needed"
        )

        # Check if every known channel is already marked done
        with session_scope() as db:
            pending = (
                db.query(MessageBackfill.channel_id)
                .filter(MessageBackfill.status != "done")
                .count()
            )
            total = db.query(MessageBackfill.channel_id).count()

        if total > 0 and pending == 0:
            logger.info(
                "MessageLoggerCog: backfill already complete for all %d channels — skipping",
                total,
            )
            return

        if pending > 0:
            logger.info(
                "MessageLoggerCog: %d channel(s) not yet backfilled — resuming backfill",
                pending,
            )
        else:
            logger.info(
                "MessageLoggerCog: no backfill records found — starting initial backfill"
            )

        started = self.start_backfill()
        if not started:
            logger.info("MessageLoggerCog: backfill already in progress")

    # ── Real-time logging ────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if not message.guild or message.author.bot:
            return
        if message.guild.id != self.guild_id:
            return
        if not isinstance(message.channel, (discord.TextChannel, discord.Thread)):
            return

        msg_id = str(message.id)
        channel_id = str(message.channel.id)
        channel_name = getattr(message.channel, "name", None)
        guild_id = str(message.guild.id)
        user_id = str(message.author.id)
        sent_at = message.created_at.replace(tzinfo=None)  # store as naive UTC

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            self._save_message,
            msg_id, channel_id, channel_name, guild_id, user_id, sent_at,
        )

    def _save_message(
        self,
        message_id: str,
        channel_id: str,
        channel_name: str | None,
        guild_id: str,
        discord_user_id: str,
        sent_at: datetime,
    ) -> None:
        try:
            with session_scope() as db:
                exists = (
                    db.query(MessageLog.id)
                    .filter(MessageLog.message_id == message_id)
                    .first()
                )
                if exists:
                    return
                db.add(
                    MessageLog(
                        message_id=message_id,
                        channel_id=channel_id,
                        channel_name=channel_name,
                        guild_id=guild_id,
                        discord_user_id=discord_user_id,
                        sent_at=sent_at,
                    )
                )
        except Exception:
            logger.exception("Failed to save message %s", message_id)

    # ── Backfill ─────────────────────────────────────────────────────────────

    @property
    def backfill_running(self) -> bool:
        return self._backfill_task is not None and not self._backfill_task.done()

    def start_backfill(self) -> bool:
        """Schedule a backfill task. Returns False if one is already running."""
        if self.backfill_running:
            logger.info("MessageLoggerCog: backfill already running — ignoring request")
            return False
        logger.info("MessageLoggerCog: scheduling backfill task")
        self._backfill_task = asyncio.ensure_future(self._run_backfill())
        return True

    async def _run_backfill(self) -> None:
        guild = self.bot.get_guild(self.guild_id)
        if guild is None:
            logger.error("Guild %s not found for backfill", self.guild_id)
            return

        cutoff = datetime.now(timezone.utc) - timedelta(days=BACKFILL_LOOKBACK_DAYS)
        channels = [c for c in guild.channels if isinstance(c, discord.TextChannel)]
        logger.info(
            "Backfill started: %d channels, cutoff %s", len(channels), cutoff.date()
        )

        # Ensure a status row exists for every channel
        with session_scope() as db:
            for ch in channels:
                exists = (
                    db.query(MessageBackfill.id)
                    .filter(MessageBackfill.channel_id == str(ch.id))
                    .first()
                )
                if not exists:
                    db.add(
                        MessageBackfill(
                            channel_id=str(ch.id),
                            channel_name=ch.name,
                            status="pending",
                        )
                    )

        for ch in channels:
            channel_id = str(ch.id)

            # Skip already-completed channels
            with session_scope() as db:
                row = (
                    db.query(MessageBackfill)
                    .filter(MessageBackfill.channel_id == channel_id)
                    .one_or_none()
                )
                if row and row.status == "done":
                    continue
                if row:
                    row.status = "running"
                    row.started_at = datetime.utcnow()
                    row.error = None

            logger.info("Backfilling #%s (%s)", ch.name, channel_id)
            batch: list[tuple] = []
            fetched = 0
            oldest_dt: datetime | None = None

            try:
                async for msg in ch.history(
                    limit=None, after=cutoff, oldest_first=True
                ):
                    if msg.author.bot:
                        continue
                    batch.append(
                        (
                            str(msg.id),
                            channel_id,
                            ch.name,
                            str(guild.id),
                            str(msg.author.id),
                            msg.created_at.replace(tzinfo=None),
                        )
                    )
                    if oldest_dt is None:
                        oldest_dt = msg.created_at

                    if len(batch) >= _BATCH_SIZE:
                        saved = await asyncio.get_running_loop().run_in_executor(
                            None, self._flush_batch, batch
                        )
                        fetched += saved
                        batch = []
                        logger.debug(
                            "Backfill #%s: %d messages saved so far", ch.name, fetched
                        )
                        await asyncio.sleep(_BATCH_SLEEP_S)

                if batch:
                    saved = await asyncio.get_running_loop().run_in_executor(
                        None, self._flush_batch, batch
                    )
                    fetched += saved

                with session_scope() as db:
                    row = (
                        db.query(MessageBackfill)
                        .filter(MessageBackfill.channel_id == channel_id)
                        .one_or_none()
                    )
                    if row:
                        row.status = "done"
                        row.messages_fetched = fetched
                        row.oldest_fetched_at = (
                            oldest_dt.replace(tzinfo=None) if oldest_dt else None
                        )
                        row.completed_at = datetime.utcnow()

                logger.info(
                    "Backfilled #%s (%s): %d new messages saved",
                    ch.name, channel_id, fetched,
                )

            except discord.Forbidden:
                logger.warning("No permission to read #%s — skipping", ch.name)
                self._set_backfill_error(channel_id, "Missing read permissions")
            except Exception as exc:
                logger.exception("Backfill failed for #%s", ch.name)
                self._set_backfill_error(channel_id, str(exc)[:512])

            # Yield between channels so the rate-limit bucket has time to recover
            await asyncio.sleep(_CHANNEL_SLEEP_S)

        logger.info("Backfill complete for guild %s", self.guild_id)

    def _flush_batch(self, batch: list[tuple]) -> int:
        """Insert a batch of messages, skipping duplicates. Returns number inserted."""
        if not batch:
            return 0
        message_ids = [row[0] for row in batch]
        try:
            with session_scope() as db:
                existing = {
                    r.message_id
                    for r in db.query(MessageLog.message_id)
                    .filter(MessageLog.message_id.in_(message_ids))
                    .all()
                }
                new_rows = [
                    MessageLog(
                        message_id=mid,
                        channel_id=cid,
                        channel_name=cname,
                        guild_id=gid,
                        discord_user_id=uid,
                        sent_at=ts,
                    )
                    for mid, cid, cname, gid, uid, ts in batch
                    if mid not in existing
                ]
                db.bulk_save_objects(new_rows)
                return len(new_rows)
        except Exception:
            logger.exception("Failed to flush batch of %d messages", len(batch))
            return 0

    def _set_backfill_error(self, channel_id: str, error: str) -> None:
        try:
            with session_scope() as db:
                row = (
                    db.query(MessageBackfill)
                    .filter(MessageBackfill.channel_id == channel_id)
                    .one_or_none()
                )
                if row:
                    row.status = "failed"
                    row.error = error
                    row.completed_at = datetime.utcnow()
        except Exception:
            logger.exception("Failed to update backfill error for %s", channel_id)

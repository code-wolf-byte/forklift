"""AnalyticsCog — central analytics tracker for the Devil2Devil Discord server.

Every event is written to the database immediately (no in-memory accumulation),
so a bot restart never loses data. Voice sessions that were open when the bot
went down are detected on ``on_ready`` and closed with ``is_complete=False`` so
partial durations are still recorded.

Tracks
------
- Messages sent         → ``message_logs``         (moved from MessageLoggerCog)
- Gold Guide replies    → ``gold_guide_contributions``  (moved from QnACog.on_message)
- Voice sessions        → ``voice_sessions``        (new, restart-resilient)
- Bans / unbans         → ``moderation_events``     (new)
- Non-QnA forum posts   → ``forum_posts``           (new)
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import discord
from discord.ext import commands

from utils.database import (
    ForumPost,
    GoldGuideContribution,
    MessageBackfill,
    MessageLog,
    ModerationEvent,
    VoiceSession,
    session_scope,
)

logger = logging.getLogger(__name__)

GOLD_GUIDE_ROLE_ID = 1187156709597270157

# ── Message backfill settings (carried over from MessageLoggerCog) ────────────
BACKFILL_LOOKBACK_DAYS = 365
_PAGE_SIZE = 100       # Discord max per history request
_PAGE_SLEEP_S = 1.1    # sleep between pages (≈1 req/s, under the 5 req/5 s bucket)
_CHANNEL_SLEEP_S = 2.0 # pause between channels so rate-limit buckets recover


class AnalyticsCog(commands.Cog):
    """Central analytics cog — all event data persisted to DB with no in-memory state."""

    def __init__(self, bot: commands.Bot, *, guild_id: int) -> None:
        self.bot = bot
        self.guild_id = guild_id
        self._backfill_task: Optional[asyncio.Task] = None

    # ── Startup ───────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        logger.info("AnalyticsCog ready (guild %s)", self.guild_id)
        # Must complete before we start accepting voice events.
        await self._reconcile_voice_sessions()
        # These run as background tasks — they're slow but fully idempotent.
        asyncio.ensure_future(self._backfill_forum_posts())
        asyncio.ensure_future(self._backfill_moderation_events())
        self._maybe_start_backfill()  # message backfill (also a background task)

    # ═════════════════════════════════════════════════════════════════════════
    # MESSAGE LOGGING  (previously MessageLoggerCog)
    # ═════════════════════════════════════════════════════════════════════════

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if not message.guild or message.author.bot:
            return
        if message.guild.id != self.guild_id:
            return
        if not isinstance(
            message.channel, (discord.TextChannel, discord.Thread, discord.ForumChannel, discord.VoiceChannel)
        ):
            return

        loop = asyncio.get_running_loop()

        # Persist to message_logs
        await loop.run_in_executor(
            None,
            self._save_message,
            str(message.id),
            str(message.channel.id),
            getattr(message.channel, "name", None),
            str(message.guild.id),
            str(message.author.id),
            message.created_at.replace(tzinfo=None),
            message.content or None,
        )

        # Gold Guide contribution in a QnA thread
        if (
            isinstance(message.channel, discord.Thread)
            and isinstance(message.author, discord.Member)
            and any(r.id == GOLD_GUIDE_ROLE_ID for r in message.author.roles)
        ):
            qna_forum_id = self._get_qna_forum_id()
            if qna_forum_id is not None and message.channel.parent_id == qna_forum_id:
                await loop.run_in_executor(None, self._save_gg_contribution, message)

    def _save_message(
        self,
        message_id: str,
        channel_id: str,
        channel_name: str | None,
        guild_id: str,
        discord_user_id: str,
        sent_at: datetime,
        content: str | None,
    ) -> None:
        try:
            with session_scope() as db:
                if (
                    db.query(MessageLog.id)
                    .filter(MessageLog.message_id == message_id)
                    .first()
                ):
                    return
                db.add(
                    MessageLog(
                        message_id=message_id,
                        channel_id=channel_id,
                        channel_name=channel_name,
                        guild_id=guild_id,
                        discord_user_id=discord_user_id,
                        sent_at=sent_at,
                        content=content,
                    )
                )
        except Exception:
            logger.exception("Failed to save message %s", message_id)

    # ═════════════════════════════════════════════════════════════════════════
    # GOLD GUIDE CONTRIBUTIONS  (previously QnACog.on_message)
    # ═════════════════════════════════════════════════════════════════════════

    def _save_gg_contribution(self, message: discord.Message) -> None:
        thread = message.channel
        parent_name = thread.parent.name if thread.parent else None
        try:
            with session_scope() as db:
                if (
                    db.query(GoldGuideContribution.id)
                    .filter(GoldGuideContribution.message_id == str(message.id))
                    .first()
                ):
                    return
                db.add(
                    GoldGuideContribution(
                        guild_id=str(message.guild.id) if message.guild else None,
                        channel_id=str(thread.parent_id),
                        channel_name=parent_name,
                        thread_id=str(thread.id),
                        thread_title=thread.name,
                        message_id=str(message.id),
                        responder_discord_id=str(message.author.id),
                        responder_username=message.author.name,
                        responded_at=message.created_at.replace(tzinfo=None),
                    )
                )
        except Exception:
            logger.exception(
                "Failed to save Gold Guide contribution for message %s", message.id
            )

    # ═════════════════════════════════════════════════════════════════════════
    # VOICE SESSION TRACKING  (new)
    # ═════════════════════════════════════════════════════════════════════════

    async def _reconcile_voice_sessions(self) -> None:
        """Close sessions left open because the bot restarted mid-session.

        For each VoiceSession with ``left_at=NULL``:
        - If the user is still in voice → leave the session open (correct).
        - If the user is gone        → close with ``is_complete=False`` so we
          still capture the partial duration from ``joined_at`` to now.
        """
        guild = self.bot.get_guild(self.guild_id)
        if guild is None:
            logger.warning("AnalyticsCog: guild %s not in cache, skipping reconciliation", self.guild_id)
            return

        in_voice: set[str] = {
            str(m.id)
            for vc in guild.voice_channels
            for m in vc.members
        }
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._close_orphaned_sessions, in_voice, now_utc)
        logger.info("AnalyticsCog: voice reconciliation complete (guild %s)", self.guild_id)

    def _close_orphaned_sessions(self, in_voice: set[str], now_utc: datetime) -> None:
        try:
            with session_scope() as db:
                open_sessions = (
                    db.query(VoiceSession)
                    .filter(
                        VoiceSession.guild_id == str(self.guild_id),
                        VoiceSession.left_at.is_(None),
                    )
                    .all()
                )
                orphaned = 0
                for s in open_sessions:
                    if s.discord_user_id in in_voice:
                        continue  # user is still in voice — session is valid
                    s.left_at = now_utc
                    if s.joined_at:
                        elapsed = (now_utc - s.joined_at).total_seconds()
                        s.duration_seconds = int(max(0, elapsed))
                    s.is_complete = False  # truncated by bot restart
                    orphaned += 1
                if orphaned:
                    logger.info("Closed %d orphaned voice session(s)", orphaned)
        except Exception:
            logger.exception("Failed to reconcile orphaned voice sessions")

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if member.guild.id != self.guild_id or member.bot:
            return

        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        user_id = str(member.id)
        loop = asyncio.get_running_loop()

        # Determine what changed
        left_channel = before.channel is not None and (
            after.channel is None or before.channel.id != after.channel.id
        )
        joined_channel = after.channel is not None and (
            before.channel is None or before.channel.id != after.channel.id
        )

        if left_channel:
            await loop.run_in_executor(
                None,
                self._close_voice_session,
                user_id,
                str(before.channel.id),
                now_utc,
                True,
            )

        if joined_channel:
            await loop.run_in_executor(
                None,
                self._open_voice_session,
                user_id,
                member.name,
                str(after.channel.id),
                after.channel.name,
                now_utc,
            )

    def _open_voice_session(
        self,
        user_id: str,
        username: str,
        channel_id: str,
        channel_name: str,
        joined_at: datetime,
    ) -> None:
        try:
            with session_scope() as db:
                # Safety: close any dangling open session (shouldn't exist, but be safe)
                dangling = (
                    db.query(VoiceSession)
                    .filter(
                        VoiceSession.discord_user_id == user_id,
                        VoiceSession.guild_id == str(self.guild_id),
                        VoiceSession.left_at.is_(None),
                    )
                    .one_or_none()
                )
                if dangling:
                    dangling.left_at = joined_at
                    if dangling.joined_at:
                        elapsed = (joined_at - dangling.joined_at).total_seconds()
                        dangling.duration_seconds = int(max(0, elapsed))
                    dangling.is_complete = False

                db.add(
                    VoiceSession(
                        discord_user_id=user_id,
                        discord_username=username,
                        guild_id=str(self.guild_id),
                        channel_id=channel_id,
                        channel_name=channel_name,
                        joined_at=joined_at,
                    )
                )
        except Exception:
            logger.exception("Failed to open voice session for user %s", user_id)

    def _close_voice_session(
        self, user_id: str, channel_id: str, left_at: datetime, is_complete: bool
    ) -> None:
        try:
            with session_scope() as db:
                session = (
                    db.query(VoiceSession)
                    .filter(
                        VoiceSession.discord_user_id == user_id,
                        VoiceSession.guild_id == str(self.guild_id),
                        VoiceSession.left_at.is_(None),
                    )
                    .one_or_none()
                )
                if session is None:
                    logger.warning(
                        "No open voice session found for user %s (channel %s) on close",
                        user_id, channel_id,
                    )
                    return
                session.left_at = left_at
                if session.joined_at:
                    elapsed = (left_at - session.joined_at).total_seconds()
                    session.duration_seconds = int(max(0, elapsed))
                session.is_complete = is_complete
        except Exception:
            logger.exception("Failed to close voice session for user %s", user_id)

    # ═════════════════════════════════════════════════════════════════════════
    # MODERATION EVENTS  (new)
    # ═════════════════════════════════════════════════════════════════════════

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User) -> None:
        if guild.id != self.guild_id:
            return
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)

        reason: str | None = None
        mod_id: str | None = None
        mod_name: str | None = None
        try:
            # Brief pause — audit log entries can appear slightly after the event
            await asyncio.sleep(1)
            async for entry in guild.audit_logs(
                limit=10, action=discord.AuditLogAction.ban
            ):
                if entry.target and entry.target.id == user.id:
                    reason = entry.reason
                    if entry.user:
                        mod_id = str(entry.user.id)
                        mod_name = entry.user.name
                    break
        except Exception:
            logger.warning("Could not read audit log for ban of user %s", user.id)

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            self._save_moderation_event,
            str(user.id),
            str(user),
            str(guild.id),
            "ban",
            reason,
            mod_id,
            mod_name,
            now_utc,
        )

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User) -> None:
        if guild.id != self.guild_id:
            return
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)

        mod_id: str | None = None
        mod_name: str | None = None
        try:
            await asyncio.sleep(1)
            async for entry in guild.audit_logs(
                limit=10, action=discord.AuditLogAction.unban
            ):
                if entry.target and entry.target.id == user.id:
                    if entry.user:
                        mod_id = str(entry.user.id)
                        mod_name = entry.user.name
                    break
        except Exception:
            logger.warning("Could not read audit log for unban of user %s", user.id)

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            self._save_moderation_event,
            str(user.id),
            str(user),
            str(guild.id),
            "unban",
            None,
            mod_id,
            mod_name,
            now_utc,
        )

    def _save_moderation_event(
        self,
        discord_user_id: str,
        discord_username: str,
        guild_id: str,
        event_type: str,
        reason: str | None,
        moderator_discord_id: str | None,
        moderator_username: str | None,
        occurred_at: datetime,
    ) -> None:
        try:
            with session_scope() as db:
                db.add(
                    ModerationEvent(
                        discord_user_id=discord_user_id,
                        discord_username=discord_username,
                        guild_id=guild_id,
                        event_type=event_type,
                        reason=reason,
                        moderator_discord_id=moderator_discord_id,
                        moderator_username=moderator_username,
                        occurred_at=occurred_at,
                    )
                )
        except Exception:
            logger.exception(
                "Failed to save moderation event %s for user %s", event_type, discord_user_id
            )

    # ═════════════════════════════════════════════════════════════════════════
    # NON-QnA FORUM POST TRACKING  (new)
    # ═════════════════════════════════════════════════════════════════════════

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread) -> None:
        if thread.guild.id != self.guild_id:
            return
        if not isinstance(thread.parent, discord.ForumChannel):
            return
        # Skip the QnA forum — those threads go into qna_posts via QnACog
        qna_forum_id = self._get_qna_forum_id()
        if qna_forum_id is not None and thread.parent_id == qna_forum_id:
            return

        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        tag_names_json = json.dumps(
            [tag.name for tag in getattr(thread, "applied_tags", [])]
        )

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            self._save_forum_post,
            str(thread.id),
            str(thread.parent_id),
            thread.parent.name,
            str(thread.guild.id),
            str(thread.owner_id) if thread.owner_id else None,
            thread.name,
            tag_names_json,
            now_utc,
        )

    def _save_forum_post(
        self,
        thread_id: str,
        parent_channel_id: str,
        parent_channel_name: str,
        guild_id: str,
        discord_user_id: str | None,
        title: str,
        tag_names_json: str,
        created_at: datetime,
    ) -> bool:
        """Insert a ForumPost row if it doesn't already exist. Returns True if inserted."""
        try:
            with session_scope() as db:
                if (
                    db.query(ForumPost.id)
                    .filter(ForumPost.thread_id == thread_id)
                    .first()
                ):
                    return False
                db.add(
                    ForumPost(
                        thread_id=thread_id,
                        parent_channel_id=parent_channel_id,
                        parent_channel_name=parent_channel_name,
                        guild_id=guild_id,
                        discord_user_id=discord_user_id,
                        title=title,
                        tag_names=tag_names_json,
                        created_at=created_at,
                    )
                )
                return True
        except Exception:
            logger.exception("Failed to save forum post (thread %s)", thread_id)
            return False

    # ═════════════════════════════════════════════════════════════════════════
    # HELPERS
    # ═════════════════════════════════════════════════════════════════════════

    def _get_qna_forum_id(self) -> int | None:
        """Return the QnA forum channel ID from QnACog at runtime, or None."""
        qna_cog = self.bot.cogs.get("QnACog")
        return getattr(qna_cog, "forum_channel_id", None) if qna_cog else None

    # ═════════════════════════════════════════════════════════════════════════
    # FORUM POSTS BACKFILL
    # ═════════════════════════════════════════════════════════════════════════

    async def _backfill_forum_posts(self) -> None:
        """Populate forum_posts from all non-QnA forum channel threads.

        Idempotent — existing rows (matched by thread_id unique constraint) are
        skipped. Runs on every startup so threads created while the bot was down
        are picked up automatically.
        """
        guild = self.bot.get_guild(self.guild_id)
        if guild is None:
            logger.warning("AnalyticsCog: guild not found, skipping forum post backfill")
            return

        qna_forum_id = self._get_qna_forum_id()
        loop = asyncio.get_running_loop()
        inserted_total = 0

        for channel in guild.channels:
            if not isinstance(channel, discord.ForumChannel):
                continue
            if qna_forum_id is not None and channel.id == qna_forum_id:
                continue  # QnA threads go into qna_posts, not forum_posts

            threads: list[discord.Thread] = list(channel.threads)  # active/cached

            try:
                async for thread in channel.archived_threads(limit=None):
                    threads.append(thread)
                await asyncio.sleep(_PAGE_SLEEP_S)
            except discord.Forbidden:
                logger.warning(
                    "AnalyticsCog: no permission for archived threads in #%s", channel.name
                )
            except Exception:
                logger.exception(
                    "AnalyticsCog: failed to list archived threads in #%s", channel.name
                )

            for thread in threads:
                created_at = (
                    thread.created_at.replace(tzinfo=None)
                    if thread.created_at
                    else datetime.now(timezone.utc).replace(tzinfo=None)
                )
                tag_names_json = json.dumps(
                    [tag.name for tag in getattr(thread, "applied_tags", [])]
                )
                saved = await loop.run_in_executor(
                    None,
                    self._save_forum_post,
                    str(thread.id),
                    str(channel.id),
                    channel.name,
                    str(guild.id),
                    str(thread.owner_id) if thread.owner_id else None,
                    thread.name,
                    tag_names_json,
                    created_at,
                )
                if saved:
                    inserted_total += 1

        logger.info(
            "AnalyticsCog: forum post backfill complete — %d new rows (guild %s)",
            inserted_total, self.guild_id,
        )

    # ═════════════════════════════════════════════════════════════════════════
    # MODERATION EVENTS BACKFILL  (Discord audit log, max 90 days)
    # ═════════════════════════════════════════════════════════════════════════

    async def _backfill_moderation_events(self) -> None:
        """Populate moderation_events from the Discord audit log.

        Discord retains audit log entries for 90 days. We only run the full
        backfill once (when the table is empty for this guild). Subsequent
        startups skip it because real-time on_member_ban/on_member_unban keep
        the table current.
        """
        guild = self.bot.get_guild(self.guild_id)
        if guild is None:
            return

        with session_scope() as db:
            existing = (
                db.query(ModerationEvent)
                .filter(ModerationEvent.guild_id == str(self.guild_id))
                .count()
            )
        if existing > 0:
            logger.info(
                "AnalyticsCog: moderation_events already populated (%d rows) — skipping backfill",
                existing,
            )
            return

        logger.info(
            "AnalyticsCog: backfilling moderation events from audit log (guild %s)", self.guild_id
        )

        events: list[dict] = []
        for action, event_type in (
            (discord.AuditLogAction.ban, "ban"),
            (discord.AuditLogAction.unban, "unban"),
        ):
            try:
                async for entry in guild.audit_logs(limit=None, action=action):
                    if entry.target is None:
                        continue
                    events.append(
                        {
                            "discord_user_id": str(entry.target.id),
                            "discord_username": str(entry.target),
                            "guild_id": str(guild.id),
                            "event_type": event_type,
                            "reason": entry.reason,
                            "moderator_discord_id": str(entry.user.id) if entry.user else None,
                            "moderator_username": entry.user.name if entry.user else None,
                            "occurred_at": entry.created_at.replace(tzinfo=None),
                        }
                    )
                await asyncio.sleep(_PAGE_SLEEP_S)
            except discord.Forbidden:
                logger.warning(
                    "AnalyticsCog: no permission to read audit log for %s backfill", event_type
                )
            except Exception:
                logger.exception(
                    "AnalyticsCog: failed to read audit log for %s backfill", event_type
                )

        if not events:
            logger.info("AnalyticsCog: no audit log entries found for moderation backfill")
            return

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._flush_moderation_events, events)
        logger.info(
            "AnalyticsCog: moderation backfill complete — %d events inserted", len(events)
        )

    def _flush_moderation_events(self, events: list[dict]) -> None:
        try:
            with session_scope() as db:
                db.bulk_save_objects(
                    [ModerationEvent(**ev) for ev in events]
                )
        except Exception:
            logger.exception("AnalyticsCog: failed to flush moderation events backfill")

    # ═════════════════════════════════════════════════════════════════════════
    # MESSAGE BACKFILL  (moved from MessageLoggerCog, identical logic)
    # ═════════════════════════════════════════════════════════════════════════

    @property
    def backfill_running(self) -> bool:
        return self._backfill_task is not None and not self._backfill_task.done()

    def _maybe_start_backfill(self) -> None:
        with session_scope() as db:
            pending = (
                db.query(MessageBackfill.channel_id)
                .filter(MessageBackfill.status != "done")
                .count()
            )
            total = db.query(MessageBackfill.channel_id).count()

        if total > 0 and pending == 0:
            logger.info("AnalyticsCog: message backfill already complete — skipping")
            return
        if pending > 0:
            logger.info("AnalyticsCog: %d channel(s) pending backfill — resuming", pending)
        else:
            logger.info("AnalyticsCog: no backfill records — starting initial backfill")
        self.start_backfill()

    def start_backfill(self) -> bool:
        """Schedule a message backfill task. Returns False if already running."""
        if self.backfill_running:
            logger.info("AnalyticsCog: backfill already running — ignoring")
            return False
        logger.info("AnalyticsCog: scheduling backfill task")
        self._backfill_task = asyncio.ensure_future(self._run_backfill())
        return True

    async def _collect_backfill_targets(
        self, guild: discord.Guild
    ) -> list[discord.TextChannel | discord.Thread | discord.VoiceChannel]:
        targets: list[discord.TextChannel | discord.Thread | discord.VoiceChannel] = []
        for ch in guild.channels:
            if isinstance(ch, discord.TextChannel):
                targets.append(ch)
                targets.extend(ch.threads)
                try:
                    async for thread in ch.archived_threads(limit=None):
                        targets.append(thread)
                    await asyncio.sleep(_PAGE_SLEEP_S)
                except discord.Forbidden:
                    logger.warning(
                        "No permission to list archived threads in #%s — skipping", ch.name
                    )
                except Exception:
                    logger.exception("Failed to list archived threads in #%s", ch.name)
            elif isinstance(ch, discord.VoiceChannel):
                targets.append(ch)
            elif isinstance(ch, discord.ForumChannel):
                targets.extend(ch.threads)
                try:
                    async for thread in ch.archived_threads(limit=None):
                        targets.append(thread)
                    await asyncio.sleep(_PAGE_SLEEP_S)
                except discord.Forbidden:
                    logger.warning(
                        "No permission to list archived threads in #%s — skipping", ch.name
                    )
                except Exception:
                    logger.exception("Failed to list archived threads in #%s", ch.name)
        return targets

    async def _run_backfill(self) -> None:
        guild = self.bot.get_guild(self.guild_id)
        if guild is None:
            logger.error("AnalyticsCog: guild %s not found for backfill", self.guild_id)
            return

        cutoff = datetime.now(timezone.utc) - timedelta(days=BACKFILL_LOOKBACK_DAYS)
        channels = await self._collect_backfill_targets(guild)
        logger.info(
            "AnalyticsCog backfill started: %d channels/threads, cutoff %s",
            len(channels), cutoff.date(),
        )

        with session_scope() as db:
            for ch in channels:
                exists = (
                    db.query(MessageBackfill.id)
                    .filter(MessageBackfill.channel_id == str(ch.id))
                    .first()
                )
                if not exists:
                    db.add(MessageBackfill(
                        channel_id=str(ch.id),
                        channel_name=ch.name,
                        status="pending",
                    ))

        for ch in channels:
            channel_id = str(ch.id)

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
                    row.started_at = datetime.now(timezone.utc).replace(tzinfo=None)
                    row.error = None

            logger.info("Backfilling #%s (%s)", ch.name, channel_id)
            fetched = 0
            oldest_dt: datetime | None = None
            anchor: datetime | discord.Message = cutoff

            try:
                while True:
                    page = await ch.history(
                        limit=_PAGE_SIZE, after=anchor, oldest_first=True
                    ).flatten()

                    if not page:
                        break

                    non_bot = [m for m in page if not m.author.bot]
                    if oldest_dt is None and non_bot:
                        oldest_dt = non_bot[0].created_at

                    batch = [
                        (
                            str(m.id),
                            channel_id,
                            ch.name,
                            str(guild.id),
                            str(m.author.id),
                            m.created_at.replace(tzinfo=None),
                            m.content or None,
                        )
                        for m in non_bot
                    ]

                    if batch:
                        saved = await asyncio.get_running_loop().run_in_executor(
                            None, self._flush_batch, batch
                        )
                        fetched += saved

                    anchor = page[-1]
                    if len(page) == _PAGE_SIZE:
                        await asyncio.sleep(_PAGE_SLEEP_S)

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
                        row.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)

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

            await asyncio.sleep(_CHANNEL_SLEEP_S)

        logger.info("AnalyticsCog: backfill complete for guild %s", self.guild_id)

    def _flush_batch(self, batch: list[tuple]) -> int:
        """Insert new messages; patch content on existing rows where it is NULL."""
        if not batch:
            return 0
        message_ids = [row[0] for row in batch]
        try:
            with session_scope() as db:
                existing_rows = (
                    db.query(MessageLog)
                    .filter(MessageLog.message_id.in_(message_ids))
                    .all()
                )
                with_content = {r.message_id for r in existing_rows if r.content is not None}
                without_content = {r.message_id: r for r in existing_rows if r.content is None}

                new_rows = []
                for mid, cid, cname, gid, uid, ts, content in batch:
                    if mid in with_content:
                        continue
                    if mid in without_content:
                        if content:
                            without_content[mid].content = content
                        continue
                    new_rows.append(
                        MessageLog(
                            message_id=mid,
                            channel_id=cid,
                            channel_name=cname,
                            guild_id=gid,
                            discord_user_id=uid,
                            sent_at=ts,
                            content=content,
                        )
                    )
                if new_rows:
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
                    row.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        except Exception:
            logger.exception("Failed to update backfill error for channel %s", channel_id)


from __future__ import annotations

import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands

from utils.database import EventParticipant, ServerEvent, session_scope

logger = logging.getLogger(__name__)

# Only track in-server events — filter out external locations.
_TRACKED_ENTITY_TYPES: dict[discord.ScheduledEventLocationType, str] = {
    discord.ScheduledEventLocationType.voice: "voice",
    discord.ScheduledEventLocationType.stage_instance: "stage_instance",
}


class EventTrackerCog(commands.Cog):
    """Tracks Discord scheduled events (voice/stage only) and their participants."""

    def __init__(self, bot: commands.Bot, *, guild_id: int) -> None:
        self.bot = bot
        self.guild_id = guild_id

    def _is_tracked(self, event: discord.ScheduledEvent) -> bool:
        return event.location.type in _TRACKED_ENTITY_TYPES

    def _upsert_event(self, db_session, event: discord.ScheduledEvent) -> ServerEvent | None:
        if not self._is_tracked(event):
            return None

        now = datetime.utcnow()
        start_time = (
            event.start_time.astimezone(timezone.utc).replace(tzinfo=None)
            if event.start_time else None
        )
        end_time = (
            event.end_time.astimezone(timezone.utc).replace(tzinfo=None)
            if event.end_time else None
        )
        status = event.status.name.lower() if event.status else "scheduled"
        entity_type = _TRACKED_ENTITY_TYPES[event.location.type]
        channel_id = str(event.location.value.id) if event.location.value else None

        existing = (
            db_session.query(ServerEvent)
            .filter(ServerEvent.discord_event_id == str(event.id))
            .one_or_none()
        )

        if existing:
            existing.name = event.name
            existing.description = event.description
            existing.start_time = start_time
            existing.end_time = end_time
            existing.status = status
            existing.entity_type = entity_type
            existing.channel_id = channel_id
            existing.updated_at = now
            return existing

        new_ev = ServerEvent(
            discord_event_id=str(event.id),
            guild_id=str(event.guild_id),
            name=event.name,
            description=event.description,
            start_time=start_time,
            end_time=end_time,
            status=status,
            entity_type=entity_type,
            channel_id=channel_id,
        )
        db_session.add(new_ev)
        return new_ev

    def _record_participant(
        self, db_session, server_event_id: int, discord_user_id: str, action: str
    ) -> None:
        db_session.add(
            EventParticipant(
                event_id=server_event_id,
                discord_user_id=discord_user_id,
                action=action,
                timestamp=datetime.utcnow(),
            )
        )

    # ── Startup sync ─────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Sync all current scheduled events from Discord on startup.

        This runs even if an event is already active when the bot deploys —
        active events get their current subscriber list back-filled.
        """
        guild = self.bot.get_guild(self.guild_id)
        if guild is None:
            logger.warning("EventTrackerCog: guild %s not in cache on ready", self.guild_id)
            return

        try:
            events = await guild.fetch_scheduled_events(with_counts=False)
        except Exception:
            logger.exception("EventTrackerCog: failed to fetch scheduled events on startup")
            return

        tracked = [e for e in events if self._is_tracked(e)]
        for event in tracked:
            with session_scope() as db_session:
                self._upsert_event(db_session, event)

            if event.status == discord.ScheduledEventStatus.active:
                await self._backfill_active_subscribers(event)

        logger.info(
            "EventTrackerCog ready — synced %d/%d tracked events",
            len(tracked),
            len(events),
        )

    async def _backfill_active_subscribers(self, event: discord.ScheduledEvent) -> None:
        """Insert 'joined' rows for users already subscribed to a live event on startup."""
        try:
            user_ids: list[str] = []
            async for user in event.fetch_users():
                user_ids.append(str(user.id))
        except Exception:
            logger.warning(
                "EventTrackerCog: could not fetch subscribers for active event %s", event.id
            )
            return

        if not user_ids:
            return

        with session_scope() as db_session:
            server_event = (
                db_session.query(ServerEvent)
                .filter(ServerEvent.discord_event_id == str(event.id))
                .one_or_none()
            )
            if server_event is None:
                return

            already_joined = {
                row.discord_user_id
                for row in db_session.query(EventParticipant.discord_user_id)
                .filter(
                    EventParticipant.event_id == server_event.id,
                    EventParticipant.action == "joined",
                )
                .all()
            }

            for uid in user_ids:
                if uid not in already_joined:
                    self._record_participant(db_session, server_event.id, uid, "joined")

    # ── Event lifecycle ───────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_scheduled_event_create(self, event: discord.ScheduledEvent) -> None:
        if not self._is_tracked(event):
            return
        with session_scope() as db_session:
            self._upsert_event(db_session, event)

    @commands.Cog.listener()
    async def on_scheduled_event_update(
        self, _before: discord.ScheduledEvent, after: discord.ScheduledEvent
    ) -> None:
        if not self._is_tracked(after):
            return
        with session_scope() as db_session:
            self._upsert_event(db_session, after)

    @commands.Cog.listener()
    async def on_scheduled_event_delete(self, event: discord.ScheduledEvent) -> None:
        if not self._is_tracked(event):
            return
        with session_scope() as db_session:
            existing = (
                db_session.query(ServerEvent)
                .filter(ServerEvent.discord_event_id == str(event.id))
                .one_or_none()
            )
            if existing:
                existing.status = "cancelled"
                existing.updated_at = datetime.utcnow()

    # ── Participant tracking ──────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_scheduled_event_user_add(
        self, event: discord.ScheduledEvent, user: discord.User
    ) -> None:
        if not self._is_tracked(event):
            return
        with session_scope() as db_session:
            server_event = (
                db_session.query(ServerEvent)
                .filter(ServerEvent.discord_event_id == str(event.id))
                .one_or_none()
            )
            if server_event is None:
                server_event = self._upsert_event(db_session, event)
                db_session.flush()
            self._record_participant(db_session, server_event.id, str(user.id), "joined")

    @commands.Cog.listener()
    async def on_scheduled_event_user_remove(
        self, event: discord.ScheduledEvent, user: discord.User
    ) -> None:
        if not self._is_tracked(event):
            return
        with session_scope() as db_session:
            server_event = (
                db_session.query(ServerEvent)
                .filter(ServerEvent.discord_event_id == str(event.id))
                .one_or_none()
            )
            if server_event is None:
                return
            self._record_participant(db_session, server_event.id, str(user.id), "left")

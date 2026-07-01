#!/usr/bin/env python3
"""
Backfill VolunteerContribution records from existing message_logs history.

Unlike backfill_qna.py, this does NOT need to re-fetch Discord message history —
message_logs already contains every message ever logged, across all channels. This
script only needs to:
  1. Connect to Discord and read the current members of the Volunteer role.
  2. Query message_logs for every message sent by one of those members.
  3. Insert a VolunteerContribution row per message (deduplicated by message_id).

Run once after deploying the schema changes. Safe to re-run — inserts are
idempotent (skips existing rows by message_id).
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

ENV_PATH = PROJECT_ROOT / ".env"

GUILD_ID = 1187144343400751234
VOLUNTEER_ROLE_ID = 1301984870087528540

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


_LOCAL_DB_URL = f"sqlite:///{PROJECT_ROOT / 'forklift.db'}"
_SKIP_ENV_KEYS = {"DATABASE_URL"}


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key in _SKIP_ENV_KEYS:
            continue
        value = value.strip().strip("\"'")
        if key:
            os.environ.setdefault(key, value)
    os.environ["DATABASE_URL"] = _LOCAL_DB_URL


async def run() -> None:
    try:
        import discord
    except ImportError as exc:
        raise SystemExit("discord.py is not installed.") from exc

    # Import DB after env is loaded so DATABASE_URL is set
    from utils.database import MessageLog, VolunteerContribution, init_db, session_scope

    init_db()

    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        raise SystemExit("DISCORD_BOT_TOKEN not set.")

    intents = discord.Intents.default()
    intents.guilds = True
    intents.members = True

    client = discord.Client(intents=intents)

    @client.event
    async def on_ready() -> None:
        logger.info("Connected as %s", client.user)

        guild = client.get_guild(GUILD_ID)
        if guild is None:
            logger.error("Guild %d not found.", GUILD_ID)
            await client.close()
            return

        volunteer_role = guild.get_role(VOLUNTEER_ROLE_ID)
        if volunteer_role is None:
            logger.warning("Volunteer role %d not found — nothing to backfill.", VOLUNTEER_ROLE_ID)
            await client.close()
            return

        volunteer_ids = {str(m.id) for m in volunteer_role.members}
        member_names = {str(m.id): m.name for m in volunteer_role.members}
        logger.info("Volunteer members found: %d", len(volunteer_ids))

        if not volunteer_ids:
            await client.close()
            return

        inserted = 0

        def _do_backfill() -> int:
            nonlocal inserted
            with session_scope() as db_session:
                existing_ids = {
                    r[0]
                    for r in db_session.query(VolunteerContribution.message_id)
                    .filter(VolunteerContribution.message_id.isnot(None))
                    .all()
                }
                rows = (
                    db_session.query(MessageLog)
                    .filter(MessageLog.discord_user_id.in_(volunteer_ids))
                    .all()
                )
                new_objs = [
                    VolunteerContribution(
                        guild_id=r.guild_id,
                        channel_id=r.channel_id,
                        channel_name=r.channel_name,
                        parent_channel_id=r.parent_channel_id,
                        parent_channel_name=r.parent_channel_name,
                        message_id=r.message_id,
                        responder_discord_id=r.discord_user_id,
                        responder_username=member_names.get(r.discord_user_id),
                        responded_at=r.sent_at,
                    )
                    for r in rows
                    if r.message_id not in existing_ids
                ]
                if new_objs:
                    db_session.bulk_save_objects(new_objs)
                return len(new_objs)

        loop = asyncio.get_running_loop()
        inserted = await loop.run_in_executor(None, _do_backfill)

        logger.info("Done. Volunteer contributions inserted: %d", inserted)
        await client.close()

    await client.start(token)


def main() -> None:
    load_env(ENV_PATH)
    asyncio.run(run())


if __name__ == "__main__":
    main()

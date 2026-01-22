"""
Backfill script to populate `left_at` for verified users who left before tracking was added.

This script:
1. Connects to Discord and fetches all current guild members
2. Queries all verified users with a linked discord_user_id
3. For users not currently in the guild, sets left_at to the backfill timestamp

Usage:
    python scripts/backfill_left_at.py [--dry-run] [--backfill-date YYYY-MM-DD]

Options:
    --dry-run           Preview changes without modifying the database
    --backfill-date     Date to use for left_at (default: script execution time)
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import discord

from utils.database import User, session_scope
from utils.settings import DISCORD_CONFIG

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill left_at for verified users no longer in the Discord guild."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without modifying the database",
    )
    parser.add_argument(
        "--backfill-date",
        type=str,
        default=None,
        help="Date to use for left_at (YYYY-MM-DD format). Defaults to current time.",
    )
    return parser.parse_args()


def get_verified_users_with_discord() -> list[tuple[int, str, str | None]]:
    """
    Fetch all verified users who have a linked Discord account.

    Returns:
        List of tuples: (db_id, discord_user_id, asurite_id)
    """
    users = []
    with session_scope() as session:
        query = (
            session.query(User)
            .filter(User.verified.is_(True))
            .filter(User.discord_user_id.isnot(None))
            .filter(User.left_at.is_(None))  # Only users without left_at set
        )
        for user in query.all():
            try:
                discord_id = int(user.discord_user_id)
                users.append((user.id, discord_id, user.asurite_id))
            except (TypeError, ValueError):
                logger.warning(
                    "Invalid discord_user_id for user %s: %s",
                    user.id,
                    user.discord_user_id,
                )
    return users


def update_left_at(user_ids: list[int], left_at: datetime) -> int:
    """
    Set left_at for the given user IDs.

    Returns:
        Number of users updated
    """
    if not user_ids:
        return 0

    with session_scope() as session:
        updated = (
            session.query(User)
            .filter(User.id.in_(user_ids))
            .update({User.left_at: left_at}, synchronize_session=False)
        )
        return updated


async def fetch_guild_member_ids(guild_id: int, bot_token: str) -> set[int]:
    """
    Connect to Discord and fetch all member IDs from the guild.

    Returns:
        Set of Discord user IDs currently in the guild
    """
    intents = discord.Intents.default()
    intents.members = True  # Required to fetch guild members

    client = discord.Client(intents=intents)
    member_ids: set[int] = set()

    @client.event
    async def on_ready():
        logger.info("Connected to Discord as %s", client.user)

        guild = client.get_guild(guild_id)
        if guild is None:
            logger.error("Could not find guild %s", guild_id)
            await client.close()
            return

        logger.info("Fetching members from guild: %s (%s)", guild.name, guild.id)

        # Fetch all members (this may take a while for large guilds)
        async for member in guild.fetch_members(limit=None):
            member_ids.add(member.id)

        logger.info("Found %d members in guild", len(member_ids))
        await client.close()

    await client.start(bot_token)
    return member_ids


async def run_backfill(dry_run: bool, backfill_date: datetime) -> None:
    """Main backfill logic."""
    if DISCORD_CONFIG is None:
        logger.error("DISCORD_CONFIG is not set. Cannot connect to Discord.")
        sys.exit(1)

    guild_id = DISCORD_CONFIG.guild_id
    bot_token = DISCORD_CONFIG.bot_token

    if not guild_id or not bot_token:
        logger.error("Missing guild_id or bot_token in DISCORD_CONFIG")
        sys.exit(1)

    # Step 1: Get verified users from database
    logger.info("Fetching verified users with Discord accounts...")
    verified_users = get_verified_users_with_discord()
    logger.info("Found %d verified users with Discord accounts (left_at is NULL)", len(verified_users))

    if not verified_users:
        logger.info("No users to process. Exiting.")
        return

    # Step 2: Fetch current guild members from Discord
    logger.info("Connecting to Discord to fetch guild members...")
    guild_member_ids = await fetch_guild_member_ids(guild_id, bot_token)

    if not guild_member_ids:
        logger.warning("No members found in guild. This may indicate an error.")
        return

    # Step 3: Find verified users not in the guild
    users_to_update: list[tuple[int, str | None]] = []
    for db_id, discord_id, asurite in verified_users:
        if discord_id not in guild_member_ids:
            users_to_update.append((db_id, asurite))

    logger.info(
        "Found %d verified users who are no longer in the guild",
        len(users_to_update),
    )

    if not users_to_update:
        logger.info("All verified users are still in the guild. Nothing to backfill.")
        return

    # Step 4: Preview or apply changes
    logger.info("Users to be updated:")
    for db_id, asurite in users_to_update[:20]:  # Show first 20
        logger.info("  - User ID %d (ASURITE: %s)", db_id, asurite or "N/A")
    if len(users_to_update) > 20:
        logger.info("  ... and %d more", len(users_to_update) - 20)

    if dry_run:
        logger.info("[DRY RUN] Would set left_at=%s for %d users", backfill_date.isoformat(), len(users_to_update))
        return

    # Step 5: Update database
    user_ids = [db_id for db_id, _ in users_to_update]
    updated_count = update_left_at(user_ids, backfill_date)
    logger.info("Updated left_at for %d users to %s", updated_count, backfill_date.isoformat())


def main() -> None:
    args = parse_args()

    # Parse backfill date
    if args.backfill_date:
        try:
            backfill_date = datetime.strptime(args.backfill_date, "%Y-%m-%d")
            backfill_date = backfill_date.replace(tzinfo=timezone.utc)
        except ValueError:
            logger.error("Invalid date format. Use YYYY-MM-DD.")
            sys.exit(1)
    else:
        backfill_date = datetime.now(timezone.utc)

    logger.info("=" * 60)
    logger.info("Backfill left_at Script")
    logger.info("=" * 60)
    logger.info("Mode: %s", "DRY RUN" if args.dry_run else "LIVE")
    logger.info("Backfill date: %s", backfill_date.isoformat())
    logger.info("=" * 60)

    asyncio.run(run_backfill(args.dry_run, backfill_date))

    logger.info("Done.")


if __name__ == "__main__":
    main()

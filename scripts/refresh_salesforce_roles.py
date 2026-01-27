"""
Sync Discord roles derived from Salesforce data for all users in the database.

This script:
1. Exports all users to a CSV.
2. For each user with a Discord ID, fetches Salesforce profile data.
3. Removes all roles listed in ROLE_ID_MAP, then adds roles derived from Salesforce.

By default, this is a dry run. Pass --apply to modify roles.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import os
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import discord

from utils.database import User, init_db, session_scope
from asu_discord.roles import ROLE_ID_MAP
from asu_discord.cogs.verification import role_names_from_student_profile

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

ENV_PATH = PROJECT_ROOT / ".env"


def load_env(path: Path) -> dict[str, str]:
    """Parse a .env file into a dict, ignoring comments and blank lines."""
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("\"'")
        if key:
            env[key] = value
    return env


def apply_env(env: dict[str, str]) -> None:
    """Populate os.environ with values if they are missing."""
    for key, value in env.items():
        os.environ.setdefault(key, value)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Refresh Discord roles from Salesforce for all users."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply role removals/additions. Default is dry run.",
    )
    parser.add_argument(
        "--csv-path",
        type=str,
        default=str(PROJECT_ROOT / "data" / "users.csv"),
        help="Output CSV path for all users in the database.",
    )
    return parser.parse_args()


def fetch_all_users() -> list[User]:
    with session_scope() as session:
        return session.query(User).order_by(User.id.asc()).all()


def write_role_csv(rows: list[dict[str, Any]], csv_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "id",
                "asurite_id",
                "email",
                "discord_user_id",
                "roles_current",
                "roles_after_apply",
                "status",
                "notes",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row.get("id"),
                    row.get("asurite_id"),
                    row.get("email"),
                    row.get("discord_user_id"),
                    row.get("roles_current"),
                    row.get("roles_after_apply"),
                    row.get("status"),
                    row.get("notes"),
                ]
            )


def _parse_discord_id(value: str | None, user_id: int) -> int | None:
    if not value:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        logger.warning("Invalid discord_user_id for user %s: %s", user_id, value)
        return None


def _roles_from_profile(profile: dict[str, Any]) -> list[int]:
    logical_names = role_names_from_student_profile(profile)
    role_ids: list[int] = []
    for name in sorted(logical_names):
        role_id = ROLE_ID_MAP.get(name)
        if role_id is None:
            logger.debug("No configured role id for %s", name)
            continue
        role_ids.append(role_id)
    return role_ids


async def _update_member_roles(
    *,
    member: discord.Member,
    guild: discord.Guild,
    target_role_ids: list[int],
    apply: bool,
) -> tuple[int, int]:
    role_ids_to_remove = {
        role_id for role_id in ROLE_ID_MAP.values() if guild.get_role(role_id)
    }
    current_role_ids = {role.id for role in member.roles}

    to_remove_ids = [rid for rid in role_ids_to_remove if rid in current_role_ids]
    to_add_ids = [rid for rid in target_role_ids if rid not in current_role_ids]

    roles_to_remove = [guild.get_role(rid) for rid in to_remove_ids]
    roles_to_remove = [role for role in roles_to_remove if role is not None]
    roles_to_add = [guild.get_role(rid) for rid in to_add_ids]
    roles_to_add = [role for role in roles_to_add if role is not None]

    if apply:
        if roles_to_remove:
            await member.remove_roles(
                *roles_to_remove, reason="Salesforce role refresh"
            )
        if roles_to_add:
            await member.add_roles(*roles_to_add, reason="Salesforce role refresh")

    return len(roles_to_remove), len(roles_to_add)


def _current_role_names(member: discord.Member) -> list[str]:
    reverse_map = {role_id: name for name, role_id in ROLE_ID_MAP.items()}
    names: list[str] = []
    for role in member.roles:
        name = reverse_map.get(role.id)
        if name:
            names.append(name)
    return sorted(set(names))


def _role_names_from_ids(role_ids: list[int]) -> list[str]:
    reverse_map = {role_id: name for name, role_id in ROLE_ID_MAP.items()}
    names: list[str] = []
    for role_id in role_ids:
        name = reverse_map.get(role_id)
        if name:
            names.append(name)
    return sorted(set(names))


async def run_sync(apply: bool, csv_path: Path) -> None:
    env = load_env(ENV_PATH)
    apply_env(env)

    bot_token = os.environ.get("DISCORD_BOT_TOKEN")
    guild_id_raw = os.environ.get("DISCORD_GUILD_ID")
    if not bot_token or not guild_id_raw:
        logger.error("Missing DISCORD_BOT_TOKEN or DISCORD_GUILD_ID in .env")
        sys.exit(1)

    try:
        guild_id = int(guild_id_raw)
    except ValueError:
        logger.error("DISCORD_GUILD_ID is not a valid integer: %s", guild_id_raw)
        sys.exit(1)

    init_db()

    users = fetch_all_users()
    logger.info("Loaded %d users from database", len(users))

    # Import Salesforce after env is loaded so credentials are picked up.
    from asu_discord.salesforce import get_student_profile  # noqa: WPS433

    intents = discord.Intents.default()
    intents.members = True

    client = discord.Client(intents=intents)

    stats = {
        "processed": 0,
        "skipped_no_discord": 0,
        "skipped_profile_error": 0,
        "role_removals": 0,
        "role_additions": 0,
    }
    rows: list[dict[str, Any]] = []

    @client.event
    async def on_ready() -> None:
        logger.info("Connected to Discord as %s", client.user)

        guild = client.get_guild(guild_id)
        if guild is None:
            logger.error("Could not find guild %s", guild_id)
            await client.close()
            return

        for user in users:
            discord_id = _parse_discord_id(user.discord_user_id, user.id)
            if discord_id is None:
                stats["skipped_no_discord"] += 1
                rows.append(
                    {
                        "id": user.id,
                        "asurite_id": user.asurite_id,
                        "email": user.email,
                        "discord_user_id": user.discord_user_id,
                        "roles_current": "",
                        "roles_after_apply": "",
                        "status": "skipped",
                        "notes": "missing_or_invalid_discord_id",
                    }
                )
                continue

            try:
                member = guild.get_member(discord_id)
                if member is None:
                    member = await guild.fetch_member(discord_id)
            except discord.NotFound:
                logger.warning("Discord member not found for user %s", user.id)
                stats["skipped_no_discord"] += 1
                rows.append(
                    {
                        "id": user.id,
                        "asurite_id": user.asurite_id,
                        "email": user.email,
                        "discord_user_id": user.discord_user_id,
                        "roles_current": "",
                        "roles_after_apply": "",
                        "status": "skipped",
                        "notes": "member_not_found",
                    }
                )
                continue
            except discord.HTTPException as exc:
                logger.warning(
                    "Failed to fetch Discord member %s: %s", discord_id, exc
                )
                stats["skipped_no_discord"] += 1
                rows.append(
                    {
                        "id": user.id,
                        "asurite_id": user.asurite_id,
                        "email": user.email,
                        "discord_user_id": user.discord_user_id,
                        "roles_current": "",
                        "roles_after_apply": "",
                        "status": "skipped",
                        "notes": "member_fetch_failed",
                    }
                )
                continue

            profile = get_student_profile(user.asurite_id)
            if profile.get("error"):
                logger.warning(
                    "Salesforce profile error for %s: %s",
                    user.asurite_id,
                    profile.get("error"),
                )
                stats["skipped_profile_error"] += 1
                rows.append(
                    {
                        "id": user.id,
                        "asurite_id": user.asurite_id,
                        "email": user.email,
                        "discord_user_id": user.discord_user_id,
                        "roles_current": ", ".join(_current_role_names(member)),
                        "roles_after_apply": "",
                        "status": "skipped",
                        "notes": "salesforce_profile_error",
                    }
                )
                continue

            target_role_ids = _roles_from_profile(profile)
            current_names = _current_role_names(member)
            desired_names = _role_names_from_ids(target_role_ids)
            removed, added = await _update_member_roles(
                member=member,
                guild=guild,
                target_role_ids=target_role_ids,
                apply=apply,
            )

            stats["processed"] += 1
            stats["role_removals"] += removed
            stats["role_additions"] += added
            rows.append(
                {
                    "id": user.id,
                    "asurite_id": user.asurite_id,
                    "email": user.email,
                    "discord_user_id": user.discord_user_id,
                    "roles_current": ", ".join(current_names),
                    "roles_after_apply": ", ".join(desired_names),
                    "status": "applied" if apply else "dry_run",
                    "notes": "",
                }
            )

        await client.close()

    write_role_csv(rows, csv_path)
    logger.info("Wrote %d rows to %s", len(rows), csv_path)

    await client.start(bot_token)

    logger.info(
        "Done. processed=%d skipped_no_discord=%d skipped_profile_error=%d removed=%d added=%d",
        stats["processed"],
        stats["skipped_no_discord"],
        stats["skipped_profile_error"],
        stats["role_removals"],
        stats["role_additions"],
    )


def main() -> None:
    args = parse_args()
    mode = "LIVE" if args.apply else "DRY RUN"
    logger.info("=" * 60)
    logger.info("Salesforce Role Refresh (%s)", mode)
    logger.info("=" * 60)
    asyncio.run(run_sync(args.apply, Path(args.csv_path)))


if __name__ == "__main__":
    main()

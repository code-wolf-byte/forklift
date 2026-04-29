"""
Sync Discord roles derived from Salesforce data for all users in the database.

This script:
1. Exports all users to a CSV with categorized role information.
2. For each user with a Discord ID, fetches Salesforce profile data.
3. Removes all roles listed in ROLE_ID_MAP, then adds roles derived from Salesforce.

By default, this is a dry run. Pass --apply to modify roles.

CSV output columns (data/users.csv by default):
id, asurite_id, email, discord_user_id,
first_year, transfer, graduate, upperclassmen, first_generation,
college, campus, residency, stage_name, term_code,
status, notes
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

from utils.database import User, UserRoleException, init_db, session_scope, get_exceptions_for_discord_id
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
    parser.add_argument(
        "--workers",
        type=int,
        default=10,
        help="Number of concurrent workers for processing users (default: 10).",
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
                # Academic Level (boolean columns)
                "first_year",
                "transfer",
                "graduate",
                "upperclassmen",
                # Special
                "first_generation",
                # Categories
                "college",
                "campus",
                "residency",
                # Salesforce metadata
                "stage_name",
                "term_code",
                # Processing info
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
                    row.get("first_year"),
                    row.get("transfer"),
                    row.get("graduate"),
                    row.get("upperclassmen"),
                    row.get("first_generation"),
                    row.get("college"),
                    row.get("campus"),
                    row.get("residency"),
                    row.get("stage_name"),
                    row.get("term_code"),
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


def _roles_from_profile(profile) -> list[int]:
    logical_names = role_names_from_student_profile(profile)
    role_ids: list[int] = []
    for name in sorted(logical_names):
        role_id = ROLE_ID_MAP.get(name)
        if role_id is None:
            logger.debug("No configured role id for %s", name)
            continue
        role_ids.append(role_id)
    return role_ids


def _normalize_asurite(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip()
    suffix = "@asu.edu"
    if normalized.lower().endswith(suffix):
        normalized = normalized[: -len(suffix)]
    return normalized or None


async def _update_member_roles(
    *,
    member: discord.Member,
    guild: discord.Guild,
    target_role_ids: list[int],
    apply: bool,
    protected_role_ids: set[int] | None = None,
    always_add_role_ids: list[int] | None = None,
) -> tuple[int, int]:
    _protected = protected_role_ids or set()
    role_ids_to_remove = {
        role_id
        for role_id in ROLE_ID_MAP.values()
        if guild.get_role(role_id) and role_id not in _protected
    }
    current_role_ids = {role.id for role in member.roles}

    # Target = Salesforce-derived + always-add, minus paused
    effective_target = list(target_role_ids)
    for rid in (always_add_role_ids or []):
        if rid not in effective_target:
            effective_target.append(rid)

    to_remove_ids = [rid for rid in role_ids_to_remove if rid in current_role_ids]
    to_add_ids = [rid for rid in effective_target if rid not in current_role_ids]

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


def _role_names_from_ids(role_ids: list[int]) -> list[str]:
    reverse_map = {role_id: name for name, role_id in ROLE_ID_MAP.items()}
    names: list[str] = []
    for role_id in role_ids:
        name = reverse_map.get(role_id)
        if name:
            names.append(name)
    return sorted(set(names))


RESIDENCY_ROLE_NAMES = {
    "Arizona Resident",
    "Out of State",
    "International Student",
}

COLLEGE_ROLE_NAMES = {
    "Barrett The Honors College",
    "College of Health Solutions",
    "Ira A. Fulton Schools of Engineering",
    "College of Liberal Arts and Sciences",
    "College of Global Futures",
    "Edson College of Nursing and Health Innovation",
    "Herberger Institute for Design and the Arts",
    "Thunderbird School of Global Management",
    "Mary Lou Fulton Teachers College",
    "New College of Interdisciplinary Arts and Sciences",
    "College of Integrative Sciences and Arts",
    "W.P. Carey School of Business",
    "Walter Cronkite School of Journalism and Mass Communication",
    "Watts College of Public Service and Community Solutions",
    "University College",
}

CAMPUS_ROLE_NAMES = {
    "Tempe",
    "Downtown Phoenix",
    "Polytechnic",
    "LA Center",
    "West Valley",
    "Online",
}


def _missing_category_flags(role_names: list[str]) -> tuple[bool, bool, bool]:
    role_set = set(role_names)
    missing_residency = not any(name in role_set for name in RESIDENCY_ROLE_NAMES)
    missing_college = not any(name in role_set for name in COLLEGE_ROLE_NAMES)
    missing_campus = not any(name in role_set for name in CAMPUS_ROLE_NAMES)
    return missing_residency, missing_college, missing_campus


def _diagnose_missing_roles(
    profile: dict[str, Any],
    missing_residency: bool,
    missing_college: bool,
    missing_campus: bool,
) -> list[str]:
    """
    Diagnose why roles are missing - either data missing from Salesforce
    or a parsing/mapping issue.
    """
    notes = []

    if missing_residency:
        state = profile.get("state")
        is_international = profile.get("international") or profile.get("is_international")
        if is_international:
            # International students should have the International Student role
            notes.append("residency: international flag set but role not assigned (parsing)")
        elif not state:
            notes.append("residency: state missing in Salesforce contact")
        else:
            notes.append(f"residency: state='{state}' not mapped (parsing)")

    if missing_college:
        college_code = profile.get("collegeProgramCode")
        college_name = profile.get("college")
        if not college_code and not college_name:
            notes.append("college: no collegeProgramCode in Salesforce")
        elif college_code:
            notes.append(f"college: code='{college_code}' not mapped (parsing)")
        elif college_name:
            notes.append(f"college: name='{college_name}' not in ROLE_ID_MAP (parsing)")

    if missing_campus:
        location = profile.get("locationName") or profile.get("campus")
        if not location or location == "N/A":
            notes.append("campus: no locationName in Salesforce")
        else:
            notes.append(f"campus: location='{location}' not mapped (parsing)")

    # Check stage - non-enrolled/admitted users may have incomplete data
    stage = profile.get("stageName")
    if stage and stage.lower() not in {"enrolled", "admitted"}:
        notes.append(f"stage '{stage}' may have incomplete data")

    return notes


def _derive_role_flags(role_names: list[str]) -> dict[str, Any]:
    """Derive categorized role flags from a list of role names."""
    role_set = set(role_names)

    # Academic level flags (boolean)
    first_year = "First Year" in role_set
    transfer = "Transfer Student" in role_set
    graduate = "Graduate Student" in role_set
    upperclassmen = "Upperclassmen" in role_set

    # Special flags
    first_generation = "First Generation Student" in role_set

    # College (single value)
    college = ""
    for name in COLLEGE_ROLE_NAMES:
        if name in role_set:
            college = name
            break

    # Campus (single value)
    campus = ""
    for name in CAMPUS_ROLE_NAMES:
        if name in role_set:
            campus = name
            break

    # Residency (single value)
    residency = ""
    for name in ("International Student", "Arizona Resident", "Out of State"):
        if name in role_set:
            residency = name
            break

    return {
        "first_year": first_year,
        "transfer": transfer,
        "graduate": graduate,
        "upperclassmen": upperclassmen,
        "first_generation": first_generation,
        "college": college,
        "campus": campus,
        "residency": residency,
    }


async def _process_user(
    user: User,
    guild: discord.Guild,
    get_student_profile,
    apply: bool,
    semaphore: asyncio.Semaphore,
) -> dict[str, Any] | None:
    """Process a single user and return their row data or None if skipped."""
    async with semaphore:
        asurite_id = _normalize_asurite(user.asurite_id)
        if not user.asurite_id:
            logger.debug("User %s: skipped (no asurite_id)", user.id)
            return {"status": "skipped_profile_error"}

        discord_id = _parse_discord_id(user.discord_user_id, user.id)
        if discord_id is None:
            logger.debug("User %s (%s): skipped (no discord_id)", user.id, user.asurite_id)
            return {"status": "skipped_no_discord"}

        try:
            member = guild.get_member(discord_id)
            if member is None:
                member = await guild.fetch_member(discord_id)
        except discord.NotFound:
            logger.info("User %s (%s): Discord member not found", user.id, user.asurite_id)
            return {"status": "skipped_no_discord"}
        except discord.HTTPException as exc:
            logger.warning(
                "User %s (%s): failed to fetch Discord member: %s", user.id, user.asurite_id, exc
            )
            return {"status": "skipped_no_discord"}

        if not asurite_id:
            logger.debug("User %s: skipped (normalized asurite_id empty)", user.id)
            return {"status": "skipped_profile_error"}

        # Avoid blocking the Discord gateway heartbeat with sync HTTP calls.
        profile = await asyncio.to_thread(get_student_profile, asurite_id)
        if profile is None:
            logger.info("User %s (%s): no Salesforce profile returned", user.id, user.asurite_id)
            return {"status": "skipped_profile_error"}

        target_role_ids = _roles_from_profile(profile)

        # Respect per-user role exceptions.
        exceptions = await asyncio.to_thread(get_exceptions_for_discord_id, str(discord_id))
        paused_names = {e.role_name for e in exceptions if e.exception_type == "paused"}
        added_names = {e.role_name for e in exceptions if e.exception_type == "added"}
        protected_role_ids = {
            ROLE_ID_MAP[name]
            for name in (paused_names | added_names)
            if name in ROLE_ID_MAP
        }
        # Remove paused roles from Salesforce-derived targets.
        target_role_ids = [
            rid for rid in target_role_ids
            if rid not in {ROLE_ID_MAP.get(n) for n in paused_names}
        ]
        always_add_ids = [ROLE_ID_MAP[n] for n in added_names if n in ROLE_ID_MAP]

        desired_names = _role_names_from_ids(target_role_ids) + sorted(added_names - paused_names)
        role_flags = _derive_role_flags(desired_names)
        (
            missing_residency_role,
            missing_college_role,
            missing_campus_role,
        ) = _missing_category_flags(desired_names)
        removed, added = await _update_member_roles(
            member=member,
            guild=guild,
            target_role_ids=target_role_ids,
            apply=apply,
            protected_role_ids=protected_role_ids,
            always_add_role_ids=always_add_ids,
        )

        # Diagnose why roles are missing
        notes_parts = _diagnose_missing_roles(
            profile,
            missing_residency_role,
            missing_college_role,
            missing_campus_role,
        )

        action = "applied" if apply else "dry_run"
        logger.info(
            "User %s (%s): %s, -%d/+%d roles, assigned=[%s]",
            user.id,
            user.asurite_id,
            action,
            removed,
            added,
            ", ".join(desired_names) if desired_names else "none",
        )

        return {
            "status": "processed",
            "removed": removed,
            "added": added,
            "row": {
                "id": user.id,
                "asurite_id": user.asurite_id,
                "email": user.email,
                "discord_user_id": user.discord_user_id,
                "first_year": role_flags["first_year"],
                "transfer": role_flags["transfer"],
                "graduate": role_flags["graduate"],
                "upperclassmen": role_flags["upperclassmen"],
                "first_generation": role_flags["first_generation"],
                "college": role_flags["college"],
                "campus": role_flags["campus"],
                "residency": role_flags["residency"],
                "stage_name": profile.get("stageName") or "",
                "term_code": profile.get("termCode") or "",
                "status": "applied" if apply else "dry_run",
                "notes": "; ".join(notes_parts),
            },
        }


async def run_sync(apply: bool, csv_path: Path, workers: int) -> None:
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
        logger.info("Processing users with %d concurrent workers", workers)

        guild = client.get_guild(guild_id)
        if guild is None:
            logger.error("Could not find guild %s", guild_id)
            await client.close()
            return

        semaphore = asyncio.Semaphore(workers)

        # Create tasks for all users
        tasks = [
            _process_user(user, guild, get_student_profile, apply, semaphore)
            for user in users
        ]

        # Process all users concurrently with progress logging
        total = len(tasks)
        completed = 0
        for coro in asyncio.as_completed(tasks):
            result = await coro
            completed += 1
            if completed % 50 == 0 or completed == total:
                logger.info("Progress: %d/%d users processed", completed, total)

            if result is None:
                continue

            status = result.get("status")
            if status == "skipped_no_discord":
                stats["skipped_no_discord"] += 1
            elif status == "skipped_profile_error":
                stats["skipped_profile_error"] += 1
            elif status == "processed":
                stats["processed"] += 1
                stats["role_removals"] += result.get("removed", 0)
                stats["role_additions"] += result.get("added", 0)
                if result.get("row"):
                    rows.append(result["row"])

        await client.close()

    await client.start(bot_token)

    write_role_csv(rows, csv_path)
    logger.info("Wrote %d rows to %s", len(rows), csv_path)

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
    asyncio.run(run_sync(args.apply, Path(args.csv_path), args.workers))


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import os
import sys
from pathlib import Path

ROLE_ID_MAP = {
    # Special Roles
    "Special Roles" : {
    "First Generation Student": 1210322592544596030,
    },
    # Academic Level Roles
    "Academic Level Roles": {
    "First Year": 1187164746454138900,
    "Transfer Student": 1187164763189416078,
    "Graduate Student": 1187164940923060284,
    "Upperclassmen": 1205549707938766878,
    },
    # College Roles
    "College Roles": {
    "Barrett The Honors College": 1187459588287635466,
    "Ira A. Fulton Schools of Engineering": 1187460517422444676,
    "College of Liberal Arts and Sciences": 1187460910936232099,
    "College of Global Futures": 1187459643304312852,
    "Edson College of Nursing and Health Innovation": 1187460135434588322,
    "Herberger Institute for Design and the Arts": 1187460355618779316,
    "Thunderbird School of Global Management": 1187460980247117865,
    "Mary Lou Fulton Teachers College": 1187460649798881432,
    "New College of Interdisciplinary Arts and Sciences": 1187460740316151831,
    "College of Integrative Sciences and Arts": 1187459946552492112,
    "W.P. Carey School of Business": 1187461362356605039,
    "Walter Cronkite School of Journalism and Mass Communication": 1187461060320571442,
    "Watts College of Public Service and Community Solutions": 1187461173533233192,
    "University College": 1263595373058981898,
    },
    # Campus Roles
    "Campus Roles": {
    "Tempe": 1282464973255348366,
    "Downtown Phoenix": 1282465059431252051,
    "Polytechnic": 1282465090808971397,
    "LA Center": 1282501414433849378,
    "West Valley": 1282465131749576704,
    "Online": 1465991804993278113,
    },
    # Residency Status Roles
    "Residency Status Roles": {
    "Out of State": 1333934752490848377,
    "Arizona Resident": 1333934478887882823,
    "International Student": 1187457897966338129,
    }
}


GUILD_ID = 1187144343400751234
VERIFIED_ROLE_ID = 1207423172803035176

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def load_env(path: Path) -> dict[str, str]:
    """Parse a .env file into a dict, ignoring comments and blank lines."""
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
    """Populate os.environ with values if they are missing."""
    for key, value in env.items():
        os.environ.setdefault(key, value)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Export Discord members missing any Academic, College, Campus, or Residency role."
        )
    )
    parser.add_argument(
        "--csv-path",
        type=str,
        default=str(PROJECT_ROOT / "data" / "missing_student_roles.csv"),
        help="Output CSV path.",
    )
    parser.add_argument(
        "--include-unverified",
        action="store_true",
        help="Include members without the verified role.",
    )
    parser.add_argument(
        "--include-bots",
        action="store_true",
        help="Include bot accounts in the export.",
    )
    return parser.parse_args()


def _category_role_maps() -> tuple[dict[str, set[int]], dict[int, str]]:
    category_role_ids: dict[str, set[int]] = {}
    role_name_by_id: dict[int, str] = {}
    for category, mapping in ROLE_ID_MAP.items():
        if not isinstance(mapping, dict):
            continue
        category_role_ids[category] = set(mapping.values())
        for name, role_id in mapping.items():
            role_name_by_id[role_id] = name
    return category_role_ids, role_name_by_id


def _format_role_names(role_ids: list[int], role_name_by_id: dict[int, str]) -> str:
    names = [role_name_by_id.get(role_id, str(role_id)) for role_id in role_ids]
    names = [name for name in names if name]
    names.sort()
    return "; ".join(names)


async def run_export(
    *,
    csv_path: Path,
    include_unverified: bool,
    include_bots: bool,
) -> None:
    try:
        import discord
    except ImportError as exc:
        raise SystemExit("discord.py is not installed.") from exc

    env = load_env(ENV_PATH)
    apply_env(env)

    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        raise SystemExit("DISCORD_BOT_TOKEN is not set in the environment or .env.")

    intents = discord.Intents.all()

    client = discord.Client(intents=intents)
    category_role_ids, role_name_by_id = _category_role_maps()
    target_categories = [
        "Academic Level Roles",
        "College Roles",
        "Campus Roles",
        "Residency Status Roles",
    ]

    rows: list[list[str]] = []
    stats = {
        "members_total": 0,
        "members_exported": 0,
        "members_skipped_unverified": 0,
        "members_skipped_bots": 0,
    }

    @client.event
    async def on_ready() -> None:
        logger.info("Connected to Discord as %s", client.user)
        guild = client.get_guild(GUILD_ID)
        if guild is None:
            logger.error("Guild %s not found", GUILD_ID)
            await client.close()
            return

        verified_role = guild.get_role(VERIFIED_ROLE_ID)
        if verified_role is None:
            logger.warning("Verified role %s not found", VERIFIED_ROLE_ID)

        logger.info("Fetching members from Discord (this may take a while).")
        async for member in guild.fetch_members(limit=None):
            stats["members_total"] += 1
            logger.info(
                "Checking member=%s (%s) display=%s",
                member.name,
                member.id,
                member.display_name,
            )
            if not include_bots and member.bot:
                stats["members_skipped_bots"] += 1
                continue
            if not include_unverified and verified_role and verified_role not in member.roles:
                stats["members_skipped_unverified"] += 1
                continue

            member_role_ids = [role.id for role in member.roles]
            category_roles: dict[str, list[int]] = {}
            missing_flags: dict[str, bool] = {}
            for category in target_categories:
                ids = category_role_ids.get(category, set())
                matched = [rid for rid in member_role_ids if rid in ids]
                category_roles[category] = matched
                missing_flags[category] = len(matched) == 0

            if not any(missing_flags.values()):
                continue

            missing_categories = [
                category
                for category in target_categories
                if missing_flags.get(category, False)
            ]
            missing_categories_text = "; ".join(missing_categories)

            rows.append(
                [
                    str(member.id),
                    member.name,
                    member.display_name,
                    "yes" if verified_role and verified_role in member.roles else "no",
                    _format_role_names(
                        category_roles["Academic Level Roles"], role_name_by_id
                    ),
                    _format_role_names(
                        category_roles["College Roles"], role_name_by_id
                    ),
                    _format_role_names(
                        category_roles["Campus Roles"], role_name_by_id
                    ),
                    _format_role_names(
                        category_roles["Residency Status Roles"], role_name_by_id
                    ),
                    missing_categories_text,
                ]
            )
            stats["members_exported"] += 1

        await client.close()

    await client.start(token)

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "discord_user_id",
                "username",
                "display_name",
                "verified",
                "academic_level_roles",
                "college_roles",
                "campus_roles",
                "residency_roles",
                "missing_categories",
            ]
        )
        writer.writerows(rows)

    logger.info("Wrote %d rows to %s", len(rows), csv_path)
    logger.info(
        "Done. total=%d exported=%d skipped_unverified=%d skipped_bots=%d",
        stats["members_total"],
        stats["members_exported"],
        stats["members_skipped_unverified"],
        stats["members_skipped_bots"],
    )


def main() -> None:
    args = parse_args()
    asyncio.run(
        run_export(
            csv_path=Path(args.csv_path),
            include_unverified=args.include_unverified,
            include_bots=args.include_bots,
        )
    )


if __name__ == "__main__":
    main()

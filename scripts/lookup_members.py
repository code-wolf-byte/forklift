"""Look up Discord members by server nickname / username and print their name and email from the DB."""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"

sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

GUILD_ID = 1187144343400751234

# Names / server nicknames to look up (edit or pass via --names)
DEFAULT_NAMES = [
    "Maidemons",
    ":hatched_chick:",
    "Allison F.",
    "manuelrd64",
    "MasonB",
    "Autumn B)",
    "Adz",
    "Ibrahim Absolom's",
    "Christian",
    "VE",
    "Natalia Rodriguez",
    "Perry the Palestinian Platypus",
    "vv4mpzzz",
    "Deepak",
    "Viper_Boy",
    ":sparkles: Luce :sparkles:",
    "Adam Blomquist",
    "Isaac",
    "monklerheee",
    "Ellou",
    "NBA YOUNGBOY",
    "Katie",
    "McRib :meat_on_bone:",
    "JC",
    "rabid_stray_dog",
]


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


def _normalize(s: str) -> str:
    """Lowercase and strip for comparison."""
    return s.strip().lower()


async def lookup(names: list[str]) -> None:
    try:
        import discord
    except ImportError as exc:
        raise SystemExit("discord.py is not installed.") from exc

    from utils.database import get_session, User

    env = load_env(ENV_PATH)
    apply_env(env)

    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        raise SystemExit("DISCORD_BOT_TOKEN is not set in the environment or .env.")

    target_normalized = {_normalize(n): n for n in names}

    intents = discord.Intents.default()
    intents.members = True
    client = discord.Client(intents=intents)

    results: list[tuple[str, str, str | None, str | None]] = []  # (query, discord_id, full_name, email)

    @client.event
    async def on_ready() -> None:
        guild = client.get_guild(GUILD_ID)
        if guild is None:
            print(f"ERROR: Guild {GUILD_ID} not found.")
            await client.close()
            return

        print(f"Connected as {client.user}. Fetching members...")
        remaining = dict(target_normalized)  # normalized -> original query

        async for member in guild.fetch_members(limit=None):
            if not remaining:
                break

            matched_query: str | None = None
            for norm_key in list(remaining.keys()):
                display_norm = _normalize(member.display_name)
                username_norm = _normalize(member.name)
                if norm_key in (display_norm, username_norm):
                    matched_query = remaining.pop(norm_key)
                    break

            if matched_query is None:
                continue

            discord_id = str(member.id)
            full_name: str | None = None
            email: str | None = None

            db = get_session()
            try:
                user = db.query(User).filter(User.discord_user_id == discord_id).first()
                if user:
                    full_name = user.full_name
                    email = user.email
            finally:
                db.close()

            results.append((matched_query, discord_id, full_name, email))

        # Report any not found
        for norm_key, original in remaining.items():
            results.append((original, "NOT FOUND", None, None))

        await client.close()

    await client.start(token)

    # Print results
    print()
    col_w = max(len(r[0]) for r in results) + 2 if results else 20
    header = f"{'Query':<{col_w}}  {'Discord ID':<22}  {'Full Name':<30}  {'Email'}"
    print(header)
    print("-" * len(header))
    for query, discord_id, full_name, email in sorted(results, key=lambda r: r[0].lower()):
        fn = full_name or "(not in DB)"
        em = email or "(not in DB)"
        if discord_id == "NOT FOUND":
            fn = em = ""
        print(f"{query:<{col_w}}  {discord_id:<22}  {fn:<30}  {em}")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Look up Discord members by server nickname and print name+email from DB.")
    parser.add_argument(
        "--names",
        nargs="+",
        metavar="NAME",
        help="Names to look up (overrides built-in list).",
    )
    args = parser.parse_args()
    names = args.names if args.names else DEFAULT_NAMES
    asyncio.run(lookup(names))


if __name__ == "__main__":
    main()

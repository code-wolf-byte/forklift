"""List every channel in the Devil2Devil Discord server, grouped by category.

Usage:
    python scripts/list_channels.py [--env-file .env] [--csv data/channels.csv]
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import requests
from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parent.parent
API = "https://discord.com/api/v10"
D2D_GUILD_ID = "1187144343400751234"
TYPES = {0: "text", 2: "voice", 4: "category", 5: "announcement", 13: "stage", 15: "forum", 16: "media"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--env-file", default=str(PROJECT_ROOT / ".env"))
    parser.add_argument("--guild", default=D2D_GUILD_ID)
    parser.add_argument("--csv", help="Also write the channel list to this CSV path.")
    args = parser.parse_args()

    env = dotenv_values(args.env_file)
    headers = {"Authorization": f"Bot {env['DISCORD_BOT_TOKEN']}"}
    resp = requests.get(f"{API}/guilds/{args.guild}/channels", headers=headers, timeout=15)
    resp.raise_for_status()
    channels = resp.json()

    names = {c["id"]: c["name"] for c in channels if c["type"] == 4}
    rows = sorted(
        (c for c in channels if c["type"] != 4),
        key=lambda c: (c.get("parent_id") is not None, names.get(c.get("parent_id"), ""), c["position"]),
    )
    current = object()
    for c in rows:
        if c.get("parent_id") != current:
            current = c.get("parent_id")
            print(f"\n[{names.get(current, 'No category')}]")
        print(f"  #{c['name']:<32} {TYPES.get(c['type'], c['type']):<12} {c['id']}  {(c.get('topic') or '').replace(chr(10), ' ')[:60]}")
    print(f"\n{len(rows)} channels in {len(names)} categories")

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["category", "name", "type", "id", "topic"])
            for c in rows:
                w.writerow([names.get(c.get("parent_id"), ""), c["name"], TYPES.get(c["type"], c["type"]), c["id"], c.get("topic") or ""])


if __name__ == "__main__":
    main()

"""Archive last year's Devil2Devil cohort channels into "Archive  2026".

Moves every channel in the cohort categories below into the archive category,
syncs its permissions to the category (hidden from @everyone), strips the
"emoji・" prefix from its name, archives open threads in the Q&A forum, and
deletes the emptied categories. Dry run unless --apply is passed; --apply first
writes a JSON snapshot of every touched channel/category for rollback.

Usage:
    python scripts/archive_channels.py [--apply]
    python scripts/archive_channels.py --archive "Archive 2026 - Pt. 2" --categories Minecraft --apply
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

import requests
from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parent.parent
API = "https://discord.com/api/v10"
GUILD_ID = "1187144343400751234"
ARCHIVE_CATEGORY = "Archive  2026"  # sic, two spaces
# Nov 2025 cohort. Unverified (verify-here), Minecraft and #coming-soon stay live.
COHORT_CATEGORIES = [
    "News", "Server Guide", "Support", "Rewards", "Connect", "Talk", "Share",
    "Campus Chat", "Roommate Finder", "Graduate", "Activities and Games",
]
MAX_PER_CATEGORY = 50


def call(session: requests.Session, method: str, path: str, **kw):
    while True:
        resp = session.request(method, f"{API}{path}", timeout=15, **kw)
        if resp.status_code == 429:
            time.sleep(resp.json().get("retry_after", 1) + 0.1)
            continue
        resp.raise_for_status()
        return resp.json() if resp.content else None


def clean(name: str) -> str:
    return name.split("・")[-1].strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--env-file", default=str(PROJECT_ROOT / ".env"))
    parser.add_argument("--archive", default=ARCHIVE_CATEGORY, help="Destination category; created hidden if missing.")
    parser.add_argument("--categories", nargs="+", default=COHORT_CATEGORIES, help="Categories to empty and delete.")
    parser.add_argument("--apply", action="store_true", help="Actually make the changes.")
    args = parser.parse_args()

    env = dotenv_values(args.env_file)
    s = requests.Session()
    s.headers["Authorization"] = f"Bot {env['DISCORD_BOT_TOKEN']}"
    channels = call(s, "GET", f"/guilds/{GUILD_ID}/channels")

    cats = {c["name"]: c for c in channels if c["type"] == 4}
    missing = [n for n in args.categories if n not in cats]
    if missing:
        raise SystemExit(f"Categories not found: {missing}")
    # New archive categories only hide from @everyone, like the existing ones.
    archive = cats.get(args.archive) or {"id": None, "name": args.archive, "permission_overwrites": [
        {"id": GUILD_ID, "type": 0, "allow": "0", "deny": "1024"}]}
    source_ids = {cats[n]["id"] for n in args.categories}
    cat_pos = {c["id"]: c["position"] for c in cats.values()}
    moving = sorted(
        (c for c in channels if c.get("parent_id") in source_ids),
        key=lambda c: (cat_pos[c["parent_id"]], c["position"]),
    )
    already = [c for c in channels if archive["id"] and c.get("parent_id") == archive["id"]]
    if len(already) + len(moving) > MAX_PER_CATEGORY:
        raise SystemExit(f"{len(already)} + {len(moving)} channels exceeds Discord's {MAX_PER_CATEGORY}-per-category limit")

    # Q&A forum threads still open, if the forum is being archived.
    qna_id = env.get("QNA_FORUM_CHANNEL_ID")
    qna_threads = []
    if any(c["id"] == qna_id for c in moving):
        active = call(s, "GET", f"/guilds/{GUILD_ID}/threads/active")["threads"]
        qna_threads = [t for t in active if t.get("parent_id") == qna_id]

    by_id = {c["id"]: c for c in channels}
    print(f"Move into [{args.archive}]{'' if archive['id'] else ' (new)'} ({len(already)} there now, {len(already) + len(moving)} after):")
    for c in moving:
        print(f"  [{by_id[c['parent_id']]['name']}] #{c['name']}  ->  #{clean(c['name'])}")
    renames = [c for c in already if clean(c["name"]) != c["name"]]
    print(f"\nRename already-archived ({len(renames)}):")
    for c in renames:
        print(f"  #{c['name']}  ->  #{clean(c['name'])}")
    print(f"\nArchive {len(qna_threads)} open threads in Q&A forum #{by_id.get(qna_id, {}).get('name')}")
    print(f"Delete {len(args.categories)} emptied categories: {', '.join(args.categories)}")

    if not args.apply:
        print("\nDry run. Re-run with --apply to make these changes.")
        return

    snap = PROJECT_ROOT / "data" / f"archive_snapshot_{datetime.now():%Y%m%d_%H%M%S}.json"
    snap.parent.mkdir(parents=True, exist_ok=True)
    snap.write_text(json.dumps({
        "channels": moving + renames,
        "categories": [cats[n] for n in args.categories],
        "qna_threads": [t["id"] for t in qna_threads],
    }, indent=2))
    print(f"\nSnapshot written to {snap}")
    if not archive["id"]:
        archive = call(s, "POST", f"/guilds/{GUILD_ID}/channels", json={
            "name": args.archive, "type": 4, "permission_overwrites": archive["permission_overwrites"]})
        print(f"  created category [{args.archive}]")

    failed = []
    for c in moving:
        try:
            call(s, "PATCH", f"/channels/{c['id']}", json={
                "name": clean(c["name"]),
                "parent_id": archive["id"],
                "permission_overwrites": archive["permission_overwrites"],
            })
            print(f"  moved #{clean(c['name'])}")
        except requests.HTTPError as exc:
            failed.append(c["name"])
            print(f"  FAILED #{c['name']}: {exc.response.text}")
    for c in renames:
        try:
            call(s, "PATCH", f"/channels/{c['id']}", json={"name": clean(c["name"])})
        except requests.HTTPError as exc:
            failed.append(c["name"])
            print(f"  FAILED rename #{c['name']}: {exc.response.text}")
    for t in qna_threads:
        try:
            call(s, "PATCH", f"/channels/{t['id']}", json={"archived": True})
        except requests.HTTPError as exc:
            failed.append(t["name"])
            print(f"  FAILED thread {t['name']}: {exc.response.text}")

    if failed:
        print(f"\n{len(failed)} failures; leaving categories in place so nothing is orphaned.")
        return
    for n in args.categories:
        call(s, "DELETE", f"/channels/{cats[n]['id']}")
        print(f"  deleted category [{n}]")
    print("\nDone.")


if __name__ == "__main__":
    main()

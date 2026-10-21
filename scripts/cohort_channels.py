"""Set up and tear down the yearly Devil2Devil cohort channels from config/cohort_channels.yaml.

    export    Write the live layout of the config's categories (or --categories) to the config.
    setup     Create any missing categories/channels from the config, placed above existing categories.
              Uncategorized live channels with a matching name are moved in instead of duplicated.
    teardown  Move every channel in the config's categories into an archive category (hidden per
              archive_permissions), strip "emoji・" prefixes, archive open Q&A threads, delete the
              emptied categories. Writes a JSON snapshot to data/ first.

setup and teardown are dry runs unless --apply is passed; both are safe to re-run after a failure.

Usage:
    python scripts/cohort_channels.py export
    python scripts/cohort_channels.py setup [--apply]
    python scripts/cohort_channels.py teardown --archive "Archive 2027" [--apply]
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

import discord
import requests
import yaml
from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG = PROJECT_ROOT / "config" / "cohort_channels.yaml"
API = "https://discord.com/api/v10"
GUILD_ID = "1187144343400751234"
MAX_PER_CATEGORY = 50
TYPES = {"text": 0, "voice": 2, "category": 4, "announcement": 5, "stage": 13, "forum": 15}
TYPE_NAMES = {v: k for k, v in TYPES.items()}
# Channel settings copied to/from the config, per type.
FIELDS = {
    0: ["topic", "nsfw", "rate_limit_per_user", "default_auto_archive_duration"],
    2: ["nsfw", "bitrate", "user_limit", "rtc_region"],
    5: ["topic", "nsfw", "default_auto_archive_duration"],
    13: ["bitrate", "user_limit", "rtc_region"],
    15: ["topic", "nsfw", "rate_limit_per_user", "flags", "available_tags", "default_reaction_emoji",
         "default_sort_order", "default_forum_layout", "default_thread_rate_limit_per_user"],
}
HEADER = """\
# Devil2Devil cohort channel layout, used by scripts/cohort_channels.py.
#
# setup creates these categories/channels (top of the server, in this order);
# teardown archives whatever is in these categories. Regenerate from the live
# server with `python scripts/cohort_channels.py export` after editing in Discord.
#
# permissions: role name -> {allow: [...], deny: [...]}, using discord.py
#   permission names (view_channel, send_messages, ...); a bare number holds
#   flags py-cord has no name for yet. A channel without `permissions` is synced
#   to its category.
# qna_forum: true marks the forum the Q&A bot watches (QNA_FORUM_CHANNEL_ID).
"""


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


def perm_names(value: str) -> list:
    names = [n for n, on in discord.Permissions(int(value)) if on]
    unknown = int(value) & ~perm_bits(names)  # flags newer than py-cord stay as a raw int
    return names + [unknown] if unknown else names


def perm_bits(spec: list) -> int:
    return sum(x for x in spec if isinstance(x, int)) | discord.Permissions(
        **dict.fromkeys((x for x in spec if isinstance(x, str)), True)).value


def to_config_perms(overwrites: list[dict], role_names: dict[str, str]) -> dict:
    out = {}
    for o in overwrites:
        if o["type"] != 0:  # per-member overwrites don't carry over between cohorts
            continue
        spec = {k: perm_names(o[k]) for k in ("allow", "deny") if int(o[k])}
        out[role_names[o["id"]]] = spec
    return out


def to_overwrites(perms: dict, role_ids: dict[str, str]) -> list[dict]:
    out = []
    for role, spec in perms.items():
        if role not in role_ids:
            raise SystemExit(f"Role {role!r} in config not found on the server")
        bits = {k: perm_bits(spec.get(k, [])) for k in ("allow", "deny")}
        out.append({"id": role_ids[role], "type": 0, "allow": str(bits["allow"]), "deny": str(bits["deny"])})
    return out


def channel_config(c: dict, cat: dict, role_names: dict[str, str], qna_id: str | None) -> dict:
    entry = {"name": c["name"], "type": TYPE_NAMES[c["type"]]}
    if c["id"] == qna_id:
        entry["qna_forum"] = True
    perms = to_config_perms(c["permission_overwrites"], role_names)
    if perms != to_config_perms(cat["permission_overwrites"], role_names):
        entry["permissions"] = perms
    for f in FIELDS.get(c["type"], []):
        if c.get(f):  # skip unset/default (None, False, 0, [])
            entry[f] = c[f]
    if "available_tags" in entry:
        entry["available_tags"] = [{k: v for k, v in t.items() if k != "id" and v} for t in entry["available_tags"]]
    return entry


def channel_payload(entry: dict, parent_id: str, cat_perms: dict, role_ids: dict[str, str]) -> dict:
    body = {k: v for k, v in entry.items() if k not in ("qna_forum", "permissions")}
    body["type"] = TYPES[entry["type"]]
    body["parent_id"] = parent_id
    body["permission_overwrites"] = to_overwrites(entry.get("permissions", cat_perms), role_ids)
    return body


def export(s, channels, roles, config, args, env) -> None:
    role_names = {r["id"]: r["name"] for r in roles}
    cats = {c["name"]: c for c in channels if c["type"] == 4}
    names = args.categories or [c["name"] for c in config["categories"]]
    missing = [n for n in names if n not in cats]
    if missing:
        raise SystemExit(f"Categories not found: {missing}")
    out = {"archive_permissions": config.get("archive_permissions", {"@everyone": {"deny": ["view_channel"]}}),
           "categories": []}
    for n in names:
        cat = cats[n]
        kids = sorted((c for c in channels if c.get("parent_id") == cat["id"]), key=lambda c: c["position"])
        out["categories"].append({
            "name": n,
            "permissions": to_config_perms(cat["permission_overwrites"], role_names),
            "channels": [channel_config(c, cat, role_names, env.get("QNA_FORUM_CHANNEL_ID")) for c in kids],
        })
    CONFIG.write_text(HEADER + "\n" + yaml.safe_dump(out, sort_keys=False, allow_unicode=True, width=200, default_flow_style=None),
                      encoding="utf-8")
    print(f"Wrote {sum(len(c['channels']) for c in out['categories'])} channels in {len(names)} categories to {CONFIG}")


def setup(s, channels, roles, config, args, env) -> None:
    role_ids = {r["name"]: r["id"] for r in roles}
    live_cats = {c["name"]: c for c in channels if c["type"] == 4}
    stragglers = {clean(c["name"]): c for c in channels if c["type"] != 4 and not c.get("parent_id")}

    plan = []
    for cat in config["categories"]:
        existing = live_cats.get(cat["name"])
        present = {clean(c["name"]) for c in channels if existing and c.get("parent_id") == existing["id"]}
        steps = [(e, "exists" if clean(e["name"]) in present else "move" if clean(e["name"]) in stragglers else "create")
                 for e in cat["channels"]]
        plan.append((cat, existing, steps))
        print(f"[{cat['name']}]{' (exists)' if existing else ' (new)'}")
        for e, action in steps:
            print(f"  {action:<7} #{e['name']}")

    if not args.apply:
        print("\nDry run. Re-run with --apply to make these changes.")
        return

    failed, cat_ids, qna = [], [], None
    for cat, existing, steps in plan:
        if not existing:
            existing = call(s, "POST", f"/guilds/{GUILD_ID}/channels", json={
                "name": cat["name"], "type": 4, "permission_overwrites": to_overwrites(cat["permissions"], role_ids)})
            print(f"  created category [{cat['name']}]")
        cat_ids.append(existing["id"])
        for e, action in steps:
            try:
                if action == "create":
                    made = call(s, "POST", f"/guilds/{GUILD_ID}/channels",
                                json=channel_payload(e, existing["id"], cat["permissions"], role_ids))
                elif action == "move":
                    made = call(s, "PATCH", f"/channels/{stragglers[clean(e['name'])]['id']}", json={
                        "name": e["name"], "parent_id": existing["id"],
                        "permission_overwrites": to_overwrites(e.get("permissions", cat["permissions"]), role_ids)})
                else:
                    made = next(c for c in channels if c.get("parent_id") == existing["id"]
                                and clean(c["name"]) == clean(e["name"]))
                if action != "exists":
                    print(f"  {action}d #{e['name']}")
                if e.get("qna_forum"):
                    qna = made["id"]
            except requests.HTTPError as exc:
                failed.append(e["name"])
                print(f"  FAILED #{e['name']}: {exc.response.text}")

    # New categories land at the bottom; put the cohort first, keep everything else in its current order.
    others = sorted((c for c in live_cats.values() if c["id"] not in cat_ids), key=lambda c: c["position"])
    call(s, "PATCH", f"/guilds/{GUILD_ID}/channels",
         json=[{"id": cid, "position": i} for i, cid in enumerate(cat_ids + [c["id"] for c in others])])
    print("  reordered categories")

    if qna and qna != env.get("QNA_FORUM_CHANNEL_ID"):
        print(f"\nSet QNA_FORUM_CHANNEL_ID={qna} in .env and restart the bot.")
    print(f"\n{len(failed)} failures; fix and re-run." if failed else "\nDone.")


def teardown(s, channels, roles, config, args, env) -> None:
    if not args.archive:
        raise SystemExit("teardown needs --archive, e.g. --archive \"Archive 2027\"")
    role_ids = {r["name"]: r["id"] for r in roles}
    cats = {c["name"]: c for c in channels if c["type"] == 4}
    names = [n for n in (args.categories or [c["name"] for c in config["categories"]]) if n in cats]
    if not names:
        raise SystemExit("None of the config's categories exist; nothing to tear down.")
    archive = cats.get(args.archive) or {"id": None, "name": args.archive,
                                         "permission_overwrites": to_overwrites(config["archive_permissions"], role_ids)}
    source_ids = {cats[n]["id"] for n in names}
    cat_pos = {c["id"]: c["position"] for c in cats.values()}
    moving = sorted((c for c in channels if c.get("parent_id") in source_ids),
                    key=lambda c: (cat_pos[c["parent_id"]], c["position"]))
    already = [c for c in channels if archive["id"] and c.get("parent_id") == archive["id"]]
    if len(already) + len(moving) > MAX_PER_CATEGORY:
        raise SystemExit(f"{len(already)} + {len(moving)} channels exceeds Discord's {MAX_PER_CATEGORY}-per-category "
                         f"limit; split it with --categories and a second --archive (e.g. \"... - Pt. 2\")")

    qna_id = env.get("QNA_FORUM_CHANNEL_ID")
    qna_threads = []
    if any(c["id"] == qna_id for c in moving):
        active = call(s, "GET", f"/guilds/{GUILD_ID}/threads/active")["threads"]
        qna_threads = [t for t in active if t.get("parent_id") == qna_id]

    by_id = {c["id"]: c for c in channels}
    print(f"Move into [{args.archive}]{'' if archive['id'] else ' (new)'} ({len(already)} there now, "
          f"{len(already) + len(moving)} after):")
    for c in moving:
        print(f"  [{by_id[c['parent_id']]['name']}] #{c['name']}  ->  #{clean(c['name'])}")
    print(f"\nArchive {len(qna_threads)} open threads in Q&A forum #{by_id.get(qna_id, {}).get('name')}")
    print(f"Delete {len(names)} emptied categories: {', '.join(names)}")

    if not args.apply:
        print("\nDry run. Re-run with --apply to make these changes.")
        return

    snap = PROJECT_ROOT / "data" / f"archive_snapshot_{datetime.now():%Y%m%d_%H%M%S}.json"
    snap.parent.mkdir(parents=True, exist_ok=True)
    snap.write_text(json.dumps({"channels": moving, "categories": [cats[n] for n in names],
                                "qna_threads": [t["id"] for t in qna_threads]}, indent=2))
    print(f"\nSnapshot written to {snap}")
    if not archive["id"]:
        archive = call(s, "POST", f"/guilds/{GUILD_ID}/channels", json={
            "name": args.archive, "type": 4, "permission_overwrites": archive["permission_overwrites"]})
        print(f"  created category [{args.archive}]")

    failed = []
    for c in moving:
        try:
            call(s, "PATCH", f"/channels/{c['id']}", json={
                "name": clean(c["name"]), "parent_id": archive["id"],
                "permission_overwrites": archive["permission_overwrites"]})
            print(f"  moved #{clean(c['name'])}")
        except requests.HTTPError as exc:
            failed.append(c["name"])
            print(f"  FAILED #{c['name']}: {exc.response.text}")
    for t in qna_threads:
        try:
            call(s, "PATCH", f"/channels/{t['id']}", json={"archived": True})
        except requests.HTTPError as exc:
            failed.append(t["name"])
            print(f"  FAILED thread {t['name']}: {exc.response.text}")

    if failed:
        print(f"\n{len(failed)} failures; leaving categories in place so nothing is orphaned.")
        return
    for n in names:
        call(s, "DELETE", f"/channels/{cats[n]['id']}")
        print(f"  deleted category [{n}]")
    print("\nDone.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["export", "setup", "teardown"])
    parser.add_argument("--env-file", default=str(PROJECT_ROOT / ".env"))
    parser.add_argument("--categories", nargs="+", help="Override the config's category list (export/teardown).")
    parser.add_argument("--archive", help="teardown: destination category; created if missing.")
    parser.add_argument("--apply", action="store_true", help="Actually make the changes.")
    args = parser.parse_args()

    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else {"categories": []}
    if args.command != "export" and not config["categories"]:
        raise SystemExit(f"{CONFIG} is empty; run export first")
    env = dotenv_values(args.env_file)
    s = requests.Session()
    s.headers["Authorization"] = f"Bot {env['DISCORD_BOT_TOKEN']}"
    channels = call(s, "GET", f"/guilds/{GUILD_ID}/channels")
    roles = call(s, "GET", f"/guilds/{GUILD_ID}/roles")
    {"export": export, "setup": setup, "teardown": teardown}[args.command](s, channels, roles, config, args, env)


if __name__ == "__main__":
    main()

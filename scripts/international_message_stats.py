"""
International Student Message Stats — Cross-DB YoY Comparison

Links last year's members (forkman.db) to this year's message logs (forklift.db)
via Discord user ID, then compares message engagement for international students
across both cohorts.

Does NOT call Salesforce — reads from pre-generated CSVs:
  data/intl_stats_lastyear.csv   (from international_stats.py)
  data/intl_stats_thisyear.csv   (from international_stats.py)

Usage:
    python scripts/international_message_stats.py
"""
from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FORKMAN_DB   = PROJECT_ROOT / "forkman.db"
FORKLIFT_DB  = PROJECT_ROOT / "forklift.db"
LY_CSV       = PROJECT_ROOT / "data" / "intl_stats_lastyear.csv"
TY_CSV       = PROJECT_ROOT / "data" / "intl_stats_thisyear.csv"


# ---------------------------------------------------------------------------
# Load international ASURITEs from CSVs
# ---------------------------------------------------------------------------

def load_international_asuries(csv_path: Path) -> set[str]:
    """Return the set of ASURITEs flagged is_international=True in the CSV."""
    asuries: set[str] = set()
    with csv_path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("is_international", "").strip().lower() == "true":
                # Strip @asu.edu suffix if present (data quality issue in thisyear CSV)
                asurite = row["asurite"].strip().lower()
                if "@" in asurite:
                    asurite = asurite.split("@")[0]
                asuries.add(asurite)
    return asuries


# ---------------------------------------------------------------------------
# Map ASURITEs → Discord IDs
# ---------------------------------------------------------------------------

def asuries_to_discord_ids_forkman(asuries: set[str]) -> dict[str, str]:
    """
    forkman.db: emails.user_snowflake keyed by ASURITE (derived from address).
    Returns {asurite: discord_snowflake}.
    """
    con = sqlite3.connect(FORKMAN_DB)
    rows = con.execute(
        """
        SELECT LOWER(SUBSTR(address, 1, INSTR(address, '@') - 1)) AS asurite,
               user_snowflake
        FROM emails
        WHERE is_verified = 1
          AND LOWER(address) LIKE '%@asu.edu'
        """
    ).fetchall()
    con.close()
    mapping = {asurite: snowflake for asurite, snowflake in rows if asurite in asuries}
    return mapping


def asuries_to_discord_ids_forklift(asuries: set[str]) -> dict[str, str]:
    """
    forklift.db: users.discord_user_id keyed by asurite_id.
    Returns {asurite: discord_user_id}.
    """
    con = sqlite3.connect(FORKLIFT_DB)
    rows = con.execute(
        "SELECT LOWER(asurite_id), discord_user_id FROM users WHERE verified = 1"
    ).fetchall()
    con.close()
    mapping = {asurite: did for asurite, did in rows if asurite in asuries}
    return mapping


# ---------------------------------------------------------------------------
# Message stats from forklift.db
# ---------------------------------------------------------------------------

def message_stats_for_discord_ids(discord_ids: set[str], label: str) -> dict:
    """Count messages in forklift.db message_logs for a set of Discord user IDs."""
    if not discord_ids:
        return {"label": label, "discord_ids": 0, "total_msgs": 0, "unique_talkers": 0}

    con = sqlite3.connect(FORKLIFT_DB)
    placeholders = ",".join("?" * len(discord_ids))
    id_list = list(discord_ids)

    total_msgs = con.execute(
        f"SELECT COUNT(*) FROM message_logs WHERE discord_user_id IN ({placeholders})",
        id_list,
    ).fetchone()[0]

    unique_talkers = con.execute(
        f"SELECT COUNT(DISTINCT discord_user_id) FROM message_logs WHERE discord_user_id IN ({placeholders})",
        id_list,
    ).fetchone()[0]

    con.close()
    return {
        "label": label,
        "discord_ids": len(discord_ids),
        "total_msgs": total_msgs,
        "unique_talkers": unique_talkers,
    }


def overall_message_stats() -> dict:
    """Server-wide message stats for context."""
    con = sqlite3.connect(FORKLIFT_DB)
    total_msgs = con.execute("SELECT COUNT(*) FROM message_logs").fetchone()[0]
    unique_talkers = con.execute(
        """
        SELECT COUNT(DISTINCT ml.discord_user_id)
        FROM message_logs ml
        JOIN users u ON ml.discord_user_id = u.discord_user_id
        WHERE u.verified = 1
        """
    ).fetchone()[0]
    total_verified = con.execute("SELECT COUNT(*) FROM users WHERE verified = 1").fetchone()[0]
    con.close()
    return {
        "total_msgs": total_msgs,
        "unique_talkers": unique_talkers,
        "total_verified": total_verified,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    # --- Load international ASURITEs from CSVs ---
    print("Loading international students from CSVs...")
    ly_intl_asuries = load_international_asuries(LY_CSV)
    ty_intl_asuries = load_international_asuries(TY_CSV)
    print(f"  Last year  (forkman CSV):   {len(ly_intl_asuries):,} international ASURITEs")
    print(f"  This year  (forklift CSV):  {len(ty_intl_asuries):,} international ASURITEs")

    # --- Map to Discord IDs ---
    print("\nMapping ASURITEs → Discord IDs...")
    ly_discord_map = asuries_to_discord_ids_forkman(ly_intl_asuries)
    ty_discord_map = asuries_to_discord_ids_forklift(ty_intl_asuries)
    print(f"  Last year  matched:   {len(ly_discord_map):,} / {len(ly_intl_asuries):,}")
    print(f"  This year  matched:   {len(ty_discord_map):,} / {len(ty_intl_asuries):,}")

    ly_discord_ids = set(ly_discord_map.values())
    ty_discord_ids = set(ty_discord_map.values())

    overlap = ly_discord_ids & ty_discord_ids
    print(f"\n  Discord IDs in BOTH cohorts (returning members): {len(overlap):,}")

    # --- Message stats in forklift.db for each cohort ---
    print("\nQuerying message_logs in forklift.db...")
    overall  = overall_message_stats()
    ly_stats = message_stats_for_discord_ids(ly_discord_ids, "Last Year International")
    ty_stats = message_stats_for_discord_ids(ty_discord_ids, "This Year International")

    # Combined: all international Discord IDs across both years
    all_intl_ids = ly_discord_ids | ty_discord_ids
    combined_stats = message_stats_for_discord_ids(all_intl_ids, "All International (combined)")

    # --- Report ---
    def pct(n, d):
        return f"{n/d*100:.1f}%" if d else "N/A"

    def talk_rate(stats, member_count):
        return stats["unique_talkers"] / member_count * 100 if member_count else 0

    overall_tr = talk_rate(overall, overall["total_verified"])
    ly_tr      = talk_rate(ly_stats, len(ly_discord_ids))
    ty_tr      = talk_rate(ty_stats, len(ty_discord_ids))
    combined_tr = talk_rate(combined_stats, len(all_intl_ids))

    print(f"\n{'='*68}")
    print("  INTERNATIONAL STUDENT MESSAGE STATS — YoY (forklift.db message_logs)")
    print(f"{'='*68}")
    print(f"  {'Metric':<42} {'Last Year':>10}  {'This Year':>10}")
    print(f"  {'-'*66}")
    print(f"  {'Intl members identified (Salesforce CSV)':<42} {len(ly_intl_asuries):>10,}  {len(ty_intl_asuries):>10,}")
    print(f"  {'  → matched to Discord ID':<42} {len(ly_discord_ids):>10,}  {len(ty_discord_ids):>10,}")
    print(f"  {'Messages sent (in forklift.db logs)':<42} {ly_stats['total_msgs']:>10,}  {ty_stats['total_msgs']:>10,}")
    print(f"  {'  % of all server messages':<42} {pct(ly_stats['total_msgs'], overall['total_msgs']):>10}  {pct(ty_stats['total_msgs'], overall['total_msgs']):>10}")
    print(f"  {'Unique talkers':<42} {ly_stats['unique_talkers']:>10,}  {ty_stats['unique_talkers']:>10,}")
    print(f"  {'Talk rate':<42} {ly_tr:>9.1f}%  {ty_tr:>9.1f}%")
    deficit_label = f"Talk rate deficit vs overall ({overall_tr:.1f}%)"
    print(f"  {deficit_label:<42} {ly_tr - overall_tr:>+9.1f}%  {ty_tr - overall_tr:>+9.1f}%")

    print(f"\n  {'─'*66}")
    print(f"  {'Server total messages':<42} {overall['total_msgs']:>23,}")
    print(f"  {'Server unique talkers (verified)':<42} {overall['unique_talkers']:>23,}")
    print(f"  {'Overall talk rate':<42} {overall_tr:>22.1f}%")

    print(f"\n  {'─'*66}")
    print(f"  {'Combined intl (both years, deduplicated)':<42} {len(all_intl_ids):>10,}")
    print(f"  {'  Messages sent':<42} {combined_stats['total_msgs']:>10,}  ({pct(combined_stats['total_msgs'], overall['total_msgs'])} of server)")
    print(f"  {'  Unique talkers':<42} {combined_stats['unique_talkers']:>10,}")
    print(f"  {'  Talk rate':<42} {combined_tr:>9.1f}%  (deficit: {combined_tr - overall_tr:>+.1f}pp)")

    print(f"\n  NOTE: {len(overlap):,} Discord IDs appear in both cohorts (returning intl members).")
    print(f"  NOTE: Last-year message counts reflect activity logged in forklift.db,")
    print(f"        which may not cover the full prior academic year depending on backfill.")
    print()


if __name__ == "__main__":
    main()

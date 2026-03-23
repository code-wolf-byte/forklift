"""
International Student Stats Report — Year-over-Year

Compares international student engagement between:
  - Last year  (forkman.db)  — member counts from Salesforce lookups; no message logs available
  - This year  (forklift.db) — member counts, message counts, unique talkers from DB + Salesforce

Outputs a CSV per cohort and prints a summary report.

Usage:
    python scripts/international_stats.py [--concurrency N] [--limit N]

Notes:
    - Requires SALESFORCE_API_CLIENT_ID / SALESFORCE_API_CLIENT_SECRET in .env or environment.
    - forkman.db has no message_logs table; last-year message stats are unavailable.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import os
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import aiohttp

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

ENV_PATH = PROJECT_ROOT / ".env"
FORKMAN_DB = PROJECT_ROOT / "forkman.db"
FORKLIFT_DB = PROJECT_ROOT / "forklift.db"

BASE = "https://esb.asu.edu"
CONTACT_URL = f"{BASE}/api/v1/asu-sf-contact/contact"
OPP_URL = f"{BASE}/api/v1/asu-sf-opportunity/opportunity"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Env helpers
# ---------------------------------------------------------------------------

def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("\"'")
        if key:
            os.environ.setdefault(key, value)


def auth_header() -> str:
    import base64
    client_id = os.environ.get("SALESFORCE_API_CLIENT_ID", "")
    client_secret = os.environ.get("SALESFORCE_API_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        raise SystemExit("SALESFORCE_API_CLIENT_ID / SALESFORCE_API_CLIENT_SECRET not set.")
    token = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    return f"Basic {token}"


# ---------------------------------------------------------------------------
# Salesforce async helpers
# ---------------------------------------------------------------------------

TARGET_TERM_CODES = {"2267", "2261"}


def _is_admitted_or_enrolled(opp: dict) -> bool:
    stage = (opp.get("stageName") or "").strip().lower()
    return stage in {"enrolled", "admitted"}


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "y", "1", "t"}
    return False


def _select_opportunity(opportunities: list[dict]) -> dict | None:
    eligible = [o for o in opportunities if isinstance(o, dict) and _is_admitted_or_enrolled(o)]
    for opp in eligible:
        if str(opp.get("termCode") or "") in TARGET_TERM_CODES:
            return opp
    return eligible[0] if eligible else None


async def fetch_profile(
    session: aiohttp.ClientSession,
    asurite: str,
    header: str,
    sem: asyncio.Semaphore,
) -> dict[str, Any]:
    """Return a minimal profile dict with keys: country, is_international, error."""
    async with sem:
        try:
            async with session.get(
                f"{CONTACT_URL}?asurite={asurite}",
                headers={"Authorization": header},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    return {"asurite": asurite, "error": f"contact HTTP {resp.status}"}
                data = await resp.json()

            contacts = data.get("contact") or []
            if not contacts:
                return {"asurite": asurite, "error": "no contact"}

            contact = contacts[0]
            contact_id = contact.get("id")
            country = contact.get("country") or "Unknown"
            state = contact.get("state") or ""

            # Fetch opportunities
            opportunities: list[dict] = []
            for career in ("Undergraduate", "Graduate"):
                try:
                    async with session.get(
                        f"{OPP_URL}?contactId={contact_id}&career={career}",
                        headers={"Authorization": header},
                        timeout=aiohttp.ClientTimeout(total=15),
                    ) as oresp:
                        if oresp.status == 200:
                            odata = await oresp.json()
                            if isinstance(odata, list):
                                opportunities.extend(odata)
                except Exception:
                    pass

            opportunities.sort(key=lambda o: str(o.get("createdDate") or ""))
            selected = _select_opportunity(opportunities)

            is_international = False
            if selected:
                is_international = _parse_bool(selected.get("internationalStudent"))
                opp_country = selected.get("country") or country
                country = opp_country if opp_country != "Unknown" else country

            return {
                "asurite": asurite,
                "country": country,
                "state": state,
                "is_international": is_international,
                "has_opportunity": selected is not None,
                "error": None,
            }

        except Exception as exc:
            return {"asurite": asurite, "error": str(exc)}


async def bulk_fetch_profiles(
    asuries: list[str],
    concurrency: int = 10,
) -> list[dict[str, Any]]:
    header = auth_header()
    sem = asyncio.Semaphore(concurrency)
    connector = aiohttp.TCPConnector(limit=concurrency)
    results: list[dict] = []

    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [
            fetch_profile(session, asurite, header, sem)
            for asurite in asuries
        ]
        total = len(tasks)
        for i, coro in enumerate(asyncio.as_completed(tasks), 1):
            result = await coro
            results.append(result)
            if i % 100 == 0 or i == total:
                logger.info("Salesforce lookups: %d / %d", i, total)

    return results


# ---------------------------------------------------------------------------
# Database queries
# ---------------------------------------------------------------------------

def get_forkman_verified_asuries() -> list[tuple[str, str]]:
    """Return [(asurite, discord_snowflake), ...] for verified @asu.edu addresses."""
    con = sqlite3.connect(FORKMAN_DB)
    rows = con.execute(
        """
        SELECT DISTINCT
            LOWER(SUBSTR(e.address, 1, INSTR(e.address, '@') - 1)) AS asurite,
            e.user_snowflake AS discord_id
        FROM emails e
        WHERE e.is_verified = 1
          AND LOWER(e.address) LIKE '%@asu.edu'
        """
    ).fetchall()
    con.close()
    return rows


def get_forklift_asuries() -> list[tuple[str, str]]:
    """Return [(asurite, discord_user_id), ...] for verified forklift users."""
    con = sqlite3.connect(FORKLIFT_DB)
    rows = con.execute(
        """
        SELECT asurite_id, discord_user_id
        FROM users
        WHERE verified = 1
          AND asurite_id IS NOT NULL
        """
    ).fetchall()
    con.close()
    return rows


def get_forklift_message_stats() -> dict[str, Any]:
    """
    Return message stats for International Student role holders from forklift.db.
    """
    con = sqlite3.connect(FORKLIFT_DB)

    # Total members with International Student role
    total_intl = con.execute(
        """
        SELECT COUNT(DISTINCT ur.user_id)
        FROM user_roles ur
        WHERE ur.role_name = 'International Student'
        """
    ).fetchone()[0]

    # Total messages sent by international students
    total_msgs = con.execute(
        """
        SELECT COUNT(ml.id)
        FROM message_logs ml
        JOIN users u ON ml.discord_user_id = u.discord_user_id
        JOIN user_roles ur ON u.id = ur.user_id
        WHERE ur.role_name = 'International Student'
        """
    ).fetchone()[0]

    # Unique talkers (international students who sent at least 1 message)
    unique_talkers = con.execute(
        """
        SELECT COUNT(DISTINCT ml.discord_user_id)
        FROM message_logs ml
        JOIN users u ON ml.discord_user_id = u.discord_user_id
        JOIN user_roles ur ON u.id = ur.user_id
        WHERE ur.role_name = 'International Student'
        """
    ).fetchone()[0]

    # Total messages in server (all users)
    total_all_msgs = con.execute("SELECT COUNT(*) FROM message_logs").fetchone()[0]

    # Total unique talkers who are in the users table (verified members only)
    total_unique_talkers = con.execute(
        """
        SELECT COUNT(DISTINCT ml.discord_user_id)
        FROM message_logs ml
        JOIN users u ON ml.discord_user_id = u.discord_user_id
        WHERE u.verified = 1
        """
    ).fetchone()[0]

    # Total verified members this year
    total_verified = con.execute(
        "SELECT COUNT(*) FROM users WHERE verified = 1"
    ).fetchone()[0]

    con.close()
    return {
        "total_intl_role_holders": total_intl,
        "total_msgs_by_intl": total_msgs,
        "unique_talkers_intl": unique_talkers,
        "total_all_msgs": total_all_msgs,
        "total_unique_talkers_all": total_unique_talkers,
        "total_verified_members": total_verified,
    }


# ---------------------------------------------------------------------------
# CSV writers
# ---------------------------------------------------------------------------

def write_csv(path: Path, profiles: list[dict], extra_fields: list[str] = []) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["asurite", "country", "state", "is_international", "has_opportunity", "error"] + extra_fields
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(profiles)
    logger.info("Wrote %d rows → %s", len(profiles), path)


# ---------------------------------------------------------------------------
# Report printer
# ---------------------------------------------------------------------------

def print_report(
    label: str,
    profiles: list[dict],
    msg_stats: dict[str, Any] | None = None,
    forkman_verified_total: int = 0,
) -> None:
    errors = [p for p in profiles if p.get("error")]
    ok = [p for p in profiles if not p.get("error")]
    intl = [p for p in ok if p.get("is_international")]
    no_opp = [p for p in ok if not p.get("has_opportunity")]

    country_counter: Counter = Counter(p["country"] for p in intl)
    top_countries = country_counter.most_common(15)

    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")

    total_members = forkman_verified_total if forkman_verified_total else len(ok)
    print(f"  Verified members:          {total_members:>6,}")
    print(f"  Salesforce lookups:        {len(profiles):>6,}")
    print(f"  Successful lookups:        {len(ok):>6,}")
    print(f"  International students:    {len(intl):>6,}  ({len(intl)/total_members*100:.1f}% of verified)")
    print(f"  No opportunity found:      {len(no_opp):>6,}")
    print(f"  Lookup errors:             {len(errors):>6,}")

    if msg_stats:
        s = msg_stats
        intl_pct_msgs = s['total_msgs_by_intl'] / s['total_all_msgs'] * 100 if s['total_all_msgs'] else 0
        intl_pct_talkers = s['unique_talkers_intl'] / s['total_unique_talkers_all'] * 100 if s['total_unique_talkers_all'] else 0
        talk_rate = s['unique_talkers_intl'] / s['total_intl_role_holders'] * 100 if s['total_intl_role_holders'] else 0
        overall_talk_rate = s['total_unique_talkers_all'] / s['total_verified_members'] * 100 if s['total_verified_members'] else 0

        print(f"\n  --- Message Stats ---")
        print(f"  Total server messages:     {s['total_all_msgs']:>8,}")
        print(f"  Messages by intl students: {s['total_msgs_by_intl']:>8,}  ({intl_pct_msgs:.1f}% of all messages)")
        print(f"  Server unique talkers:     {s['total_unique_talkers_all']:>8,}  ({overall_talk_rate:.1f}% talk rate)")
        print(f"  Intl unique talkers:       {s['unique_talkers_intl']:>8,}  ({intl_pct_talkers:.1f}% of server talkers)")
        print(f"  Intl talk rate:            {talk_rate:>7.1f}%  (vs {overall_talk_rate:.1f}% overall)")
        deficit = talk_rate - overall_talk_rate  # negative = intl behind overall
        print(f"  Talk rate deficit:         {deficit:>+7.1f}pp  (intl vs overall, negative = underperforming)")
    else:
        print(f"\n  [!] No message data available for this cohort (forkman.db has no message_logs)")

    print(f"\n  --- Top Countries (International) ---")
    for country, count in top_countries:
        pct = count / len(intl) * 100 if intl else 0
        print(f"  {country:<35} {count:>4}  ({pct:.1f}%)")

    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="International Student YoY Stats")
    parser.add_argument("--concurrency", type=int, default=10, help="Salesforce concurrent requests")
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit Salesforce lookups per cohort (0 = all, useful for testing)",
    )
    parser.add_argument(
        "--skip-salesforce",
        action="store_true",
        help="Skip Salesforce API calls; only print DB-level stats (forklift only)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(PROJECT_ROOT / "data"),
        help="Directory for CSV output",
    )
    return parser.parse_args()


async def main() -> None:
    load_env(ENV_PATH)
    args = parse_args()
    out_dir = Path(args.output_dir)

    # --- Forklift DB stats (no Salesforce needed) ---
    logger.info("Querying forklift.db for message stats...")
    msg_stats = get_forklift_message_stats()

    if args.skip_salesforce:
        print("\n=== Forklift DB Stats (no Salesforce) ===")
        s = msg_stats
        intl_pct_msgs = s['total_msgs_by_intl'] / s['total_all_msgs'] * 100 if s['total_all_msgs'] else 0
        intl_pct_talkers = s['unique_talkers_intl'] / s['total_unique_talkers_all'] * 100 if s['total_unique_talkers_all'] else 0
        talk_rate = s['unique_talkers_intl'] / s['total_intl_role_holders'] * 100 if s['total_intl_role_holders'] else 0
        overall_talk_rate = s['total_unique_talkers_all'] / s['total_verified_members'] * 100 if s['total_verified_members'] else 0
        print(f"  Verified members:          {s['total_verified_members']:>8,}")
        print(f"  International role holders:{s['total_intl_role_holders']:>8,}")
        print(f"  Total server messages:     {s['total_all_msgs']:>8,}")
        print(f"  Messages by intl students: {s['total_msgs_by_intl']:>8,}  ({intl_pct_msgs:.1f}%)")
        print(f"  Server unique talkers:     {s['total_unique_talkers_all']:>8,}  ({overall_talk_rate:.1f}% talk rate)")
        print(f"  Intl unique talkers:       {s['unique_talkers_intl']:>8,}  ({intl_pct_talkers:.1f}% of talkers)")
        print(f"  Intl talk rate:            {talk_rate:>7.1f}%")
        print(f"  Talk rate deficit:         {talk_rate - overall_talk_rate:>+7.1f}pp vs overall")
        print("\nNOTE: Run without --skip-salesforce for country breakdown and YoY comparison.")
        return

    # --- Last year: forkman.db ---
    logger.info("Loading forkman.db verified ASURITEs...")
    forkman_rows = get_forkman_verified_asuries()
    forkman_asuries = [r[0] for r in forkman_rows]
    forkman_verified_total = len(forkman_asuries)
    logger.info("forkman.db verified ASU emails: %d", forkman_verified_total)

    if args.limit:
        forkman_asuries = forkman_asuries[: args.limit]
        logger.info("Limited to %d forkman lookups", len(forkman_asuries))

    logger.info("Fetching Salesforce profiles for last year cohort...")
    forkman_profiles = await bulk_fetch_profiles(forkman_asuries, concurrency=args.concurrency)

    write_csv(out_dir / "intl_stats_lastyear.csv", forkman_profiles)
    print_report(
        "LAST YEAR (forkman.db — AY 2024-25)",
        forkman_profiles,
        msg_stats=None,
        forkman_verified_total=forkman_verified_total,
    )

    # --- This year: forklift.db ---
    logger.info("Loading forklift.db verified ASURITEs...")
    forklift_rows = get_forklift_asuries()
    forklift_asuries = [r[0] for r in forklift_rows]
    logger.info("forklift.db verified users: %d", len(forklift_asuries))

    if args.limit:
        forklift_asuries = forklift_asuries[: args.limit]
        logger.info("Limited to %d forklift lookups", len(forklift_asuries))

    logger.info("Fetching Salesforce profiles for this year cohort...")
    forklift_profiles = await bulk_fetch_profiles(forklift_asuries, concurrency=args.concurrency)

    write_csv(out_dir / "intl_stats_thisyear.csv", forklift_profiles)
    print_report(
        "THIS YEAR (forklift.db — AY 2025-26)",
        forklift_profiles,
        msg_stats=msg_stats,
    )

    # --- YoY summary ---
    ly_intl = [p for p in forkman_profiles if not p.get("error") and p.get("is_international")]
    ty_intl = [p for p in forklift_profiles if not p.get("error") and p.get("is_international")]

    print(f"\n{'='*60}")
    print("  YEAR-OVER-YEAR SUMMARY")
    print(f"{'='*60}")
    print(f"  {'Metric':<40} {'Last Year':>10}  {'This Year':>10}")
    print(f"  {'-'*62}")
    print(f"  {'Verified members':<40} {forkman_verified_total:>10,}  {msg_stats['total_verified_members']:>10,}")
    print(f"  {'International students (Salesforce)':<40} {len(ly_intl):>10,}  {len(ty_intl):>10,}")
    pct_ly = len(ly_intl) / forkman_verified_total * 100 if forkman_verified_total else 0
    pct_ty = len(ty_intl) / msg_stats['total_verified_members'] * 100 if msg_stats['total_verified_members'] else 0
    print(f"  {'  % of verified members':<40} {pct_ly:>9.1f}%  {pct_ty:>9.1f}%")
    print(f"  {'Messages by intl students':<40} {'N/A (no data)':>10}  {msg_stats['total_msgs_by_intl']:>10,}")
    print(f"  {'Intl unique talkers':<40} {'N/A (no data)':>10}  {msg_stats['unique_talkers_intl']:>10,}")
    talk_rate = msg_stats['unique_talkers_intl'] / msg_stats['total_intl_role_holders'] * 100 if msg_stats['total_intl_role_holders'] else 0
    overall_rate = msg_stats['total_unique_talkers_all'] / msg_stats['total_verified_members'] * 100 if msg_stats['total_verified_members'] else 0
    print(f"  {'Intl talk rate':<40} {'N/A':>10}  {talk_rate:>9.1f}%")
    print(f"  {'Overall talk rate':<40} {'N/A':>10}  {overall_rate:>9.1f}%")
    print(f"  {'Talk rate deficit (intl vs overall)':<40} {'N/A':>10}  {talk_rate - overall_rate:>+9.1f}pp")
    print()
    print("  NOTE: Last-year message stats unavailable — forkman.db has no message_logs table.")
    print()


if __name__ == "__main__":
    asyncio.run(main())

"""
International Student Cohort — Country Breakdown
Nov 15 2025 – Feb 28 2026 verification window

Pulls all users with 'International Student' role who verified in the window,
looks up their country via Salesforce, and prints a country breakdown.

Usage:
    python scripts/intl_cohort_countries.py [--concurrency N] [--limit N]
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import os
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import aiohttp

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

ENV_PATH = PROJECT_ROOT / ".env"
FORKLIFT_DB = PROJECT_ROOT / "forklift.db"

BASE = "https://esb.asu.edu"
CONTACT_URL = f"{BASE}/api/v1/asu-sf-contact/contact"
OPP_URL = f"{BASE}/api/v1/asu-sf-opportunity/opportunity"

WINDOW_START = "2000-01-01"
WINDOW_END = "2026-03-31 23:59:59"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Env / auth
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
# DB query
# ---------------------------------------------------------------------------

def get_cohort_asuries() -> list[tuple[str, str]]:
    """Return [(asurite, discord_user_id), ...] for the Nov 15–Feb 28 intl cohort."""
    con = sqlite3.connect(FORKLIFT_DB)
    rows = con.execute(
        """
        SELECT DISTINCT u.asurite_id, u.discord_user_id
        FROM users u
        JOIN user_roles ur ON u.id = ur.user_id
        WHERE ur.role_name = 'International Student'
          AND u.verified = 1
          AND u.verified_at BETWEEN ? AND ?
        """,
        (WINDOW_START, WINDOW_END),
    ).fetchall()
    con.close()
    return rows


# ---------------------------------------------------------------------------
# Salesforce fetch — filter to term code 2267 via opportunity lookup
# ---------------------------------------------------------------------------

TARGET_TERM = "2267"


async def fetch_country(
    session: aiohttp.ClientSession,
    asurite: str,
    header: str,
    sem: asyncio.Semaphore,
) -> dict[str, Any]:
    async with sem:
        try:
            # 1. Contact lookup
            async with session.get(
                f"{CONTACT_URL}?asurite={asurite}",
                headers={"Authorization": header},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    return {"asurite": asurite, "country": "Unknown", "term_match": False, "error": f"HTTP {resp.status}"}
                data = await resp.json()

            contacts = data.get("contact") or []
            if not contacts:
                return {"asurite": asurite, "country": "Unknown", "term_match": False, "error": "no contact"}

            contact = contacts[0]
            contact_id = contact.get("id")
            country = (contact.get("country") or "Unknown").strip() or "Unknown"

            # 2. Opportunity lookup — check for term code 2267
            has_term = False
            for career in ("Undergraduate", "Graduate"):
                async with session.get(
                    f"{OPP_URL}?contactId={contact_id}&career={career}",
                    headers={"Authorization": header},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as opp_resp:
                    if opp_resp.status != 200:
                        continue
                    opps = await opp_resp.json()
                    if not isinstance(opps, list):
                        continue
                    for opp in opps:
                        stage = (opp.get("stageName") or "").strip().lower()
                        term = str(opp.get("termCode") or "")
                        if term == TARGET_TERM and stage in {"enrolled", "admitted"}:
                            has_term = True
                            break
                if has_term:
                    break

            return {"asurite": asurite, "country": country, "term_match": has_term, "error": None}

        except Exception as exc:
            return {"asurite": asurite, "country": "Unknown", "term_match": False, "error": str(exc)}


async def bulk_fetch(asuries: list[str], concurrency: int) -> list[dict[str, Any]]:
    header = auth_header()
    sem = asyncio.Semaphore(concurrency)
    connector = aiohttp.TCPConnector(limit=concurrency)
    results: list[dict] = []

    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [fetch_country(session, a, header, sem) for a in asuries]
        total = len(tasks)
        for i, coro in enumerate(asyncio.as_completed(tasks), 1):
            results.append(await coro)
            if i % 50 == 0 or i == total:
                logger.info("Salesforce lookups: %d / %d", i, total)

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Intl cohort country breakdown")
    p.add_argument("--concurrency", type=int, default=10)
    p.add_argument("--limit", type=int, default=0, help="Limit lookups (0 = all)")
    p.add_argument("--output-dir", type=str, default=str(PROJECT_ROOT / "data"))
    return p.parse_args()


async def main() -> None:
    load_env(ENV_PATH)
    args = parse_args()
    out_dir = Path(args.output_dir)

    rows = get_cohort_asuries()
    logger.info("Cohort size (all time – Mar 31 2026): %d", len(rows))

    asuries = [r[0] for r in rows]
    if args.limit:
        asuries = asuries[: args.limit]
        logger.info("Limited to %d", len(asuries))

    profiles = await bulk_fetch(asuries, args.concurrency)

    # Write CSV
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "intl_cohort_term2267_countries.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["asurite", "country", "term_match", "error"])
        writer.writeheader()
        writer.writerows(profiles)
    logger.info("Wrote CSV → %s", csv_path)

    # Country breakdown — only users with a matching term 2267 opportunity
    ok = [p for p in profiles if not p["error"]]
    errors = [p for p in profiles if p["error"]]
    matched = [p for p in ok if p["term_match"]]
    country_counts = Counter(p["country"] for p in matched)

    print(f"\n{'='*55}")
    print("  International Student Cohort — Country Breakdown")
    print("  Term code filter: 2267 (admitted/enrolled)")
    print(f"{'='*55}")
    print(f"  Total in cohort:      {len(profiles):>4}")
    print(f"  Successful lookups:   {len(ok):>4}")
    print(f"  Term 2267 matches:    {len(matched):>4}")
    print(f"  Lookup errors:        {len(errors):>4}")
    print(f"\n  {'Country':<35} {'Count':>5}  {'%':>6}")
    print(f"  {'-'*50}")
    others = 0
    others_count = 0
    for country, count in country_counts.most_common():
        pct = count / len(matched) * 100 if matched else 0
        if pct < 2.0:
            others += count
            others_count += 1
        else:
            print(f"  {country:<35} {count:>5}  {pct:>5.1f}%")
    if others:
        pct = others / len(matched) * 100 if matched else 0
        print(f"  {'Others':<35} {others:>5}  {pct:>5.1f}%  ({others_count} countries)")
    print()


if __name__ == "__main__":
    asyncio.run(main())

"""Running-headcount math behind /api/admin/membership/chart."""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine, or_
from sqlalchemy.orm import sessionmaker

from routes.admin import _chart_data, _membership_query, _running_total
from utils.database import Base, DiscordMember, User, UserRole


def series(pairs):
    return [{"date": d, "count": c} for d, c in pairs]


def test_carries_baseline_forward():
    """A quiet day holds the previous headcount — the line must not drop to zero."""
    out = _running_total(series([("2026-01-01", 0), ("2026-01-02", 0)]), [], baseline=500)
    assert [d["count"] for d in out] == [500, 500]


def test_joins_and_leaves_net_out():
    joins = series([("2026-01-01", 10), ("2026-01-02", 3), ("2026-01-03", 0)])
    leaves = series([("2026-01-01", 0), ("2026-01-02", 5), ("2026-01-03", 1)])
    out = _running_total(joins, leaves, baseline=100)

    assert [d["count"] for d in out] == [110, 108, 107]
    # Per-day components are reported alongside the running total.
    assert out[1] == {"date": "2026-01-02", "count": 108, "joins": 3, "leaves": 5}


def test_leaves_on_days_with_no_joins_still_subtract():
    """Leave dates absent from the joins series must not be silently dropped."""
    out = _running_total(
        series([("2026-01-01", 0), ("2026-01-02", 0)]),
        series([("2026-01-02", 4)]),
        baseline=10,
    )
    assert [d["count"] for d in out] == [10, 6]


def test_empty_range_is_empty():
    assert _running_total([], [], baseline=42) == []


# ── Headcount comes from DiscordMember, not User ──────────────────────────────
# User.joined_at is only set for members who verified, so counting there
# undercounts the guild badly. These guard the source table and the role join.

@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    def member(discord_id, joined, left=None, roles=()):
        session.add(DiscordMember(
            discord_user_id=discord_id, joined_at=datetime.fromisoformat(joined),
            left_at=datetime.fromisoformat(left) if left else None,
        ))
        if roles:
            u = User(asurite_id=f"a{discord_id}", email=f"{discord_id}@asu.edu",
                     discord_user_id=discord_id)
            session.add(u)
            session.flush()
            for r in roles:
                session.add(UserRole(user_id=u.id, role_name=r, role_discord_id=1))

    # Two unverified members carry no roles at all — they must still be counted.
    member("1", "2026-01-05")
    member("2", "2026-01-05")
    member("3", "2026-02-10", roles=["International Student", "First Year"])
    member("4", "2026-02-10", roles=["International Student", "Upperclassmen"])
    member("5", "2026-01-05", "2026-02-12", roles=["International Student", "First Year"])
    session.commit()
    return session


def headcount(session, from_dt, to_dt, roles=None, exclude_roles=None):
    def q(col, f, t):
        return _membership_query(session, col, f, t, roles, exclude_roles)

    baseline = (
        q(DiscordMember.joined_at, None, None)
        .filter(DiscordMember.joined_at < from_dt)
        .filter(or_(DiscordMember.left_at.is_(None), DiscordMember.left_at >= from_dt))
        .count()
    )
    joins = [d for (d,) in q(DiscordMember.joined_at, from_dt, to_dt).all()]
    leaves = [d for (d,) in q(DiscordMember.left_at, from_dt, to_dt).all()]
    return _running_total(_chart_data(joins, from_dt, to_dt),
                          _chart_data(leaves, from_dt, to_dt), baseline)


RANGE = (datetime(2026, 2, 1), datetime(2026, 2, 28, 23, 59, 59))


def test_counts_unverified_members(db):
    """Three members were present on Feb 1; two of them never verified."""
    out = headcount(db, *RANGE)
    assert out[0]["count"] == 3
    assert out[-1]["count"] == 4  # +2 joined Feb 10, -1 left Feb 12


def test_role_filter_ands_and_excludes(db):
    intl = headcount(db, *RANGE, roles=["International Student"])
    assert intl[-1]["count"] == 2          # 3 and 4; 5 left

    both = headcount(db, *RANGE, roles=["International Student", "First Year"])
    assert both[-1]["count"] == 1          # only 3

    excl = headcount(db, *RANGE, roles=["International Student"],
                     exclude_roles=["First Year"])
    assert excl[-1]["count"] == 1          # only 4

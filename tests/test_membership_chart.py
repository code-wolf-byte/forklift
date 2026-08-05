"""Running-headcount math behind /api/admin/membership/chart."""

from __future__ import annotations

from routes.admin import _running_total


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

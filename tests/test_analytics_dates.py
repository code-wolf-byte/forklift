"""Date-filter boundaries shared by the admin analytics endpoints.

Timestamps are stored as naive UTC while admins pick dates on an Arizona
calendar, so _parse_az_date is the single place that has to get the day
boundary right — every date-filtered admin endpoint routes through it.
"""

from datetime import datetime

from routes.admin import _parse_az_date


def test_az_day_maps_to_utc_window():
    # Arizona is UTC-7 year round (no DST), so a calendar day is 07:00 -> 07:00 UTC.
    assert _parse_az_date("2026-06-01") == datetime(2026, 6, 1, 7, 0, 0)
    end = _parse_az_date("2026-06-01", end_of_day=True)
    assert end == datetime(2026, 6, 2, 6, 59, 59, 999999)


def test_last_instant_of_the_az_day_is_inside_the_window():
    start = _parse_az_date("2026-06-01")
    end = _parse_az_date("2026-06-01", end_of_day=True)
    # 23:59:59.5 AZ on the selected day — sub-second rows must not fall out.
    assert start <= datetime(2026, 6, 2, 6, 59, 59, 500000) <= end
    # 00:00 AZ the next morning must fall outside.
    assert not (start <= datetime(2026, 6, 2, 7, 0, 0) <= end)


def test_window_is_contiguous_across_consecutive_days():
    # No gap and no overlap between one day's end and the next day's start.
    end = _parse_az_date("2026-06-01", end_of_day=True)
    next_start = _parse_az_date("2026-06-02")
    assert next_start - end == datetime(1, 1, 1, 0, 0, 1) - datetime(1, 1, 1, 0, 0, 0, 999999)


def test_blank_and_garbage_dates_disable_the_filter():
    assert _parse_az_date(None) is None
    assert _parse_az_date("") is None
    assert _parse_az_date("not-a-date") is None

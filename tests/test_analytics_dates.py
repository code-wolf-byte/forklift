"""Date-filter boundaries for the admin analytics endpoint."""

from datetime import datetime

from routes.admin import _parse_az_date


def test_az_day_maps_to_utc_window():
    # Arizona is UTC-7 year round (no DST), so a calendar day is 07:00 -> 07:00 UTC.
    assert _parse_az_date("2026-06-01") == datetime(2026, 6, 1, 7, 0, 0)
    end = _parse_az_date("2026-06-01", end_of_day=True)
    assert end == datetime(2026, 6, 2, 6, 59, 59, 999999)
    # The last instant of the AZ day must fall inside the window, sub-second included.
    assert _parse_az_date("2026-06-01") <= datetime(2026, 6, 2, 6, 59, 59, 500000) <= end


def test_blank_and_garbage_dates_disable_the_filter():
    assert _parse_az_date(None) is None
    assert _parse_az_date("") is None
    assert _parse_az_date("not-a-date") is None

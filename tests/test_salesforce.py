"""Tests for asu_discord/salesforce.py — mocked HTTP."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from asu_discord.models import StudentProfile
from asu_discord.salesforce import (
    _parse_bool,
    _deposit_paid_from_opportunity,
    _eligible_opportunities,
    _select_opportunity,
    get_student_profile,
)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

class TestParseBool:
    @pytest.mark.parametrize("value,expected", [
        (True, True),
        (False, False),
        ("true", True),
        ("True", True),
        ("TRUE", True),
        ("yes", True),
        ("y", True),
        ("1", True),
        ("t", True),
        ("false", False),
        ("no", False),
        ("0", False),
        ("", False),
        (None, False),
        (0, False),
        (1, False),
    ])
    def test_values(self, value, expected):
        assert _parse_bool(value) == expected


class TestDepositPaidFromOpportunity:
    def test_deposit_paid_true(self):
        opp = {"enrollmentDepositPaid": True}
        assert _deposit_paid_from_opportunity(opp) is True

    def test_deposit_status_paid(self):
        opp = {"enrollmentDepositPaid": False, "enrollmentDepositStatus": "Paid"}
        assert _deposit_paid_from_opportunity(opp) is True

    def test_deposit_status_case_insensitive(self):
        opp = {"enrollmentDepositStatus": "PAID"}
        assert _deposit_paid_from_opportunity(opp) is True

    def test_not_paid(self):
        opp = {"enrollmentDepositPaid": False, "enrollmentDepositStatus": "Unpaid"}
        assert _deposit_paid_from_opportunity(opp) is False

    def test_empty_opp(self):
        assert _deposit_paid_from_opportunity({}) is False


class TestEligibleOpportunities:
    def test_filters_enrolled_and_admitted(self):
        opps = [
            {"stageName": "Enrolled"},
            {"stageName": "Admitted"},
            {"stageName": "Prospect"},
            {"stageName": ""},
        ]
        result = _eligible_opportunities(opps)
        assert len(result) == 2

    def test_non_dict_excluded(self):
        opps = [{"stageName": "Enrolled"}, "invalid", None]
        result = _eligible_opportunities(opps)
        assert len(result) == 1

    def test_empty_input(self):
        assert _eligible_opportunities([]) == []


class TestSelectOpportunity:
    def test_target_term_selected_first(self):
        opps = [
            {"stageName": "Enrolled", "termCode": "9999"},
            {"stageName": "Enrolled", "termCode": "2267"},
        ]
        opp, is_current = _select_opportunity(opps)
        assert opp["termCode"] == "2267"
        assert is_current is False

    def test_non_target_term_is_current(self):
        opps = [{"stageName": "Enrolled", "termCode": "9999"}]
        opp, is_current = _select_opportunity(opps)
        assert opp is not None
        assert is_current is True

    def test_no_eligible_returns_none(self):
        opps = [{"stageName": "Prospect", "termCode": "2267"}]
        opp, is_current = _select_opportunity(opps)
        assert opp is None
        assert is_current is None

    def test_empty_returns_none(self):
        opp, is_current = _select_opportunity([])
        assert opp is None
        assert is_current is None


# ---------------------------------------------------------------------------
# get_student_profile — mocked HTTP
# ---------------------------------------------------------------------------

CONTACT_RESPONSE = {
    "contact": [
        {
            "id": "contact-001",
            "firstname": "Jane",
            "lastname": "Doe",
            "email": "jdoe@asu.edu",
            "state": "Arizona",
            "country": "USA",
        }
    ]
}

OPP_RESPONSE = [
    {
        "stageName": "Enrolled",
        "termCode": "2267",
        "career": "Undergraduate",
        "type": "First Time Freshman",
        "collegeName": "Barrett The Honors College",
        "locationName": "Tempe",
        "createdDate": "2024-01-01T00:00:00Z",
        "internationalStudent": False,
        "firstGeneration": False,
        "enrollmentDepositPaid": True,
    }
]


def _make_response(json_data, status_code=200):
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp


@pytest.fixture(autouse=True)
def patch_credentials(monkeypatch):
    monkeypatch.setenv("SALESFORCE_API_CLIENT_ID", "test_client")
    monkeypatch.setenv("SALESFORCE_API_CLIENT_SECRET", "test_secret")
    import asu_discord.salesforce as sf
    monkeypatch.setattr(sf, "CLIENT_ID", "test_client")
    monkeypatch.setattr(sf, "CLIENT_SECRET", "test_secret")


class TestGetStudentProfile:
    def test_returns_none_when_credentials_missing(self, monkeypatch):
        import asu_discord.salesforce as sf
        monkeypatch.setattr(sf, "CLIENT_ID", None)
        monkeypatch.setattr(sf, "CLIENT_SECRET", None)
        assert get_student_profile("jdoe") is None

    def test_returns_none_on_request_exception(self):
        with patch("asu_discord.salesforce.requests.get", side_effect=requests.RequestException("timeout")):
            assert get_student_profile("jdoe") is None

    def test_returns_none_when_no_contact(self):
        with patch("asu_discord.salesforce.requests.get") as mock_get:
            mock_get.return_value = _make_response({"contact": []})
            assert get_student_profile("jdoe") is None

    def test_returns_none_when_no_opportunities(self):
        def side_effect(url, **kwargs):
            if "contact" in url:
                return _make_response(CONTACT_RESPONSE)
            return _make_response([], 200)

        with patch("asu_discord.salesforce.requests.get", side_effect=side_effect):
            assert get_student_profile("jdoe") is None

    def _mock_get(self, url, **kwargs):
        """Route by path segment: opportunity URL vs contact URL."""
        if "opportunity" in url:
            return _make_response(OPP_RESPONSE)
        return _make_response(CONTACT_RESPONSE)

    def test_returns_student_profile_on_success(self):
        with patch("asu_discord.salesforce.requests.get", side_effect=self._mock_get):
            profile = get_student_profile("jdoe")

        assert isinstance(profile, StudentProfile)
        assert profile.asurite == "jdoe"
        assert profile.name == "Jane Doe"
        assert profile.email == "jdoe@asu.edu"

    def test_profile_has_opportunities(self):
        with patch("asu_discord.salesforce.requests.get", side_effect=self._mock_get):
            profile = get_student_profile("jdoe")

        assert len(profile.opportunities) > 0

    def test_profile_in_state_for_arizona(self):
        with patch("asu_discord.salesforce.requests.get", side_effect=self._mock_get):
            profile = get_student_profile("jdoe")

        assert profile.inState is True
        assert profile.outOfState is False

    def test_profile_deposit_paid(self):
        with patch("asu_discord.salesforce.requests.get", side_effect=self._mock_get):
            profile = get_student_profile("jdoe")

        assert profile.depositPaid is True or profile.enrollmentDepositPaid is True

    def test_opp_request_failure_skipped(self):
        def side_effect(url, **kwargs):
            if "opportunity" in url:
                raise requests.RequestException("opp failure")
            return _make_response(CONTACT_RESPONSE)

        with patch("asu_discord.salesforce.requests.get", side_effect=side_effect):
            result = get_student_profile("jdoe")

        assert result is None

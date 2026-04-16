"""Tests for role-derivation helpers in asu_discord/cogs/verification.py."""

from __future__ import annotations

import pytest

from asu_discord.cogs.verification import (
    TARGET_TERM_CODE,
    _college_role_from_name,
    _campus_role_from_location,
    role_names_from_student_profile,
)
from asu_discord.models import SalesforceOpportunity, StudentProfile
from tests.conftest import make_opportunity, make_student_profile


# ---------------------------------------------------------------------------
# YAML config loading
# ---------------------------------------------------------------------------

class TestTargetTermCode:
    def test_loaded_from_yaml(self):
        assert isinstance(TARGET_TERM_CODE, str)
        assert len(TARGET_TERM_CODE) == 4

    def test_current_value(self):
        assert TARGET_TERM_CODE == "2267"


# ---------------------------------------------------------------------------
# _college_role_from_name
# ---------------------------------------------------------------------------

class TestCollegeRoleFromName:
    @pytest.mark.parametrize("name,expected", [
        ("Ira A. Fulton Schools of Engineering", "Ira A. Fulton Schools of Engineering"),
        ("ira a. fulton schools of engineering", "Ira A. Fulton Schools of Engineering"),
        ("Barrett The Honors College", "Barrett The Honors College"),
        ("barrett honors", "Barrett The Honors College"),
        ("College of Liberal Arts and Sciences", "College of Liberal Arts and Sciences"),
        ("College of Global Futures", "College of Global Futures"),
        ("Edson College of Nursing and Health Innovation", "Edson College of Nursing and Health Innovation"),
        ("Herberger Institute for Design and the Arts", "Herberger Institute for Design and the Arts"),
        ("Thunderbird School of Global Management", "Thunderbird School of Global Management"),
        ("Mary Lou Fulton Teachers College", "Mary Lou Fulton Teachers College"),
        ("New College of Interdisciplinary Arts and Sciences", "New College of Interdisciplinary Arts and Sciences"),
        ("College of Integrative Sciences and Arts", "College of Integrative Sciences and Arts"),
        ("W.P. Carey School of Business", "W.P. Carey School of Business"),
        ("Walter Cronkite School of Journalism and Mass Communication", "Walter Cronkite School of Journalism and Mass Communication"),
        ("Watts College of Public Service and Community Solutions", "Watts College of Public Service and Community Solutions"),
        ("University College", "University College"),
    ])
    def test_known_colleges(self, name, expected):
        assert _college_role_from_name(name) == expected

    def test_case_insensitive(self):
        assert _college_role_from_name("BARRETT THE HONORS COLLEGE") == "Barrett The Honors College"

    def test_none_returns_none(self):
        assert _college_role_from_name(None) is None

    def test_empty_string_returns_none(self):
        assert _college_role_from_name("") is None

    def test_whitespace_returns_none(self):
        assert _college_role_from_name("   ") is None

    def test_unknown_college_returns_none(self):
        assert _college_role_from_name("School of Wizardry") is None

    def test_partial_match_fulton_without_ira(self):
        # "fulton" alone doesn't match Ira A. Fulton (requires "ira a" too)
        result = _college_role_from_name("Fulton Schools of Something")
        assert result != "Ira A. Fulton Schools of Engineering"


# ---------------------------------------------------------------------------
# _campus_role_from_location
# ---------------------------------------------------------------------------

class TestCampusRoleFromLocation:
    @pytest.mark.parametrize("location,expected", [
        ("Tempe", "Tempe"),
        ("tempe", "Tempe"),
        ("TEMPE", "Tempe"),
        ("Downtown Phoenix", "Downtown Phoenix"),
        ("downtown phoenix", "Downtown Phoenix"),
        ("Polytechnic", "Polytechnic"),
        ("Online", "Online"),
        ("West Valley", "West Valley"),
        ("LA Center", "LA Center"),
        ("Los Angeles", "LA Center"),
        ("los angeles", "LA Center"),
    ])
    def test_known_locations(self, location, expected):
        assert _campus_role_from_location(location) == expected

    def test_none_returns_none(self):
        assert _campus_role_from_location(None) is None

    def test_empty_string_returns_none(self):
        assert _campus_role_from_location("") is None

    def test_unknown_location_returns_none(self):
        assert _campus_role_from_location("Moon Campus") is None


# ---------------------------------------------------------------------------
# role_names_from_student_profile
# ---------------------------------------------------------------------------

class TestRoleNamesFromStudentProfile:
    def test_empty_opportunities_returns_empty(self):
        profile = make_student_profile()
        roles = role_names_from_student_profile(profile)
        assert roles == set()

    def test_first_year_role(self):
        opp = make_opportunity(stageName="Enrolled", termCode="2267", career="Undergraduate", type="First Time Freshman")
        profile = make_student_profile(opportunities=[opp])
        roles = role_names_from_student_profile(profile)
        assert "First Year" in roles

    def test_transfer_student_role(self):
        opp = make_opportunity(stageName="Enrolled", termCode="2267", career="Undergraduate", type="Transfer")
        profile = make_student_profile(opportunities=[opp])
        roles = role_names_from_student_profile(profile)
        assert "Transfer Student" in roles

    def test_graduate_student_role(self):
        opp = make_opportunity(stageName="Enrolled", termCode="2267", career="Graduate", type=None)
        profile = make_student_profile(opportunities=[opp])
        roles = role_names_from_student_profile(profile)
        assert "Graduate Student" in roles

    def test_upperclassmen_for_non_target_term(self):
        opp = make_opportunity(stageName="Enrolled", termCode="2261", career="Undergraduate", type="Continuing")
        profile = make_student_profile(opportunities=[opp])
        roles = role_names_from_student_profile(profile)
        assert "Upperclassmen" in roles

    def test_international_student_role(self):
        opp = make_opportunity(stageName="Enrolled", termCode="2267", internationalStudent=True)
        profile = make_student_profile(opportunities=[opp])
        roles = role_names_from_student_profile(profile)
        assert "International Student" in roles

    def test_first_gen_student_role(self):
        opp = make_opportunity(stageName="Enrolled", termCode="2267", firstGeneration=True)
        profile = make_student_profile(opportunities=[opp])
        roles = role_names_from_student_profile(profile)
        assert "First Generation Student" in roles

    def test_commited_role_from_deposit(self):
        opp = make_opportunity(stageName="Enrolled", termCode="2267", enrollmentDepositPaid=True)
        profile = make_student_profile(opportunities=[opp])
        roles = role_names_from_student_profile(profile)
        assert "Commited" in roles

    def test_commited_role_from_deposit_status(self):
        opp = make_opportunity(stageName="Enrolled", termCode="2267", enrollmentDepositStatus="Paid")
        profile = make_student_profile(opportunities=[opp])
        roles = role_names_from_student_profile(profile)
        assert "Commited" in roles

    def test_college_role_from_opportunity(self):
        opp = make_opportunity(stageName="Enrolled", termCode="2267", collegeName="Barrett The Honors College")
        profile = make_student_profile(opportunities=[opp])
        roles = role_names_from_student_profile(profile)
        assert "Barrett The Honors College" in roles

    def test_campus_role_from_opportunity(self):
        opp = make_opportunity(stageName="Enrolled", termCode="2267", locationName="Tempe")
        profile = make_student_profile(opportunities=[opp])
        roles = role_names_from_student_profile(profile)
        assert "Tempe" in roles

    def test_in_state_role(self):
        profile = make_student_profile(inState=True)
        roles = role_names_from_student_profile(profile)
        assert "Arizona Resident" in roles

    def test_out_of_state_role(self):
        profile = make_student_profile(outOfState=True)
        roles = role_names_from_student_profile(profile)
        assert "Out of State" in roles

    def test_international_from_profile_field(self):
        profile = make_student_profile(international=True)
        roles = role_names_from_student_profile(profile)
        assert "International Student" in roles

    def test_unenrolled_opportunity_excluded(self):
        opp = make_opportunity(stageName="Prospect", termCode="2267")
        profile = make_student_profile(opportunities=[opp])
        roles = role_names_from_student_profile(profile)
        assert "First Year" not in roles
        assert "Graduate Student" not in roles

    def test_admitted_opportunity_included(self):
        opp = make_opportunity(stageName="Admitted", termCode="2267", career="Graduate")
        profile = make_student_profile(opportunities=[opp])
        roles = role_names_from_student_profile(profile)
        assert "Graduate Student" in roles

    def test_profile_level_college_fallback(self):
        from asu_discord.roles import ROLE_ID_MAP
        college = "W.P. Carey School of Business"
        profile = make_student_profile(college=college)
        roles = role_names_from_student_profile(profile)
        assert college in roles

    def test_multiple_roles_combined(self):
        opp = make_opportunity(
            stageName="Enrolled",
            termCode="2267",
            career="Undergraduate",
            type="First Time Freshman",
            collegeName="Barrett The Honors College",
            locationName="Tempe",
            firstGeneration=True,
        )
        profile = make_student_profile(opportunities=[opp], inState=True)
        roles = role_names_from_student_profile(profile)
        assert "First Year" in roles
        assert "Barrett The Honors College" in roles
        assert "Tempe" in roles
        assert "First Generation Student" in roles
        assert "Arizona Resident" in roles

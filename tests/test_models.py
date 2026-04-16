"""Tests for Pydantic models in asu_discord/models.py."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from asu_discord.models import (
    DiscordProfile,
    DiscordTokenData,
    SalesforceOpportunity,
    StudentProfile,
)


class TestDiscordProfile:
    def test_minimal_valid(self):
        p = DiscordProfile(id="123", username="alice")
        assert p.id == "123"
        assert p.username == "alice"
        assert p.global_name is None
        assert p.avatar is None
        assert p.discriminator is None

    def test_full_fields(self):
        p = DiscordProfile(
            id="456",
            username="bob",
            global_name="Bob Smith",
            avatar="abc123",
            discriminator="0001",
        )
        assert p.global_name == "Bob Smith"
        assert p.avatar == "abc123"

    def test_extra_fields_allowed(self):
        p = DiscordProfile(id="1", username="u", flags=64)
        assert p.model_dump()["flags"] == 64

    def test_missing_required_raises(self):
        with pytest.raises(ValidationError):
            DiscordProfile(username="no_id")

    def test_model_validate_from_dict(self):
        data = {"id": "7", "username": "carol", "global_name": "Carol"}
        p = DiscordProfile.model_validate(data)
        assert p.id == "7"

    def test_model_dump_round_trip(self):
        data = {"id": "99", "username": "dave", "avatar": "xyz"}
        p = DiscordProfile.model_validate(data)
        assert p.model_dump()["username"] == "dave"


class TestDiscordTokenData:
    def test_minimal_valid(self):
        t = DiscordTokenData(access_token="tok123")
        assert t.access_token == "tok123"
        assert t.token_type == "Bearer"
        assert t.scope == ""
        assert t.expires_in is None

    def test_full_fields(self):
        t = DiscordTokenData(
            access_token="abc",
            token_type="Bearer",
            scope="identify",
            expires_in=604800,
        )
        assert t.expires_in == 604800
        assert t.scope == "identify"

    def test_extra_fields_allowed(self):
        t = DiscordTokenData(access_token="x", refresh_token="y")
        assert t.model_dump()["refresh_token"] == "y"

    def test_missing_access_token_raises(self):
        with pytest.raises(ValidationError):
            DiscordTokenData(token_type="Bearer")


class TestSalesforceOpportunity:
    def test_all_none_defaults(self):
        opp = SalesforceOpportunity()
        assert opp.stageName is None
        assert opp.termCode is None
        assert opp.career is None

    def test_populate_fields(self):
        opp = SalesforceOpportunity(stageName="Enrolled", termCode="2267", career="Undergraduate")
        assert opp.stageName == "Enrolled"
        assert opp.termCode == "2267"

    def test_extra_fields_allowed(self):
        opp = SalesforceOpportunity(unknownField="value")
        assert opp.model_dump()["unknownField"] == "value"

    def test_model_validate(self):
        data = {"stageName": "Admitted", "collegeName": "Barrett The Honors College"}
        opp = SalesforceOpportunity.model_validate(data)
        assert opp.collegeName == "Barrett The Honors College"


class TestStudentProfile:
    def test_required_asurite(self):
        with pytest.raises(ValidationError):
            StudentProfile()

    def test_minimal_valid(self):
        p = StudentProfile(asurite="jdoe123")
        assert p.asurite == "jdoe123"
        assert p.opportunities == []
        assert p.inState is False
        assert p.outOfState is False
        assert p.international is False

    def test_opportunities_list(self):
        opp = SalesforceOpportunity(stageName="Enrolled", termCode="2267")
        p = StudentProfile(asurite="x", opportunities=[opp])
        assert len(p.opportunities) == 1
        assert p.opportunities[0].termCode == "2267"

    def test_bool_fields(self):
        p = StudentProfile(asurite="x", inState=True, firstYear=True, depositPaid=True)
        assert p.inState is True
        assert p.firstYear is True
        assert p.depositPaid is True

    def test_extra_fields_allowed(self):
        p = StudentProfile(asurite="x", customField="yes")
        assert p.model_dump()["customField"] == "yes"

    def test_model_validate_nested_opportunity(self):
        data = {
            "asurite": "jsmith",
            "opportunities": [{"stageName": "Enrolled", "career": "Graduate"}],
        }
        p = StudentProfile.model_validate(data)
        assert p.opportunities[0].career == "Graduate"

    def test_campus_default(self):
        p = StudentProfile(asurite="x")
        assert p.campus == "N/A"
        assert p.locationName == "N/A"

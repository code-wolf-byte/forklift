"""Tests for the admin-editable app settings layer."""

from __future__ import annotations

import pytest

from asu_discord.roles import DEFAULT_ROLE_ID_MAP
from utils import app_settings
from utils.app_settings import SettingsValidationError
from utils.database import AppSetting, init_db, session_scope

VALID_ID = "1187144343400751234"


@pytest.fixture
def clean_settings():
    """Run against an empty app_settings table, and leave it empty afterwards."""
    init_db()
    with session_scope() as db_session:
        db_session.query(AppSetting).delete()
    app_settings.clear_cache()
    yield
    with session_scope() as db_session:
        db_session.query(AppSetting).delete()
    app_settings.clear_cache()


class TestDefaults:
    def test_empty_table_returns_code_defaults(self, clean_settings):
        for key in app_settings.KEYS:
            assert app_settings.get(key) == app_settings.defaults()[key]

    def test_role_map_default_matches_source(self, clean_settings):
        assert app_settings.get("role_id_map") == DEFAULT_ROLE_ID_MAP

    def test_unknown_key_raises(self):
        with pytest.raises(KeyError):
            app_settings.get("not_a_setting")


class TestOverrides:
    def test_override_wins_over_default(self, clean_settings):
        app_settings.set_many({"gold_guide_role_id": VALID_ID}, updated_by="tester")
        assert app_settings.get("gold_guide_role_id") == VALID_ID

    def test_none_resets_to_default(self, clean_settings):
        default = app_settings.defaults()["gold_guide_role_id"]
        app_settings.set_many({"gold_guide_role_id": VALID_ID}, updated_by="tester")
        app_settings.set_many({"gold_guide_role_id": None}, updated_by="tester")
        assert app_settings.get("gold_guide_role_id") == default

    def test_partial_role_map_override(self, clean_settings):
        name = next(iter(DEFAULT_ROLE_ID_MAP))
        app_settings.set_many({"role_id_map": {name: VALID_ID}}, updated_by="tester")
        assert app_settings.get("role_id_map") == {name: int(VALID_ID)}

    def test_get_all_reports_override_and_audit(self, clean_settings):
        app_settings.set_many({"target_term_code": "2271"}, updated_by="tester")
        row = app_settings.get_all()["target_term_code"]
        assert row["value"] == "2271"
        assert row["is_overridden"] is True
        assert row["updated_by"] == "tester"
        assert app_settings.get_all()["gold_guide_role_id"]["is_overridden"] is False


class TestValidation:
    @pytest.mark.parametrize("bad", ["123", "abc", "", "12345678901234567890123"])
    def test_rejects_bad_snowflake(self, bad):
        with pytest.raises(SettingsValidationError):
            app_settings.validate("gold_guide_role_id", bad)

    @pytest.mark.parametrize("bad", ["226", "22671", "abcd"])
    def test_rejects_bad_term_code(self, bad):
        with pytest.raises(SettingsValidationError):
            app_settings.validate("target_term_code", bad)

    def test_rejects_empty_active_term_codes(self):
        with pytest.raises(SettingsValidationError):
            app_settings.validate("active_term_codes", [])

    def test_rejects_unknown_role_map_key(self):
        with pytest.raises(SettingsValidationError):
            app_settings.validate("role_id_map", {"Not A Real Role": VALID_ID})

    def test_rejects_bad_role_map_value(self):
        name = next(iter(DEFAULT_ROLE_ID_MAP))
        with pytest.raises(SettingsValidationError):
            app_settings.validate("role_id_map", {name: "nope"})

    def test_blank_role_map_entry_is_dropped(self):
        name = next(iter(DEFAULT_ROLE_ID_MAP))
        assert app_settings.validate("role_id_map", {name: ""}) == {}

    def test_optional_snowflake_may_be_cleared(self):
        assert app_settings.validate("qna_helper_role_id", "") is None

    def test_required_snowflake_may_not_be_cleared(self):
        with pytest.raises(SettingsValidationError):
            app_settings.validate("verified_role_id", "")

    def test_iter_snowflakes_covers_every_shape(self):
        assert list(app_settings.iter_snowflakes("gold_guide_role_id", VALID_ID)) == [VALID_ID]
        assert list(
            app_settings.iter_snowflakes("admin_restricted_role_ids", [VALID_ID])
        ) == [VALID_ID]
        assert list(
            app_settings.iter_snowflakes("role_id_map", {"X": int(VALID_ID)})
        ) == [VALID_ID]


class TestRoleCategoriesStayInSync:
    def test_every_categorised_role_name_is_mapped(self):
        from routes.admin import MEMBER_ROLE_CATEGORIES

        categorised = {
            name for names in MEMBER_ROLE_CATEGORIES.values() for name in names
        }
        assert categorised <= set(DEFAULT_ROLE_ID_MAP), (
            "MEMBER_ROLE_CATEGORIES lists role names absent from DEFAULT_ROLE_ID_MAP: "
            f"{sorted(categorised - set(DEFAULT_ROLE_ID_MAP))}"
        )

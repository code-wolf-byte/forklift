"""The admin verification kill switch, enforced in asu_discord.api."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from asu_discord import api


@pytest.fixture
def no_dispatch(monkeypatch):
    """Record cog dispatches instead of performing them."""
    dispatched = MagicMock()
    monkeypatch.setattr(api, "_dispatch_to_cog", dispatched)
    monkeypatch.setattr(api, "_config", MagicMock())
    return dispatched


def _switch(monkeypatch, enabled: bool) -> None:
    monkeypatch.setattr(
        "utils.app_settings.get",
        lambda key: enabled if key == "verification_enabled" else None,
    )


class TestVerifiedRole:
    def test_granted_when_enabled(self, no_dispatch, monkeypatch):
        _switch(monkeypatch, True)
        api.assign_verified_role("123", asurite="jdoe")
        no_dispatch.assert_called_once()

    def test_skipped_when_disabled(self, no_dispatch, monkeypatch):
        _switch(monkeypatch, False)
        # Must not raise — the OAuth callback turns an exception into a 502.
        api.assign_verified_role("123", asurite="jdoe")
        no_dispatch.assert_not_called()


class TestSalesforceRoles:
    def test_assigned_when_enabled(self, no_dispatch, monkeypatch):
        _switch(monkeypatch, True)
        api.assign_roles_from_profile("123", MagicMock())
        no_dispatch.assert_called_once()

    def test_skipped_when_disabled(self, no_dispatch, monkeypatch):
        _switch(monkeypatch, False)
        api.assign_roles_from_profile("123", MagicMock())
        no_dispatch.assert_not_called()


class TestUnaffectedPaths:
    """Removal and refresh keep working — the switch only gates granting."""

    def test_remove_verified_role_still_dispatches(self, no_dispatch, monkeypatch):
        _switch(monkeypatch, False)
        api.remove_verified_role("123", reason="left the server")
        no_dispatch.assert_called_once()

    def test_refresh_from_profile_still_dispatches(self, no_dispatch, monkeypatch):
        _switch(monkeypatch, False)
        api.refresh_roles_from_profile("123", MagicMock())
        no_dispatch.assert_called_once()

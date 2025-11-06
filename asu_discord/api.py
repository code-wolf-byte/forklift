"""Discord OAuth2 and guild role helpers."""

from __future__ import annotations

import logging
from typing import Any, Dict
from urllib.parse import urlencode

import requests

from utils.settings import DISCORD_CONFIG, DiscordConfig

DEFAULT_TIMEOUT = 10
logger = logging.getLogger(__name__)


class DiscordAPIError(RuntimeError):
    """Raised when Discord API requests fail."""

    def __init__(self, message: str, *, status: int | None = None, payload: Dict[str, Any] | None = None):
        super().__init__(message)
        self.status = status
        self.payload = payload or {}


def _config() -> DiscordConfig:
    if DISCORD_CONFIG is None:
        raise DiscordAPIError(
            "Discord configuration is missing. Ensure Discord environment variables are set.",
            status=None,
        )
    return DISCORD_CONFIG


def build_authorize_url(state: str) -> str:
    cfg = _config()
    params = {
        "client_id": cfg.client_id,
        "response_type": "code",
        "redirect_uri": cfg.redirect_uri,
        "scope": cfg.scope,
        "state": state,
        "prompt": "consent",
    }
    return f"{cfg.authorize_base}?{urlencode(params)}"


def exchange_code_for_token(code: str) -> Dict[str, Any]:
    cfg = _config()
    data = {
        "client_id": cfg.client_id,
        "client_secret": cfg.client_secret,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": cfg.redirect_uri,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    try:
        response = requests.post(cfg.token_url, data=data, headers=headers, timeout=DEFAULT_TIMEOUT)
    except requests.RequestException as exc:
        logger.error("Discord token exchange request failed: %s", exc)
        raise DiscordAPIError("Unable to reach Discord for token exchange") from exc

    if response.status_code >= 400:
        payload = _safe_json(response)
        logger.error("Discord token exchange failed: %s", payload)
        raise DiscordAPIError("Discord token exchange failed", status=response.status_code, payload=payload)

    return _safe_json(response)


def fetch_user_profile(access_token: str) -> Dict[str, Any]:
    cfg = _config()
    url = f"{cfg.api_base}/users/@me"
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        response = requests.get(url, headers=headers, timeout=DEFAULT_TIMEOUT)
    except requests.RequestException as exc:
        logger.error("Discord user profile request failed: %s", exc)
        raise DiscordAPIError("Unable to reach Discord to fetch user profile") from exc

    if response.status_code >= 400:
        payload = _safe_json(response)
        logger.error("Discord user profile fetch failed: %s", payload)
        raise DiscordAPIError("Failed to fetch Discord user profile", status=response.status_code, payload=payload)

    return _safe_json(response)


def ensure_guild_membership(user_id: str, access_token: str) -> None:
    cfg = _config()
    url = f"{cfg.api_base}/guilds/{cfg.guild_id}/members/{user_id}"
    headers = {
        "Authorization": f"Bot {cfg.bot_token}",
        "Content-Type": "application/json",
    }
    json_payload = {"access_token": access_token}

    try:
        response = requests.put(url, headers=headers, json=json_payload, timeout=DEFAULT_TIMEOUT)
    except requests.RequestException as exc:
        logger.error("Discord guild join request failed: %s", exc)
        raise DiscordAPIError("Unable to add Discord user to guild") from exc

    if response.status_code not in {200, 201, 204}:
        payload = _safe_json(response)
        if payload.get("code") == 10004:
            logger.info(
                "Discord guild join returned Unknown Guild (code 10004); assuming user is already a member"
            )
            return
        logger.error("Discord guild join failed: %s", payload)
        raise DiscordAPIError("Failed to add Discord user to guild", status=response.status_code, payload=payload)


def assign_verified_role(user_id: str) -> None:
    cfg = _config()
    url = f"{cfg.api_base}/guilds/{cfg.guild_id}/members/{user_id}/roles/{cfg.verified_role_id}"
    headers = {
        "Authorization": f"Bot {cfg.bot_token}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.put(url, headers=headers, timeout=DEFAULT_TIMEOUT)
    except requests.RequestException as exc:
        logger.error("Discord role assignment request failed: %s", exc)
        raise DiscordAPIError("Unable to assign verified role in Discord") from exc

    if response.status_code not in {204, 201}:
        payload = _safe_json(response)
        if payload.get("code") == 10004:
            logger.info(
                "Discord role assignment returned Unknown Guild (code 10004); assuming role already applied"
            )
            return
        logger.error("Discord role assignment failed: %s", payload)
        raise DiscordAPIError("Failed to assign Discord verified role", status=response.status_code, payload=payload)


def _safe_json(response: requests.Response) -> Dict[str, Any]:
    try:
        data = response.json()
        if isinstance(data, dict):
            return data
    except ValueError:
        pass
    return {"text": response.text}


__all__ = [
    "DiscordAPIError",
    "assign_verified_role",
    "build_authorize_url",
    "ensure_guild_membership",
    "exchange_code_for_token",
    "fetch_user_profile",
]

from __future__ import annotations

import logging
import secrets
from datetime import datetime

from flask import Blueprint, redirect, request, session, url_for

from services.discord import (
    DiscordAPIError,
    assign_verified_role,
    build_authorize_url,
    ensure_guild_membership,
    exchange_code_for_token,
    fetch_user_profile,
)
from utils.database import User, session_scope
from utils.settings import CONFIG, DISCORD_CONFIG

discord_bp = Blueprint("discord", __name__)
logger = logging.getLogger(__name__)


def _oauth_failure(message: str, status_code: int = 400):
    failure_redirect = CONFIG.DISCORD_FAILURE_REDIRECT
    if failure_redirect:
        session["verification_error"] = message
        return redirect(failure_redirect)
    return message, status_code


@discord_bp.route("/auth/discord/login")
def discord_login():
    if DISCORD_CONFIG is None:
        logger.error("Discord login attempted without configuration")
        return _oauth_failure("Discord integration is not configured", 503)

    verification_state = session.get("verification_state")
    if not verification_state or not verification_state.get("saml_complete"):
        logger.info("Discord login requested without SAML completion")
        return redirect(url_for("saml.saml_login"))

    state_token = secrets.token_urlsafe(32)
    session["discord_oauth_state"] = state_token

    authorize_url = build_authorize_url(state_token)
    return redirect(authorize_url)


@discord_bp.route("/auth/discord/callback")
def discord_callback():
    if DISCORD_CONFIG is None:
        logger.error("Discord callback invoked without configuration")
        return _oauth_failure("Discord integration is not configured", 503)

    error = request.args.get("error")
    if error:
        logger.warning("Discord OAuth returned error: %s", error)
        return _oauth_failure(f"Discord authorization error: {error}", 400)

    state = request.args.get("state")
    expected_state = session.pop("discord_oauth_state", None)
    if not state or expected_state is None or state != expected_state:
        logger.error("Discord OAuth state mismatch: expected=%s received=%s", expected_state, state)
        return _oauth_failure("Invalid Discord OAuth state", 400)

    code = request.args.get("code")
    if not code:
        logger.error("Discord callback missing authorization code")
        return _oauth_failure("Missing Discord authorization code", 400)

    verification_state = session.get("verification_state") or {}
    if not verification_state.get("saml_complete"):
        logger.error("Discord callback without completed SAML verification")
        return _oauth_failure("SAML verification must be completed before Discord linking", 400)

    user_db_id = verification_state.get("user_id")
    if not user_db_id:
        logger.error("Verification session missing user reference")
        return _oauth_failure("Verification session has expired. Restart verification.", 400)

    try:
        token_data = exchange_code_for_token(code)
    except DiscordAPIError as exc:
        logger.error("Discord token exchange failed: %s", exc)
        return _oauth_failure(str(exc), 400)

    access_token = token_data.get("access_token")
    if not access_token:
        logger.error("Discord token exchange response missing access token: %s", token_data)
        return _oauth_failure("Discord token response missing access token", 500)

    try:
        profile = fetch_user_profile(access_token)
    except DiscordAPIError as exc:
        logger.error("Discord user profile fetch failed: %s", exc)
        return _oauth_failure(str(exc), 400)

    discord_user_id = profile.get("id")
    if not discord_user_id:
        logger.error("Discord profile missing user id: %s", profile)
        return _oauth_failure("Discord profile response missing user id", 500)

    try:
        with session_scope() as db_session:
            user = db_session.get(User, user_db_id)
            if user is None:
                logger.error("Database user for verification not found: id=%s", user_db_id)
                raise DiscordAPIError("Unable to load verification record for Discord linking")

            user.discord_user_id = discord_user_id
            user.discord_username = profile.get("username")
            user.discord_global_name = profile.get("global_name")
            user.discord_avatar = profile.get("avatar")

            ensure_guild_membership(discord_user_id, access_token)
            assign_verified_role(discord_user_id)

            user.verified = True
            user.verified_at = datetime.utcnow()
    except DiscordAPIError as exc:
        logger.error("Discord integration failed for user %s: %s", discord_user_id, exc)
        return _oauth_failure(str(exc), 502)
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Unexpected error linking Discord account")
        return _oauth_failure("Unexpected Discord verification failure", 500)

    verification_state.update(
        {
            "discord_user_id": discord_user_id,
            "discord_username": profile.get("username"),
            "discord_complete": True,
            "verified": True,
        }
    )
    session["verification_state"] = verification_state
    session["discord_user"] = profile

    success_redirect = CONFIG.DISCORD_SUCCESS_REDIRECT
    if success_redirect:
        return redirect(success_redirect)

    return {
        "status": "verified",
        "asurite": verification_state.get("asurite"),
        "email": verification_state.get("email"),
        "discord_user_id": discord_user_id,
        "discord_username": profile.get("username"),
    }

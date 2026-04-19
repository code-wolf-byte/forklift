from __future__ import annotations

import logging
import secrets
from datetime import datetime
from pathlib import Path

import yaml
from flask import Blueprint, redirect, request, session, url_for
from sqlalchemy.exc import IntegrityError

_ADMIN_CONFIG_PATH = Path(__file__).parent.parent / "config" / "verification.yaml"
with _ADMIN_CONFIG_PATH.open() as _f:
    _ADMIN_RESTRICTED_ROLE_IDS: list[str] = (
        yaml.safe_load(_f).get("admin", {}).get("restricted_role_ids", [])
    )

from asu_discord.api import (
    DiscordAPIError,
    assign_verified_role,
    assign_roles_from_profile,
    build_authorize_url,
    check_member_has_any_role,
    check_member_is_admin,
    exchange_code_for_token,
    fetch_user_profile,
    remove_verified_role,
    remove_roles_from_profile,
)
from asu_discord.salesforce import get_student_profile
from utils.database import User, session_scope
from utils.settings import CONFIG, DISCORD_CONFIG

discord_bp = Blueprint("discord", __name__)
logger = logging.getLogger(__name__)
BANNED_VERIFICATION_MESSAGE = "This ASURITE is banned from verification."


def _oauth_failure(message: str, status_code: int = 400):
    failure_redirect = CONFIG.DISCORD_FAILURE_REDIRECT
    if failure_redirect:
        session["verification_error"] = message
        return redirect(failure_redirect)
    return message, status_code


@discord_bp.route("/auth/discord/login")
def discord_login():
    if not CONFIG.CAS_ENABLED:
        logger.info("Discord login requested while CAS is disabled")
        return _oauth_failure("ASU single sign-on is disabled in this environment", 503)
    if DISCORD_CONFIG is None:
        logger.error("Discord login attempted without configuration")
        return _oauth_failure("Discord integration is not configured", 503)

    verification_state = session.get("verification_state")
    if not verification_state or not verification_state.get("cas_complete"):
        logger.info("Discord login requested without CAS completion")
        return redirect(url_for("cas.cas_login"))

    user_id = verification_state.get("user_id")
    if user_id:
        with session_scope() as db_session:
            user = db_session.get(User, user_id)
            if user is not None and user.banned:
                session["verification_error"] = BANNED_VERIFICATION_MESSAGE
                return _oauth_failure(BANNED_VERIFICATION_MESSAGE, 403)

    state_token = secrets.token_urlsafe(32)
    session["discord_oauth_state"] = state_token

    authorize_url = build_authorize_url(state_token)
    return redirect(authorize_url)


@discord_bp.route("/auth/discord/callback")
def discord_callback():
    if not CONFIG.CAS_ENABLED:
        logger.error("Discord callback invoked while CAS is disabled")
        return _oauth_failure("CAS verification is disabled in this environment", 503)
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
        logger.error(
            "Discord OAuth state mismatch: expected=%s received=%s",
            expected_state,
            state,
        )
        return _oauth_failure("Invalid Discord OAuth state", 400)

    code = request.args.get("code")
    if not code:
        logger.error("Discord callback missing authorization code")
        return _oauth_failure("Missing Discord authorization code", 400)

    verification_state = session.get("verification_state") or {}
    if not verification_state.get("cas_complete"):
        logger.error("Discord callback without completed CAS verification")
        return _oauth_failure(
            "CAS verification must be completed before Discord linking", 400
        )

    user_db_id = verification_state.get("user_id")
    if not user_db_id:
        logger.error("Verification session missing user reference")
        return _oauth_failure(
            "Verification session has expired. Restart verification.", 400
        )

    with session_scope() as db_session:
        user = db_session.get(User, user_db_id)
        if user is not None and user.banned:
            session["verification_error"] = BANNED_VERIFICATION_MESSAGE
            return _oauth_failure(BANNED_VERIFICATION_MESSAGE, 403)

    try:
        token_data = exchange_code_for_token(code)
    except DiscordAPIError as exc:
        logger.error("Discord token exchange failed: %s", exc)
        return _oauth_failure(str(exc), 400)

    try:
        profile = fetch_user_profile(token_data.access_token)
    except DiscordAPIError as exc:
        logger.error("Discord user profile fetch failed: %s", exc)
        return _oauth_failure(str(exc), 400)

    discord_user_id = profile.id

    asurite = verification_state.get("asurite")
    old_discord_user_id: str | None = None
    try:
        with session_scope() as db_session:
            user = db_session.get(User, user_db_id)
            if user is None:
                logger.error(
                    "Database user for verification not found: id=%s", user_db_id
                )
                raise DiscordAPIError(
                    "Unable to load verification record for Discord linking"
                )
            if user.banned:
                session["verification_error"] = BANNED_VERIFICATION_MESSAGE
                return _oauth_failure(BANNED_VERIFICATION_MESSAGE, 403)

            if asurite and user.asurite_id != asurite:
                user = (
                    db_session.query(User)
                    .filter(User.asurite_id == asurite)
                    .one_or_none()
                )
                if user is None:
                    logger.error(
                        "Database user for ASURITE %s not found during verification",
                        asurite,
                    )
                    raise DiscordAPIError(
                        "Unable to load verification record for Discord linking"
                    )
                if user.banned:
                    session["verification_error"] = BANNED_VERIFICATION_MESSAGE
                    return _oauth_failure(BANNED_VERIFICATION_MESSAGE, 403)
                user_db_id = user.id
                verification_state["user_id"] = user_db_id

            existing_user = (
                db_session.query(User)
                .filter(User.discord_user_id == discord_user_id, User.id != user.id)
                .one_or_none()
            )
            if existing_user:
                asurite = verification_state.get("asurite")
                if asurite and existing_user.asurite_id == asurite:
                    logger.warning(
                        "Discord user %s already linked to ASURITE %s under id %s; "
                        "refreshing that record instead of %s",
                        discord_user_id,
                        asurite,
                        existing_user.id,
                        user.id,
                    )
                    user = existing_user
                    user_db_id = user.id
                    verification_state["user_id"] = user_db_id
                else:
                    message = (
                        "This Discord account is already linked to another ASURITE. "
                        "If this is your account, please contact support."
                    )
                    session["verification_error"] = message
                    return _oauth_failure(message, 409)

            if user.discord_user_id == discord_user_id and (
                not asurite or user.asurite_id == asurite
            ):
                user.updated_at = datetime.utcnow()
            else:
                if user.discord_user_id and user.discord_user_id != discord_user_id:
                    old_discord_user_id = user.discord_user_id
                    try:
                        remove_verified_role(
                            user.discord_user_id,
                            reason=f"Re-linking verification for {user.asurite_id}",
                        )
                    except DiscordAPIError as exc:
                        logger.warning(
                            "Failed to remove verified role for Discord user %s: %s",
                            user.discord_user_id,
                            exc,
                        )

                user.discord_user_id = discord_user_id
                user.discord_username = profile.username
                user.discord_global_name = profile.global_name
                user.discord_avatar = profile.avatar
                user.verified = True
                user.verified_at = datetime.utcnow()
                if user.created_at != user.verified_at:
                    user.created_at = user.verified_at

            try:
                assign_verified_role(
                    discord_user_id, asurite=verification_state.get("asurite")
                )
            except DiscordAPIError as exc:
                logger.error(
                    "Discord integration failed for user %s: %s", discord_user_id, exc
                )
                return _oauth_failure(str(exc), 502)
    except IntegrityError as exc:
        if "users.discord_user_id" not in str(getattr(exc, "orig", exc)):
            logger.exception("Unexpected database error linking Discord account")
            return _oauth_failure("Unexpected Discord verification failure", 500)

        logger.warning(
            "Discord user %s triggered unique constraint; attempting to reuse existing record",
            discord_user_id,
        )
        try:
            with session_scope() as db_session:
                existing_user = (
                    db_session.query(User)
                    .filter(User.discord_user_id == discord_user_id)
                    .one_or_none()
                )
                if existing_user is None:
                    logger.exception(
                        "Discord user %s caused uniqueness error but no existing record was found",
                        discord_user_id,
                    )
                    return _oauth_failure(
                        "Unexpected Discord verification failure", 500
                    )

                asurite = verification_state.get("asurite")
                if asurite and existing_user.asurite_id != asurite:
                    message = (
                        "This Discord account is already linked to another ASURITE. "
                        "If this is your account, please contact support."
                    )
                    session["verification_error"] = message
                    return _oauth_failure(message, 409)

                if existing_user.discord_user_id == discord_user_id and (
                    not asurite or existing_user.asurite_id == asurite
                ):
                    existing_user.updated_at = datetime.utcnow()
                else:
                    existing_user.discord_username = profile.username
                    existing_user.discord_global_name = profile.global_name
                    existing_user.discord_avatar = profile.avatar
                    existing_user.verified = True
                    existing_user.verified_at = datetime.utcnow()
                    if existing_user.created_at != existing_user.verified_at:
                        existing_user.created_at = existing_user.verified_at

                user_db_id = existing_user.id
                verification_state["user_id"] = user_db_id
        except Exception:  # pragma: no cover - defensive
            logger.exception("Failed to recover from Discord uniqueness error")
            return _oauth_failure("Unexpected Discord verification failure", 500)

        try:
            assign_verified_role(
                discord_user_id, asurite=verification_state.get("asurite")
            )
        except DiscordAPIError as assign_exc:
            logger.error(
                "Discord integration failed for user %s: %s",
                discord_user_id,
                assign_exc,
            )
            return _oauth_failure(str(assign_exc), 502)
    except DiscordAPIError as exc:
        logger.error("Discord integration failed for user %s: %s", discord_user_id, exc)
        return _oauth_failure(str(exc), 502)
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Unexpected error linking Discord account")
        return _oauth_failure("Unexpected Discord verification failure", 500)

    # After Discord verification, attempt to look up the student's Salesforce profile.
    # Any failures here are non-fatal; verification still succeeds.
    asurite = verification_state.get("asurite")
    student_profile = get_student_profile(asurite) if asurite else None

    verification_state.update(
        {
            "discord_user_id": discord_user_id,
            "discord_username": profile.username,
            "discord_complete": True,
            "verified": True,
        }
    )
    session["verification_state"] = verification_state
    session["discord_user"] = profile.model_dump()

    # Check and persist admin status (non-fatal if bot is unavailable)
    is_admin = False
    try:
        is_admin = check_member_is_admin(discord_user_id)
    except Exception:
        logger.warning("Failed to check admin status for Discord user %s", discord_user_id)
    try:
        with session_scope() as db_session:
            admin_user = db_session.get(User, user_db_id)
            if admin_user is not None:
                admin_user.is_admin = is_admin
    except Exception:
        logger.warning("Failed to update is_admin in DB for user %s", user_db_id)
    session["is_admin"] = is_admin

    is_officer = False
    try:
        is_officer = (not is_admin) and check_member_has_any_role(discord_user_id, _ADMIN_RESTRICTED_ROLE_IDS)
    except Exception:
        logger.warning("Failed to check officer role for Discord user %s", discord_user_id)
    session["is_officer"] = is_officer

    if student_profile is not None:
        profile_dict = student_profile.model_dump()
        verification_state["student_profile"] = profile_dict
        session["student_profile"] = profile_dict

        # Assign additional Discord roles based on Salesforce profile data.
        try:
            if old_discord_user_id and old_discord_user_id != discord_user_id:
                try:
                    remove_roles_from_profile(old_discord_user_id, student_profile)
                except DiscordAPIError as exc:
                    logger.warning(
                        "Failed to remove Salesforce-based roles for user %s: %s",
                        old_discord_user_id,
                        exc,
                    )

            logger.info(
                "Salesforce profile data for %s (Discord %s): %s",
                asurite,
                discord_user_id,
                student_profile,
            )
            assign_roles_from_profile(discord_user_id, student_profile)
        except DiscordAPIError as exc:
            logger.error(
                "Failed to assign Salesforce-based roles for user %s: %s",
                discord_user_id,
                exc,
            )
        except Exception:  # pragma: no cover - defensive
            logger.exception(
                "Unexpected error assigning Salesforce-based roles for user %s",
                discord_user_id,
            )

    success_redirect = CONFIG.DISCORD_SUCCESS_REDIRECT
    if success_redirect:
        return redirect(success_redirect)

    return {
        "status": "verified",
        "asurite": verification_state.get("asurite"),
        "email": verification_state.get("email"),
        "discord_user_id": discord_user_id,
        "discord_username": profile.username,
    }

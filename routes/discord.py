from __future__ import annotations

import logging
import secrets
import threading
from datetime import datetime
from pathlib import Path

import yaml
from flask import Blueprint, jsonify, redirect, request, session, url_for

_ADMIN_CONFIG_PATH = Path(__file__).parent.parent / "config" / "verification.yaml"
with _ADMIN_CONFIG_PATH.open() as _f:
    _admin_cfg = yaml.safe_load(_f).get("admin", {})
    _ADMIN_ROLE_IDS: list[str] = _admin_cfg.get("role_ids") or []
    _ADMIN_RESTRICTED_ROLE_IDS: list[str] = _admin_cfg.get("restricted_role_ids") or []

from asu_discord.api import (
    DiscordAPIError,
    assign_verified_role,
    assign_roles_from_profile,
    build_authorize_url,
    check_member_has_any_role,
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


@discord_bp.route("/auth/discord/prepare", methods=["POST"])
def discord_prepare():
    """Return the Discord OAuth2 URL as JSON for client-side navigation.

    Client-side navigation (window.location.href) triggers mobile app links,
    allowing the Discord app to open instead of the mobile browser.
    """
    if not CONFIG.CAS_ENABLED:
        return jsonify({"error": "ASU single sign-on is disabled"}), 503
    if DISCORD_CONFIG is None:
        return jsonify({"error": "Discord integration is not configured"}), 503

    verification_state = session.get("verification_state")
    if not verification_state or not verification_state.get("cas_complete"):
        return jsonify({"error": "CAS verification required", "redirect": url_for("cas.cas_login")}), 403

    user_id = verification_state.get("user_id")
    if user_id:
        with session_scope() as db_session:
            user = db_session.get(User, user_id)
            if user is not None and user.banned:
                return jsonify({"error": BANNED_VERIFICATION_MESSAGE}), 403

    state_token = secrets.token_urlsafe(32)
    session["discord_oauth_state"] = state_token

    authorize_url = build_authorize_url(state_token)
    return jsonify({"authorize_url": authorize_url})


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
            # ASURITE (from CAS) is the authoritative, only-unique identity. Resolve the
            # record by ASURITE; fall back to the session's user id if ASURITE is missing.
            user = None
            if asurite:
                user = (
                    db_session.query(User)
                    .filter(User.asurite_id == asurite)
                    .one_or_none()
                )
            if user is None:
                user = db_session.get(User, user_db_id)
            if user is None:
                logger.error(
                    "Database user for verification not found: id=%s asurite=%s",
                    user_db_id,
                    asurite,
                )
                raise DiscordAPIError(
                    "Unable to load verification record for Discord linking"
                )

            user_db_id = user.id
            verification_state["user_id"] = user_db_id

            # Banned ASURITEs may not link any Discord account.
            if user.banned:
                session["verification_error"] = BANNED_VERIFICATION_MESSAGE
                return _oauth_failure(BANNED_VERIFICATION_MESSAGE, 403)

            # This Discord account may already be linked to a *different* ASURITE record
            # (e.g. a compromised/old account). Since ASURITE is authoritative, detach
            # the Discord account from those records so the current user can claim it.
            other_links = (
                db_session.query(User)
                .filter(User.discord_user_id == discord_user_id, User.id != user.id)
                .all()
            )
            for other in other_links:
                logger.warning(
                    "Discord account %s was linked to ASURITE %s (id=%s); detaching in "
                    "favor of ASURITE %s",
                    discord_user_id,
                    other.asurite_id,
                    other.id,
                    user.asurite_id,
                )
                other.discord_user_id = None
                other.verified = False
                other.verified_at = None

            # If the ASURITE record currently points at a different Discord account,
            # unverify that old account in the Discord server before re-linking.
            if user.discord_user_id and user.discord_user_id != discord_user_id:
                old_discord_user_id = user.discord_user_id
                try:
                    remove_verified_role(
                        old_discord_user_id,
                        reason=f"Re-linking verification for {user.asurite_id}",
                    )
                except DiscordAPIError as exc:
                    logger.warning(
                        "Failed to remove verified role for Discord user %s: %s",
                        old_discord_user_id,
                        exc,
                    )

            # Link (or refresh) the Discord account on the ASURITE record.
            if user.discord_user_id != discord_user_id:
                user.verified_at = datetime.utcnow()
                if user.created_at != user.verified_at:
                    user.created_at = user.verified_at
            user.discord_user_id = discord_user_id
            user.discord_username = profile.username
            user.discord_global_name = profile.global_name
            user.discord_avatar = profile.avatar
            user.verified = True
            user.updated_at = datetime.utcnow()

            try:
                assign_verified_role(discord_user_id, asurite=asurite)
            except DiscordAPIError as exc:
                logger.error(
                    "Discord integration failed for user %s: %s", discord_user_id, exc
                )
                return _oauth_failure(str(exc), 502)
    except DiscordAPIError as exc:
        logger.error("Discord integration failed for user %s: %s", discord_user_id, exc)
        return _oauth_failure(str(exc), 502)
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Unexpected error linking Discord account")
        return _oauth_failure("Unexpected Discord verification failure", 500)

    # After Discord verification, attempt to look up the student's Salesforce profile.
    # Any failures here are non-fatal; verification still succeeds.
    asurite = verification_state.get("asurite")
    student_profile = None
    if asurite:
        try:
            student_profile = get_student_profile(asurite)
            if student_profile and "asurite" in student_profile:
                from utils.salesforce import cache_sf_profile
                threading.Thread(
                    target=cache_sf_profile,
                    args=(asurite, student_profile),
                    daemon=True,
                ).start()
        except Exception:  # pragma: no cover - defensive
            logger.exception(
                "Failed to fetch Salesforce student profile for %s", asurite
            )

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
        is_admin = check_member_has_any_role(discord_user_id, _ADMIN_ROLE_IDS)
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
        # The full Salesforce profile is NOT stored in the session: `opportunities` is
        # unbounded (39 entries -> 112KB JSON -> 11.8KB Set-Cookie even after zlib),
        # which blows past nginx's 4K proxy_buffer_size (502) and the browser's 4K
        # per-cookie limit. Nothing reads it back. Roles are derived from it here.

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

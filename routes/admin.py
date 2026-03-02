from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from functools import wraps

from flask import Blueprint, abort, jsonify, redirect, request, send_from_directory, session

from utils.database import User, session_scope

admin_bp = Blueprint("admin", __name__)
logger = logging.getLogger(__name__)

REACT_BUILD_DIR = os.getenv(
    "REACT_BUILD_DIR",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "asu-unity-react", "dist"),
)


def require_admin(f):
    """Decorator: enforces CAS+Discord completion and is_admin session flag."""

    @wraps(f)
    def decorated(*args, **kwargs):
        verification_state = session.get("verification_state") or {}
        cas_complete = bool(verification_state.get("cas_complete"))
        discord_complete = bool(
            verification_state.get("discord_complete") or verification_state.get("verified")
        )
        if not (cas_complete and discord_complete and session.get("is_admin")):
            abort(403)
        return f(*args, **kwargs)

    return decorated


@admin_bp.route("/api/admin/me")
def admin_me():
    verification_state = session.get("verification_state") or {}
    cas_complete = bool(verification_state.get("cas_complete"))
    discord_complete = bool(
        verification_state.get("discord_complete") or verification_state.get("verified")
    )
    if not (cas_complete and discord_complete):
        return jsonify({"error": "Unauthorized"}), 403

    discord_user_id = verification_state.get("discord_user_id")
    if not discord_user_id:
        return jsonify({"error": "Unauthorized"}), 403

    user = None
    is_admin = False
    with session_scope() as db_session:
        user = (
            db_session.query(User)
            .filter(User.discord_user_id == discord_user_id)
            .one_or_none()
        )
        if user is None:
            return jsonify({"error": "User not found"}), 404
        is_admin = bool(user.is_admin)
        asurite_id = user.asurite_id
        discord_username = user.discord_username
        discord_avatar = user.discord_avatar

    # Refresh session is_admin from DB
    session["is_admin"] = is_admin

    if not is_admin:
        return jsonify({"error": "Forbidden"}), 403

    return jsonify(
        {
            "asurite_id": asurite_id,
            "discord_username": discord_username,
            "discord_user_id": discord_user_id,
            "discord_avatar": discord_avatar,
            "is_admin": is_admin,
        }
    )


@admin_bp.route("/api/admin/stats")
@require_admin
def admin_stats():
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_naive = today_start.replace(tzinfo=None)

    with session_scope() as db_session:
        total_users = db_session.query(User).count()
        verified_count = db_session.query(User).filter(User.verified == True).count()  # noqa: E712
        today_verifications = (
            db_session.query(User)
            .filter(User.verified == True, User.verified_at >= today_naive)  # noqa: E712
            .count()
        )

    return jsonify(
        {
            "total_users": total_users,
            "verified_count": verified_count,
            "today_verifications": today_verifications,
        }
    )


@admin_bp.route("/api/admin/users")
@require_admin
def admin_users():
    page = max(1, request.args.get("page", 1, type=int))
    per_page = min(100, max(1, request.args.get("per_page", 50, type=int)))
    offset = (page - 1) * per_page

    with session_scope() as db_session:
        total = db_session.query(User).count()
        users = (
            db_session.query(User).order_by(User.id.desc()).offset(offset).limit(per_page).all()
        )
        user_list = [
            {
                "id": u.id,
                "asurite_id": u.asurite_id,
                "discord_username": u.discord_username,
                "discord_user_id": u.discord_user_id,
                "verified": u.verified,
                "verified_at": u.verified_at.isoformat() if u.verified_at else None,
                "banned": u.banned,
                "is_admin": u.is_admin,
            }
            for u in users
        ]

    return jsonify(
        {
            "users": user_list,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": (total + per_page - 1) // per_page,
        }
    )


@admin_bp.route("/admin")
@admin_bp.route("/admin/<path:path>")
def admin_spa(path=""):
    verification_state = session.get("verification_state") or {}
    cas_complete = bool(verification_state.get("cas_complete"))
    discord_complete = bool(
        verification_state.get("discord_complete") or verification_state.get("verified")
    )
    if not (cas_complete and discord_complete and session.get("is_admin")):
        return redirect("/")

    react_index = os.path.join(REACT_BUILD_DIR, "index.html")
    if not os.path.exists(react_index):
        abort(404)

    if path and os.path.exists(os.path.join(REACT_BUILD_DIR, path)):
        return send_from_directory(REACT_BUILD_DIR, path)
    return send_from_directory(REACT_BUILD_DIR, "index.html")

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from functools import wraps
from zoneinfo import ZoneInfo

from flask import Blueprint, abort, jsonify, redirect, request, send_from_directory, session

from utils.database import CronJobConfig, User, session_scope

AZ_TZ = ZoneInfo("America/Phoenix")

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


def _next_run_az(cfg: CronJobConfig) -> str:
    """Return next scheduled run time as an AZ-aware ISO string."""
    now_az = datetime.now(AZ_TZ)
    scheduled_today = now_az.replace(
        hour=cfg.schedule_hour, minute=cfg.schedule_minute, second=0, microsecond=0
    )
    already_ran_today = False
    if cfg.last_run_at is not None:
        last_az = cfg.last_run_at.replace(tzinfo=timezone.utc).astimezone(AZ_TZ)
        already_ran_today = last_az.date() >= now_az.date()

    if not already_ran_today:
        return scheduled_today.isoformat()
    return (scheduled_today + timedelta(days=1)).isoformat()


def _serialize_cron_config(cfg: CronJobConfig) -> dict:
    last_run_str = None
    if cfg.last_run_at is not None:
        last_az = cfg.last_run_at.replace(tzinfo=timezone.utc).astimezone(AZ_TZ)
        last_run_str = last_az.isoformat()
    return {
        "job_name": cfg.job_name,
        "display_name": cfg.display_name,
        "enabled": cfg.enabled,
        "schedule_hour": cfg.schedule_hour,
        "schedule_minute": cfg.schedule_minute,
        "last_run_at": last_run_str,
        "next_run_at": _next_run_az(cfg),
    }


@admin_bp.route("/api/admin/automations")
@require_admin
def admin_automations():
    with session_scope() as db_session:
        configs = db_session.query(CronJobConfig).order_by(CronJobConfig.id.asc()).all()
    return jsonify([_serialize_cron_config(c) for c in configs])


@admin_bp.route("/api/admin/automations/<job_name>", methods=["PUT"])
@require_admin
def admin_update_automation(job_name: str):
    data = request.get_json(silent=True) or {}

    with session_scope() as db_session:
        cfg = (
            db_session.query(CronJobConfig)
            .filter(CronJobConfig.job_name == job_name)
            .one_or_none()
        )
        if cfg is None:
            return jsonify({"error": "Not found"}), 404

        if "enabled" in data:
            cfg.enabled = bool(data["enabled"])
        if "schedule_hour" in data:
            h = int(data["schedule_hour"])
            if not 0 <= h <= 23:
                return jsonify({"error": "schedule_hour must be 0–23"}), 400
            cfg.schedule_hour = h
        if "schedule_minute" in data:
            m = int(data["schedule_minute"])
            if not 0 <= m <= 59:
                return jsonify({"error": "schedule_minute must be 0–59"}), 400
            cfg.schedule_minute = m

    with session_scope() as db_session:
        cfg = (
            db_session.query(CronJobConfig)
            .filter(CronJobConfig.job_name == job_name)
            .one()
        )
        return jsonify(_serialize_cron_config(cfg))


@admin_bp.route("/api/admin/automations/<job_name>/trigger", methods=["POST"])
@require_admin
def admin_trigger_automation(job_name: str):
    from cron import cron_manager

    if job_name not in cron_manager.job_names:
        return jsonify({"error": "Unknown job"}), 404

    success = cron_manager.run_jobs(job_names=[job_name], raise_on_error=False)
    return jsonify({"status": "triggered" if success else "failed", "job_name": job_name})


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

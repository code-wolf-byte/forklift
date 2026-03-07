from __future__ import annotations

import logging
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from functools import wraps
from zoneinfo import ZoneInfo

from flask import Blueprint, abort, jsonify, redirect, request, send_from_directory, session
from sqlalchemy import func

from utils.database import CronJobConfig, User, UserRole, session_scope

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

    # Period for retention/leaves stats — defaults to current month in AZ time
    from_date_str = request.args.get("from_date")
    to_date_str = request.args.get("to_date")

    now_az = datetime.now(AZ_TZ)
    if from_date_str:
        from_dt = _parse_az_date(from_date_str)
    else:
        from_dt = (
            now_az.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            .astimezone(timezone.utc)
            .replace(tzinfo=None)
        )
        from_date_str = now_az.replace(day=1).date().isoformat()

    if to_date_str:
        to_dt = _parse_az_date(to_date_str, end_of_day=True)
    else:
        to_dt = now_az.astimezone(timezone.utc).replace(tzinfo=None)
        to_date_str = now_az.date().isoformat()

    with session_scope() as db_session:
        total_users = db_session.query(User).count()
        verified_count = db_session.query(User).filter(User.verified == True).count()  # noqa: E712
        today_verifications = (
            db_session.query(User)
            .filter(User.verified == True, User.verified_at >= today_naive)  # noqa: E712
            .count()
        )

        # Verified users who left during the period
        verified_leaves = (
            db_session.query(User)
            .filter(
                User.verified == True,  # noqa: E712
                User.left_at.isnot(None),
                User.left_at >= from_dt,
                User.left_at <= to_dt,
            )
            .count()
        )

        # Verified users as of start of period (verified before period began)
        verified_at_start = (
            db_session.query(User)
            .filter(User.verified == True, User.verified_at < from_dt)  # noqa: E712
            .count()
        )

        # Verified users as of end of period
        verified_at_end = (
            db_session.query(User)
            .filter(User.verified == True, User.verified_at <= to_dt)  # noqa: E712
            .count()
        )

    retention_rate = (
        round(((verified_at_start - verified_leaves) / verified_at_start) * 100, 1)
        if verified_at_start > 0
        else None
    )

    return jsonify(
        {
            "total_users": total_users,
            "verified_count": verified_count,
            "today_verifications": today_verifications,
            "verified_leaves": verified_leaves,
            "verified_at_start": verified_at_start,
            "verified_at_end": verified_at_end,
            "retention_rate": retention_rate,
            "period": {"from_date": from_date_str, "to_date": to_date_str},
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

    if not already_ran_today and scheduled_today > now_az:
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
        "channel_id": cfg.channel_id,
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
        if "channel_id" in data:
            cfg.channel_id = data["channel_id"] or None

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


@admin_bp.route("/api/admin/discord-channels")
@require_admin
def admin_discord_channels():
    try:
        from asu_discord.api import get_guild_channels
        channels = get_guild_channels()
    except Exception:
        channels = []
    return jsonify(channels)


# ─── Roles ────────────────────────────────────────────────────────────────────

@admin_bp.route("/api/admin/roles")
@require_admin
def admin_roles():
    with session_scope() as db_session:
        rows = (
            db_session.query(UserRole.role_name, func.count(UserRole.id).label("cnt"))
            .group_by(UserRole.role_name)
            .order_by(UserRole.role_name.asc())
            .all()
        )
    return jsonify([{"role_name": r, "count": c} for r, c in rows])


# ─── Activity helpers ─────────────────────────────────────────────────────────

def _parse_az_date(date_str: str | None, *, end_of_day: bool = False) -> datetime | None:
    """Parse a YYYY-MM-DD string in AZ time and return a naive UTC datetime."""
    if not date_str:
        return None
    try:
        dt = datetime.fromisoformat(date_str)
        if end_of_day:
            dt = dt.replace(hour=23, minute=59, second=59)
        return dt.replace(tzinfo=AZ_TZ).astimezone(timezone.utc).replace(tzinfo=None)
    except ValueError:
        return None


def _activity_query(db_session, date_col, from_dt, to_dt, role: str | None, exclude_role: str | None = None):
    """Filtered User query on the given date column, optionally restricted to a role."""
    q = db_session.query(User).filter(date_col.isnot(None))
    if from_dt:
        q = q.filter(date_col >= from_dt)
    if to_dt:
        q = q.filter(date_col <= to_dt)
    if role:
        q = (
            q.join(UserRole, UserRole.user_id == User.id)
            .filter(UserRole.role_name == role)
            .distinct()
        )
    if exclude_role:
        subq = (
            db_session.query(UserRole.user_id)
            .filter(UserRole.role_name == exclude_role)
            .subquery()
        )
        q = q.filter(~User.id.in_(subq))
    return q


def _chart_data(dates: list, from_dt, to_dt) -> list:
    """Aggregate naive-UTC datetimes by AZ date, zero-filling the full range."""
    counter: Counter = Counter()
    for dt in dates:
        if dt is not None:
            az_date = dt.replace(tzinfo=timezone.utc).astimezone(AZ_TZ).date()
            counter[az_date] += 1

    if from_dt and to_dt:
        start = from_dt.replace(tzinfo=timezone.utc).astimezone(AZ_TZ).date()
        end = to_dt.replace(tzinfo=timezone.utc).astimezone(AZ_TZ).date()
    elif counter:
        start, end = min(counter), max(counter)
    else:
        return []

    result, cur = [], start
    while cur <= end:
        result.append({"date": cur.isoformat(), "count": counter.get(cur, 0)})
        cur += timedelta(days=1)
    return result


def _serialize_activity(u: User, date_field: str) -> dict:
    dt = getattr(u, date_field)
    dt_az = dt.replace(tzinfo=timezone.utc).astimezone(AZ_TZ).isoformat() if dt else None
    return {
        "id": u.id,
        "asurite_id": u.asurite_id,
        "discord_username": u.discord_username,
        "discord_user_id": u.discord_user_id,
        "discord_avatar": u.discord_avatar,
        date_field: dt_az,
    }


def _paginated_activity(date_col, date_field: str):
    from_dt  = _parse_az_date(request.args.get("from_date"))
    to_dt    = _parse_az_date(request.args.get("to_date"), end_of_day=True)
    role     = request.args.get("role") or None
    page     = max(1, request.args.get("page", 1, type=int))
    per_page = min(100, max(1, request.args.get("per_page", 25, type=int)))
    offset   = (page - 1) * per_page

    with session_scope() as db_session:
        q = _activity_query(db_session, date_col, from_dt, to_dt, role)
        total = q.count()
        users = q.order_by(date_col.desc()).offset(offset).limit(per_page).all()
        result = [_serialize_activity(u, date_field) for u in users]

    return jsonify({
        "users": result,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": max(1, (total + per_page - 1) // per_page),
    })


def _chart_activity(date_col):
    from_dt = _parse_az_date(request.args.get("from_date"))
    to_dt   = _parse_az_date(request.args.get("to_date"), end_of_day=True)
    role    = request.args.get("role") or None

    with session_scope() as db_session:
        dates = [u.joined_at if date_col is User.joined_at else u.left_at
                 for u in _activity_query(db_session, date_col, from_dt, to_dt, role).all()]

    return jsonify(_chart_data(dates, from_dt, to_dt))


# ─── Server joins ─────────────────────────────────────────────────────────────

@admin_bp.route("/api/admin/server-joins")
@require_admin
def admin_server_joins():
    return _paginated_activity(User.joined_at, "joined_at")


@admin_bp.route("/api/admin/server-joins/chart")
@require_admin
def admin_server_joins_chart():
    from_dt      = _parse_az_date(request.args.get("from_date"))
    to_dt        = _parse_az_date(request.args.get("to_date"), end_of_day=True)
    role         = request.args.get("role") or None
    exclude_role = request.args.get("exclude_role") or None
    with session_scope() as db_session:
        dates = [u.joined_at for u in
                 _activity_query(db_session, User.joined_at, from_dt, to_dt, role, exclude_role).all()]
    return jsonify(_chart_data(dates, from_dt, to_dt))


# ─── Server leaves ────────────────────────────────────────────────────────────

@admin_bp.route("/api/admin/server-leaves")
@require_admin
def admin_server_leaves():
    return _paginated_activity(User.left_at, "left_at")


@admin_bp.route("/api/admin/server-leaves/chart")
@require_admin
def admin_server_leaves_chart():
    from_dt      = _parse_az_date(request.args.get("from_date"))
    to_dt        = _parse_az_date(request.args.get("to_date"), end_of_day=True)
    role         = request.args.get("role") or None
    exclude_role = request.args.get("exclude_role") or None
    with session_scope() as db_session:
        dates = [u.left_at for u in
                 _activity_query(db_session, User.left_at, from_dt, to_dt, role, exclude_role).all()]
    return jsonify(_chart_data(dates, from_dt, to_dt))


@admin_bp.route("/api/admin/joins")
@require_admin
def admin_joins():
    limit = min(100, max(1, request.args.get("limit", 50, type=int)))
    with session_scope() as db_session:
        users = (
            db_session.query(User)
            .filter(User.verified == True)  # noqa: E712
            .filter(User.verified_at.isnot(None))
            .order_by(User.verified_at.desc())
            .limit(limit)
            .all()
        )
        result = [
            {
                "id": u.id,
                "asurite_id": u.asurite_id,
                "discord_username": u.discord_username,
                "discord_user_id": u.discord_user_id,
                "discord_avatar": u.discord_avatar,
                "verified_at": u.verified_at.isoformat() if u.verified_at else None,
            }
            for u in users
        ]
    return jsonify(result)


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

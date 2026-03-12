from __future__ import annotations

import logging
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from functools import wraps
from zoneinfo import ZoneInfo

from flask import Blueprint, Response, abort, jsonify, redirect, request, send_from_directory, session
from sqlalchemy import func

import csv
import io

from utils.database import CronJobConfig, MessageBackfill, MessageLog, User, UserRole, session_scope

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


@admin_bp.route("/api/admin/automations/<job_name>/reset", methods=["POST"])
@require_admin
def admin_reset_automation(job_name: str):
    """Clear last_run_at so the next run fetches all records from the beginning."""
    from cron import cron_manager

    if job_name not in cron_manager.job_names:
        return jsonify({"error": "Unknown job"}), 404

    with session_scope() as db_session:
        cfg = (
            db_session.query(CronJobConfig)
            .filter(CronJobConfig.job_name == job_name)
            .one_or_none()
        )
        if cfg is None:
            return jsonify({"error": "Job config not found"}), 404
        cfg.last_run_at = None

    logger.info("Reset last_run_at for job %s", job_name)
    return jsonify({"status": "reset", "job_name": job_name})


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

MEMBER_ROLE_CATEGORIES: dict[str, list[str]] = {
    "Academic Level": [
        "First Year",
        "Transfer Student",
        "Graduate Student",
        "Upperclassmen",
    ],
    "College": [
        "Barrett The Honors College",
        "Ira A. Fulton Schools of Engineering",
        "College of Liberal Arts and Sciences",
        "College of Global Futures",
        "Edson College of Nursing and Health Innovation",
        "Herberger Institute for Design and the Arts",
        "Thunderbird School of Global Management",
        "Mary Lou Fulton Teachers College",
        "New College of Interdisciplinary Arts and Sciences",
        "College of Integrative Sciences and Arts",
        "W.P. Carey School of Business",
        "Walter Cronkite School of Journalism and Mass Communication",
        "Watts College of Public Service and Community Solutions",
        "University College",
    ],
    "Campus": [
        "Tempe",
        "Downtown Phoenix",
        "Polytechnic",
        "LA Center",
        "West Valley",
        "Online",
    ],
    "Residency": [
        "Out of State",
        "Arizona Resident",
        "International Student",
    ],
    "Special": [
        "First Generation Student",
    ],
}


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


@admin_bp.route("/api/admin/member-stats")
@require_admin
def admin_member_stats():
    """Role distribution stats mirroring the get_studet_data.py script, queryable by date."""
    from_dt = _parse_az_date(request.args.get("from_date"))
    to_dt = _parse_az_date(request.args.get("to_date"), end_of_day=True)
    from_date_str = request.args.get("from_date", "")
    to_date_str = request.args.get("to_date", "")

    with session_scope() as db_session:
        # Base: verified users filtered by verified_at date range
        base_q = db_session.query(User).filter(User.verified == True)  # noqa: E712
        if from_dt:
            base_q = base_q.filter(User.verified_at >= from_dt)
        if to_dt:
            base_q = base_q.filter(User.verified_at <= to_dt)
        total_verified = base_q.count()

        # Count of verified users who have left (left_at is set)
        left_count = base_q.filter(User.left_at.isnot(None)).count()

        # Role counts: how many verified users (in range) have each role
        role_count_q = (
            db_session.query(UserRole.role_name, func.count(UserRole.user_id.distinct()).label("cnt"))
            .join(User, User.id == UserRole.user_id)
            .filter(User.verified == True)  # noqa: E712
        )
        if from_dt:
            role_count_q = role_count_q.filter(User.verified_at >= from_dt)
        if to_dt:
            role_count_q = role_count_q.filter(User.verified_at <= to_dt)
        role_count_map = {name: cnt for name, cnt in role_count_q.group_by(UserRole.role_name).all()}

        categories = []
        for cat_name, role_list in MEMBER_ROLE_CATEGORIES.items():
            # Users with at least one role in this category
            users_with_q = (
                db_session.query(func.count(UserRole.user_id.distinct()))
                .join(User, User.id == UserRole.user_id)
                .filter(
                    User.verified == True,  # noqa: E712
                    UserRole.role_name.in_(role_list),
                )
            )
            if from_dt:
                users_with_q = users_with_q.filter(User.verified_at >= from_dt)
            if to_dt:
                users_with_q = users_with_q.filter(User.verified_at <= to_dt)
            users_with = users_with_q.scalar() or 0

            role_breakdown = sorted(
                [{"role": r, "count": role_count_map.get(r, 0)} for r in role_list],
                key=lambda x: -x["count"],
            )
            categories.append(
                {
                    "name": cat_name,
                    "roles": role_breakdown,
                    "users_with": users_with,
                    "users_missing": total_verified - users_with,
                }
            )

    return jsonify(
        {
            "total_verified": total_verified,
            "currently_in_server": total_verified - left_count,
            "left_server": left_count,
            "categories": categories,
            "period": {"from_date": from_date_str, "to_date": to_date_str},
        }
    )


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


def _activity_query(db_session, date_col, from_dt, to_dt, roles=None, exclude_roles=None):
    """Filtered User query on the given date column.

    roles        – list of role names the user must ALL have (AND semantics).
    exclude_roles – list of role names the user must NOT have.
    """
    q = db_session.query(User).filter(date_col.isnot(None))
    if from_dt:
        q = q.filter(date_col >= from_dt)
    if to_dt:
        q = q.filter(date_col <= to_dt)
    for role in (roles or []):
        subq = (
            db_session.query(UserRole.user_id)
            .filter(UserRole.role_name == role)
            .subquery()
        )
        q = q.filter(User.id.in_(subq))
    for excl in (exclude_roles or []):
        subq = (
            db_session.query(UserRole.user_id)
            .filter(UserRole.role_name == excl)
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
    roles    = request.args.getlist("role") or None
    page     = max(1, request.args.get("page", 1, type=int))
    per_page = min(100, max(1, request.args.get("per_page", 25, type=int)))
    offset   = (page - 1) * per_page

    with session_scope() as db_session:
        q = _activity_query(db_session, date_col, from_dt, to_dt, roles)
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
    roles   = request.args.getlist("role") or None

    with session_scope() as db_session:
        dates = [u.joined_at if date_col is User.joined_at else u.left_at
                 for u in _activity_query(db_session, date_col, from_dt, to_dt, roles).all()]

    return jsonify(_chart_data(dates, from_dt, to_dt))


# ─── Server joins ─────────────────────────────────────────────────────────────

@admin_bp.route("/api/admin/server-joins")
@require_admin
def admin_server_joins():
    return _paginated_activity(User.joined_at, "joined_at")


@admin_bp.route("/api/admin/server-joins/chart")
@require_admin
def admin_server_joins_chart():
    from_dt       = _parse_az_date(request.args.get("from_date"))
    to_dt         = _parse_az_date(request.args.get("to_date"), end_of_day=True)
    roles         = request.args.getlist("role") or None
    exclude_roles = request.args.getlist("exclude_role") or None
    with session_scope() as db_session:
        dates = [u.joined_at for u in
                 _activity_query(db_session, User.joined_at, from_dt, to_dt, roles, exclude_roles).all()]
    return jsonify(_chart_data(dates, from_dt, to_dt))


# ─── Server leaves ────────────────────────────────────────────────────────────

@admin_bp.route("/api/admin/server-leaves")
@require_admin
def admin_server_leaves():
    return _paginated_activity(User.left_at, "left_at")


@admin_bp.route("/api/admin/server-leaves/chart")
@require_admin
def admin_server_leaves_chart():
    from_dt       = _parse_az_date(request.args.get("from_date"))
    to_dt         = _parse_az_date(request.args.get("to_date"), end_of_day=True)
    roles         = request.args.getlist("role") or None
    exclude_roles = request.args.getlist("exclude_role") or None
    with session_scope() as db_session:
        dates = [u.left_at for u in
                 _activity_query(db_session, User.left_at, from_dt, to_dt, roles, exclude_roles).all()]
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


# ─── Message logs ─────────────────────────────────────────────────────────────

def _message_query(db_session, from_dt, to_dt, channel_ids, roles, exclude_roles):
    """Base query for MessageLog with date, channel, and role filters."""
    q = db_session.query(MessageLog)
    if from_dt:
        q = q.filter(MessageLog.sent_at >= from_dt)
    if to_dt:
        q = q.filter(MessageLog.sent_at <= to_dt)
    if channel_ids:
        q = q.filter(MessageLog.channel_id.in_(channel_ids))
    for role in (roles or []):
        subq = (
            db_session.query(User.discord_user_id)
            .join(UserRole, UserRole.user_id == User.id)
            .filter(UserRole.role_name == role)
            .subquery()
        )
        q = q.filter(MessageLog.discord_user_id.in_(subq))
    for excl in (exclude_roles or []):
        subq = (
            db_session.query(User.discord_user_id)
            .join(UserRole, UserRole.user_id == User.id)
            .filter(UserRole.role_name == excl)
            .subquery()
        )
        q = q.filter(~MessageLog.discord_user_id.in_(subq))
    return q


def _parse_message_filters():
    """Parse shared query params for message log endpoints."""
    from_dt      = _parse_az_date(request.args.get("from_date"))
    to_dt        = _parse_az_date(request.args.get("to_date"), end_of_day=True)
    channel_ids  = request.args.getlist("channel_id") or None
    roles        = request.args.getlist("role") or None
    exclude_roles = request.args.getlist("exclude_role") or None
    return from_dt, to_dt, channel_ids, roles, exclude_roles


@admin_bp.route("/api/admin/message-logs/channels")
@require_admin
def admin_message_channels():
    """Distinct channels that have logged messages, with counts."""
    with session_scope() as db_session:
        rows = (
            db_session.query(
                MessageLog.channel_id,
                MessageLog.channel_name,
                func.count(MessageLog.id).label("cnt"),
            )
            .group_by(MessageLog.channel_id, MessageLog.channel_name)
            .order_by(func.count(MessageLog.id).desc())
            .all()
        )
    return jsonify(
        [{"channel_id": cid, "channel_name": cname or cid, "count": cnt}
         for cid, cname, cnt in rows]
    )


@admin_bp.route("/api/admin/message-logs/heatmap")
@require_admin
def admin_message_heatmap():
    """Return a 7×24 activity heatmap (day-of-week × hour) in AZ time."""
    from_dt, to_dt, channel_ids, roles, exclude_roles = _parse_message_filters()

    with session_scope() as db_session:
        q = _message_query(db_session, from_dt, to_dt, channel_ids, roles, exclude_roles)
        timestamps = [row.sent_at for row in q.with_entities(MessageLog.sent_at).all()]

    counts: dict[tuple[int, int], int] = {}
    for ts in timestamps:
        dt_az = ts.replace(tzinfo=timezone.utc).astimezone(AZ_TZ)
        key = (dt_az.weekday(), dt_az.hour)  # (0=Mon … 6=Sun, 0–23)
        counts[key] = counts.get(key, 0) + 1

    total = sum(counts.values())
    cells = [
        {"dow": dow, "hour": hour, "count": counts.get((dow, hour), 0)}
        for dow in range(7)
        for hour in range(24)
    ]
    return jsonify({"cells": cells, "total": total})


@admin_bp.route("/api/admin/message-logs/export")
@require_admin
def admin_message_export():
    """Paginated message log with optional user info joined from users table."""
    from_dt, to_dt, channel_ids, roles, exclude_roles = _parse_message_filters()
    page     = max(1, request.args.get("page", 1, type=int))
    per_page = min(200, max(1, request.args.get("per_page", 50, type=int)))
    offset   = (page - 1) * per_page

    with session_scope() as db_session:
        q = _message_query(db_session, from_dt, to_dt, channel_ids, roles, exclude_roles)
        total = q.count()
        rows = q.order_by(MessageLog.sent_at.desc()).offset(offset).limit(per_page).all()

        # Build a discord_user_id → User lookup for matched users
        user_ids = list({r.discord_user_id for r in rows})
        users_map = {
            u.discord_user_id: u
            for u in db_session.query(User)
            .filter(User.discord_user_id.in_(user_ids))
            .all()
        }

        result = []
        for r in rows:
            u = users_map.get(r.discord_user_id)
            dt_az = r.sent_at.replace(tzinfo=timezone.utc).astimezone(AZ_TZ)
            result.append({
                "message_id": r.message_id,
                "channel_id": r.channel_id,
                "channel_name": r.channel_name,
                "discord_user_id": r.discord_user_id,
                "discord_username": u.discord_username if u else None,
                "asurite_id": u.asurite_id if u else None,
                "sent_at": dt_az.isoformat(),
            })

    return jsonify({
        "rows": result,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": max(1, (total + per_page - 1) // per_page),
    })


@admin_bp.route("/api/admin/message-logs/export/csv")
@require_admin
def admin_message_export_csv():
    """Stream all matching message logs as a CSV download."""
    from_dt, to_dt, channel_ids, roles, exclude_roles = _parse_message_filters()

    with session_scope() as db_session:
        q = _message_query(db_session, from_dt, to_dt, channel_ids, roles, exclude_roles)
        rows = q.order_by(MessageLog.sent_at.asc()).all()

        user_ids = list({r.discord_user_id for r in rows})
        users_map = {
            u.discord_user_id: u
            for u in db_session.query(User)
            .filter(User.discord_user_id.in_(user_ids))
            .all()
        }

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            "sent_at_az", "channel_name", "channel_id",
            "discord_username", "asurite_id", "discord_user_id", "message_id", "content",
        ])
        for r in rows:
            u = users_map.get(r.discord_user_id)
            dt_az = r.sent_at.replace(tzinfo=timezone.utc).astimezone(AZ_TZ)
            writer.writerow([
                dt_az.strftime("%Y-%m-%d %H:%M:%S"),
                r.channel_name or "",
                r.channel_id,
                u.discord_username if u else "",
                u.asurite_id if u else "",
                r.discord_user_id,
                r.message_id,
                r.content or "",
            ])

    filename = "message_logs.csv"
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@admin_bp.route("/api/admin/message-logs/backfill", methods=["POST"])
@require_admin
def admin_message_backfill_start():
    """Trigger the one-year backfill on the running Discord bot."""
    from asu_discord.shared import get_running_bot, get_running_loop
    from asu_discord.cogs.message_logger import MessageLoggerCog

    bot = get_running_bot()
    if bot is None:
        return jsonify({"error": "Discord bot is not running"}), 503

    cog = bot.cogs.get("MessageLoggerCog")
    if cog is None or not isinstance(cog, MessageLoggerCog):
        return jsonify({"error": "MessageLoggerCog not loaded"}), 503

    loop = get_running_loop()
    if loop is None:
        return jsonify({"error": "Bot event loop unavailable"}), 503

    if cog.backfill_running:
        return jsonify({"status": "already_running"})

    # start_backfill() is synchronous (schedules an asyncio task); call it
    # from the bot's event loop thread so ensure_future runs in the right loop.
    loop.call_soon_threadsafe(cog.start_backfill)
    return jsonify({"status": "started"})


@admin_bp.route("/api/admin/message-logs/backfill/status")
@require_admin
def admin_message_backfill_status():
    """Return per-channel backfill progress."""
    from asu_discord.shared import get_running_bot
    from asu_discord.cogs.message_logger import MessageLoggerCog

    bot = get_running_bot()
    cog = bot.cogs.get("MessageLoggerCog") if bot else None
    backfill_running = isinstance(cog, MessageLoggerCog) and cog.backfill_running

    with session_scope() as db_session:
        rows = (
            db_session.query(MessageBackfill)
            .order_by(MessageBackfill.channel_name.asc())
            .all()
        )
        total_messages = db_session.query(func.count(MessageLog.id)).scalar() or 0

    def _fmt(dt):
        if dt is None:
            return None
        return dt.replace(tzinfo=timezone.utc).astimezone(AZ_TZ).isoformat()

    channels = [
        {
            "channel_id": r.channel_id,
            "channel_name": r.channel_name,
            "status": r.status,
            "messages_fetched": r.messages_fetched,
            "oldest_fetched_at": _fmt(r.oldest_fetched_at),
            "started_at": _fmt(r.started_at),
            "completed_at": _fmt(r.completed_at),
            "error": r.error,
        }
        for r in rows
    ]
    done = sum(1 for r in rows if r.status == "done")
    return jsonify({
        "backfill_running": backfill_running,
        "total_messages_logged": total_messages,
        "channels_total": len(rows),
        "channels_done": done,
        "channels": channels,
    })


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

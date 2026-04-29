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

import threading as _threading

from utils.database import (
    CronJobConfig,
    ForumPost,
    GoldGuideContribution,
    MessageBackfill,
    MessageLog,
    ModerationEvent,
    QnaPost,
    User,
    UserRole,
    UserRoleException,
    UserSalesforceProfile,
    VoiceSession,
    session_scope,
)

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


def _serialize_cron_config(cfg: CronJobConfig, extra_stats: dict | None = None) -> dict:
    last_run_str = None
    if cfg.last_run_at is not None:
        last_az = cfg.last_run_at.replace(tzinfo=timezone.utc).astimezone(AZ_TZ)
        last_run_str = last_az.isoformat()
    result = {
        "job_name": cfg.job_name,
        "display_name": cfg.display_name,
        "enabled": cfg.enabled,
        "schedule_hour": cfg.schedule_hour,
        "schedule_minute": cfg.schedule_minute,
        "last_run_at": last_run_str,
        "next_run_at": _next_run_az(cfg),
        "channel_id": cfg.channel_id,
    }
    if extra_stats is not None:
        result["stats"] = extra_stats
    return result


def _get_incomplete_verification_stats(db_session) -> dict:
    """Return n/x conversion stats for the incomplete verification export job.

    x = users who were actually exported (have incomplete_sftp_exported_at set)
    n = of those, how many eventually verified (completed the full flow)
    currently_incomplete = exported but still not verified
    """
    total_exported = (
        db_session.query(User)
        .filter(User.incomplete_sftp_exported_at.isnot(None))
        .count()
    )
    verified_after_export = (
        db_session.query(User)
        .filter(
            User.incomplete_sftp_exported_at.isnot(None),
            User.verified == True,  # noqa: E712
        )
        .count()
    )
    currently_incomplete = (
        db_session.query(User)
        .filter(
            User.incomplete_sftp_exported_at.isnot(None),
            User.verified == False,  # noqa: E712
            User.discord_user_id.is_(None),
        )
        .count()
    )
    return {
        "verified": verified_after_export,
        "total_exported": total_exported,
        "currently_incomplete": currently_incomplete,
    }


@admin_bp.route("/api/admin/automations")
@require_admin
def admin_automations():
    with session_scope() as db_session:
        configs = db_session.query(CronJobConfig).order_by(CronJobConfig.id.asc()).all()
        result = []
        for c in configs:
            extra = None
            if c.job_name == "upload_incomplete_verifications_to_sftp":
                extra = _get_incomplete_verification_stats(db_session)
            result.append(_serialize_cron_config(c, extra_stats=extra))
    return jsonify(result)


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
        extra = None
        if job_name == "upload_incomplete_verifications_to_sftp":
            extra = _get_incomplete_verification_stats(db_session)
        return jsonify(_serialize_cron_config(cfg, extra_stats=extra))


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
    """Return activity heatmap in AZ time.

    Query param ``groupby``:
      - ``dow``  (default) — 7×24 grid aggregated by day-of-week
      - ``date`` — N×24 grid with one row per calendar date
    """
    from_dt, to_dt, channel_ids, roles, exclude_roles = _parse_message_filters()
    groupby = request.args.get("groupby", "dow")

    with session_scope() as db_session:
        q = _message_query(db_session, from_dt, to_dt, channel_ids, roles, exclude_roles)
        timestamps = [row.sent_at for row in q.with_entities(MessageLog.sent_at).all()]

    total = len(timestamps)

    if groupby == "date":
        date_counts: dict[tuple, int] = {}
        for ts in timestamps:
            dt_az = ts.replace(tzinfo=timezone.utc).astimezone(AZ_TZ)
            key = (dt_az.strftime("%Y-%m-%d"), dt_az.hour)
            date_counts[key] = date_counts.get(key, 0) + 1

        dates = sorted({k[0] for k in date_counts})
        cells = [
            {"date": date, "hour": hour, "count": date_counts.get((date, hour), 0)}
            for date in dates
            for hour in range(24)
        ]
        return jsonify({"cells": cells, "dates": dates, "total": total})

    # Default: day-of-week × hour
    dow_counts: dict[tuple[int, int], int] = {}
    for ts in timestamps:
        dt_az = ts.replace(tzinfo=timezone.utc).astimezone(AZ_TZ)
        key = (dt_az.weekday(), dt_az.hour)  # (0=Mon … 6=Sun, 0–23)
        dow_counts[key] = dow_counts.get(key, 0) + 1

    cells = [
        {"dow": dow, "hour": hour, "count": dow_counts.get((dow, hour), 0)}
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

    from_label = from_dt.strftime("%Y-%m-%d") if from_dt else "start"
    to_label = to_dt.strftime("%Y-%m-%d") if to_dt else "end"
    filename = f"message_logs_{from_label}_to_{to_label}.csv"
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
    from asu_discord.cogs.analytics import AnalyticsCog

    bot = get_running_bot()
    if bot is None:
        return jsonify({"error": "Discord bot is not running"}), 503

    cog = bot.cogs.get("AnalyticsCog")
    if cog is None or not isinstance(cog, AnalyticsCog):
        return jsonify({"error": "AnalyticsCog not loaded"}), 503

    loop = get_running_loop()
    if loop is None:
        return jsonify({"error": "Bot event loop unavailable"}), 503

    if cog.backfill_running:
        return jsonify({"status": "already_running"})

    loop.call_soon_threadsafe(cog.start_backfill)
    return jsonify({"status": "started"})


@admin_bp.route("/api/admin/message-logs/backfill/status")
@require_admin
def admin_message_backfill_status():
    """Return per-channel backfill progress."""
    from asu_discord.shared import get_running_bot
    from asu_discord.cogs.analytics import AnalyticsCog

    bot = get_running_bot()
    cog = bot.cogs.get("AnalyticsCog") if bot else None
    backfill_running = isinstance(cog, AnalyticsCog) and cog.backfill_running

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


@admin_bp.route("/api/admin/qna/backfill", methods=["POST"])
@require_admin
def admin_qna_backfill_start():
    """Trigger a QnA post + Gold Guide contribution backfill on the running bot."""
    from asu_discord.shared import get_running_bot, get_running_loop
    from asu_discord.cogs.qna import QnACog

    bot = get_running_bot()
    if bot is None:
        return jsonify({"error": "Discord bot is not running"}), 503

    cog = bot.cogs.get("QnACog")
    if cog is None or not isinstance(cog, QnACog):
        return jsonify({"error": "QnACog not loaded"}), 503

    loop = get_running_loop()
    if loop is None:
        return jsonify({"error": "Bot event loop unavailable"}), 503

    if cog.backfill_running:
        return jsonify({"status": "already_running", "progress": cog._backfill_progress})

    loop.call_soon_threadsafe(cog.start_backfill)
    return jsonify({"status": "started"})


@admin_bp.route("/api/admin/qna/backfill/status", methods=["GET"])
@require_admin
def admin_qna_backfill_status():
    """Return current QnA backfill progress."""
    from asu_discord.shared import get_running_bot
    from asu_discord.cogs.qna import QnACog

    bot = get_running_bot()
    cog = bot.cogs.get("QnACog") if bot else None

    if cog is None or not isinstance(cog, QnACog):
        return jsonify({"error": "QnACog not loaded"}), 503

    return jsonify({
        "backfill_running": cog.backfill_running,
        **cog._backfill_progress,
    })


@admin_bp.route("/api/admin/qna/stats", methods=["GET"])
@require_admin
def admin_qna_stats():
    """Overall QnA post breakdown by status and tag."""
    with session_scope() as db_session:
        rows = db_session.query(QnaPost).all()

    status_counts: dict[str, int] = {}
    tag_counts: dict[str, int] = {}
    tag_by_status: dict[str, dict[str, int]] = {}

    for post in rows:
        status_counts[post.status] = status_counts.get(post.status, 0) + 1
        post_tags: list[str] = []
        if post.tags:
            try:
                import json as _json
                post_tags = _json.loads(post.tags)
            except Exception:
                pass
        if not post_tags:
            post_tags = ["(no tag)"]
        for tag in post_tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
            tag_by_status.setdefault(tag, {})
            tag_by_status[tag][post.status] = tag_by_status[tag].get(post.status, 0) + 1

    tags = [
        {"tag": tag, "total": count, "by_status": tag_by_status.get(tag, {})}
        for tag, count in sorted(tag_counts.items(), key=lambda x: -x[1])
    ]

    return jsonify({
        "total": len(rows),
        "by_status": status_counts,
        "by_tag": tags,
    })


@admin_bp.route("/api/admin/qna/gold-guide-stats", methods=["GET"])
@require_admin
def admin_gold_guide_stats():
    """Gold Guide contribution counts per member per channel, with optional date range."""
    from_date_str = request.args.get("from_date")
    to_date_str = request.args.get("to_date")

    from_dt = None
    to_dt = None
    if from_date_str:
        try:
            from_dt = datetime.strptime(from_date_str, "%Y-%m-%d").replace(tzinfo=AZ_TZ).astimezone(timezone.utc).replace(tzinfo=None)
        except ValueError:
            return jsonify({"error": "Invalid from_date, expected YYYY-MM-DD"}), 400
    if to_date_str:
        try:
            to_dt = (datetime.strptime(to_date_str, "%Y-%m-%d") + timedelta(days=1)).replace(tzinfo=AZ_TZ).astimezone(timezone.utc).replace(tzinfo=None)
        except ValueError:
            return jsonify({"error": "Invalid to_date, expected YYYY-MM-DD"}), 400

    with session_scope() as db_session:
        q = db_session.query(GoldGuideContribution)
        if from_dt:
            q = q.filter(GoldGuideContribution.responded_at >= from_dt)
        if to_dt:
            q = q.filter(GoldGuideContribution.responded_at < to_dt)
        contributions = q.order_by(GoldGuideContribution.responded_at.asc()).all()

    # Aggregate: per guide → per channel → count
    guide_map: dict[str, dict] = {}
    for c in contributions:
        gid = c.responder_discord_id
        if gid not in guide_map:
            guide_map[gid] = {
                "discord_id": gid,
                "username": c.responder_username,
                "total": 0,
                "by_channel": {},
            }
        guide_map[gid]["total"] += 1
        ch_key = c.channel_id
        if ch_key not in guide_map[gid]["by_channel"]:
            guide_map[gid]["by_channel"][ch_key] = {
                "channel_id": c.channel_id,
                "channel_name": c.channel_name,
                "count": 0,
            }
        guide_map[gid]["by_channel"][ch_key]["count"] += 1

    gold_guides = []
    for entry in sorted(guide_map.values(), key=lambda x: -x["total"]):
        gold_guides.append({
            "discord_id": entry["discord_id"],
            "username": entry["username"],
            "total_contributions": entry["total"],
            "by_channel": sorted(entry["by_channel"].values(), key=lambda x: -x["count"]),
        })

    return jsonify({
        "total_contributions": len(contributions),
        "gold_guides": gold_guides,
    })


# ─── Analytics ───────────────────────────────────────────────────────────────

_COLLEGE_ROLES = [
    "New College of Interdisciplinary Arts and Sciences",
    "Herberger Institute for Design and the Arts",
    "Edson College of Nursing and Health Innovation",
    "College of Integrative Sciences and Arts",
    "Walter Cronkite School of Journalism and Mass Communication",
    "Watts College of Public Service and Community Solutions",
    "Ira A. Fulton Schools of Engineering",
    "College of Global Futures",
    "College of Health Solutions",
    "Mary Lou Fulton Teachers College",
    "W.P. Carey School of Business",
    "College of Liberal Arts and Sciences",
    "Thunderbird School of Global Management",
    "University College",
]


@admin_bp.route("/api/admin/analytics")
@require_admin
def admin_analytics():
    import json as _json

    from_dt = _parse_az_date(request.args.get("from_date"))
    to_dt = _parse_az_date(request.args.get("to_date"), end_of_day=True)

    with session_scope() as db_session:
        # ── Core Activity ──────────────────────────────────────────────────────
        msg_q = db_session.query(MessageLog)
        if from_dt:
            msg_q = msg_q.filter(MessageLog.sent_at >= from_dt)
        if to_dt:
            msg_q = msg_q.filter(MessageLog.sent_at <= to_dt)
        messages_sent = msg_q.count()
        unique_talkers = (
            msg_q.with_entities(func.count(MessageLog.discord_user_id.distinct())).scalar() or 0
        )

        # ── Growth & Funnel / Onboarding ───────────────────────────────────────
        joins_q = db_session.query(User).filter(User.joined_at.isnot(None))
        if from_dt:
            joins_q = joins_q.filter(User.joined_at >= from_dt)
        if to_dt:
            joins_q = joins_q.filter(User.joined_at <= to_dt)
        total_joins = joins_q.count()

        verified_q = db_session.query(User).filter(User.verified == True)  # noqa: E712
        if from_dt:
            verified_q = verified_q.filter(User.verified_at >= from_dt)
        if to_dt:
            verified_q = verified_q.filter(User.verified_at <= to_dt)
        period_verified = verified_q.count()

        unverified_q = db_session.query(User).filter(
            User.verified == False, User.joined_at.isnot(None)  # noqa: E712
        )
        if from_dt:
            unverified_q = unverified_q.filter(User.joined_at >= from_dt)
        if to_dt:
            unverified_q = unverified_q.filter(User.joined_at <= to_dt)
        period_unverified = unverified_q.count()

        # ── Growth & Funnel / Retention ────────────────────────────────────────
        total_verified_alltime = (
            db_session.query(User).filter(User.verified == True).count()  # noqa: E712
        )
        in_server_count = (
            db_session.query(User)
            .filter(User.verified == True, User.left_at.is_(None))  # noqa: E712
            .count()
        )
        total_unverified_alltime = (
            db_session.query(User)
            .filter(User.verified == False, User.discord_user_id.isnot(None))  # noqa: E712
            .count()
        )

        retention_rate = None
        if from_dt:
            verified_at_start = (
                db_session.query(User)
                .filter(User.verified == True, User.verified_at < from_dt)  # noqa: E712
                .count()
            )
            leaves_q = db_session.query(User).filter(
                User.verified == True,  # noqa: E712
                User.left_at.isnot(None),
                User.left_at >= from_dt,
            )
            if to_dt:
                leaves_q = leaves_q.filter(User.left_at <= to_dt)
            leaves_count = leaves_q.count()
            if verified_at_start > 0:
                retention_rate = round(
                    ((verified_at_start - leaves_count) / verified_at_start) * 100, 1
                )

        # ── Channel Engagement ─────────────────────────────────────────────────
        ch_q = db_session.query(
            MessageLog.channel_id,
            MessageLog.channel_name,
            func.count(MessageLog.id).label("cnt"),
        )
        if from_dt:
            ch_q = ch_q.filter(MessageLog.sent_at >= from_dt)
        if to_dt:
            ch_q = ch_q.filter(MessageLog.sent_at <= to_dt)
        ch_rows = (
            ch_q.group_by(MessageLog.channel_id, MessageLog.channel_name)
            .order_by(func.count(MessageLog.id).desc())
            .limit(25)
            .all()
        )
        channels = [
            {"rank": i + 1, "channel_id": cid, "channel_name": cname or cid, "messages": cnt}
            for i, (cid, cname, cnt) in enumerate(ch_rows)
        ]

        # ── Demographics ───────────────────────────────────────────────────────
        demo_q = (
            db_session.query(
                UserRole.role_name,
                func.count(UserRole.user_id.distinct()).label("cnt"),
            )
            .join(User, User.id == UserRole.user_id)
            .filter(User.verified == True)  # noqa: E712
        )
        if from_dt:
            demo_q = demo_q.filter(User.verified_at >= from_dt)
        if to_dt:
            demo_q = demo_q.filter(User.verified_at <= to_dt)
        role_counts = {name: cnt for name, cnt in demo_q.group_by(UserRole.role_name).all()}

        # ── Voice (from voice_sessions) ────────────────────────────────────────
        vs_q = db_session.query(VoiceSession).filter(VoiceSession.left_at.isnot(None))
        if from_dt:
            vs_q = vs_q.filter(VoiceSession.joined_at >= from_dt)
        if to_dt:
            vs_q = vs_q.filter(VoiceSession.joined_at <= to_dt)
        total_voice_seconds = (
            vs_q.with_entities(func.coalesce(func.sum(VoiceSession.duration_seconds), 0)).scalar()
            or 0
        )
        voice_hours = round(total_voice_seconds / 3600, 1) if total_voice_seconds else None
        unique_speakers = (
            vs_q.with_entities(func.count(VoiceSession.discord_user_id.distinct())).scalar() or 0
        ) or None

        # Channel voice activity
        vc_rows = (
            vs_q.with_entities(
                VoiceSession.channel_id,
                VoiceSession.channel_name,
                func.sum(VoiceSession.duration_seconds).label("dur"),
                func.count(VoiceSession.id).label("sessions"),
            )
            .group_by(VoiceSession.channel_id, VoiceSession.channel_name)
            .order_by(func.sum(VoiceSession.duration_seconds).desc())
            .limit(25)
            .all()
        )
        voice_by_channel = {
            str(cid): {"channel_name": cname or cid, "voice_seconds": dur or 0, "sessions": ses}
            for cid, cname, dur, ses in vc_rows
        }

        # ── Moderation (from moderation_events + User.banned) ──────────────────
        banned_count = db_session.query(User).filter(User.banned == True).count()  # noqa: E712
        me_q = db_session.query(ModerationEvent)
        if from_dt:
            me_q = me_q.filter(ModerationEvent.occurred_at >= from_dt)
        if to_dt:
            me_q = me_q.filter(ModerationEvent.occurred_at <= to_dt)
        period_bans = me_q.filter(ModerationEvent.event_type == "ban").count()
        period_unbans = me_q.filter(ModerationEvent.event_type == "unban").count()

        # ── Forum Posts (from forum_posts) ─────────────────────────────────────
        fp_q = db_session.query(ForumPost)
        if from_dt:
            fp_q = fp_q.filter(ForumPost.created_at >= from_dt)
        if to_dt:
            fp_q = fp_q.filter(ForumPost.created_at <= to_dt)

        connect_posts = (
            fp_q.filter(ForumPost.parent_channel_name.ilike("%major%")).count()
        )
        roommate_posts = (
            fp_q.filter(ForumPost.parent_channel_name.ilike("%roommate%")).count()
        )
        forum_by_channel = (
            fp_q.with_entities(
                ForumPost.parent_channel_id,
                ForumPost.parent_channel_name,
                func.count(ForumPost.id).label("posts"),
            )
            .group_by(ForumPost.parent_channel_id, ForumPost.parent_channel_name)
            .order_by(func.count(ForumPost.id).desc())
            .all()
        )

        # ── International / Country of Origin ─────────────────────────────────
        country_q = (
            db_session.query(
                UserSalesforceProfile.country,
                func.count(UserSalesforceProfile.id).label("cnt"),
            )
            .filter(
                UserSalesforceProfile.is_international == True,  # noqa: E712
                UserSalesforceProfile.fetch_error.is_(None),
            )
            .group_by(UserSalesforceProfile.country)
            .order_by(func.count(UserSalesforceProfile.id).desc())
        )
        country_rows = country_q.all()
        international_country = (
            [{"country": c or "Unknown", "count": cnt} for c, cnt in country_rows]
            or None
        )

        # ── Programs / Gold Guides ─────────────────────────────────────────────
        gg_q = db_session.query(GoldGuideContribution)
        if from_dt:
            gg_q = gg_q.filter(GoldGuideContribution.responded_at >= from_dt)
        if to_dt:
            gg_q = gg_q.filter(GoldGuideContribution.responded_at <= to_dt)
        gg_total = gg_q.count()
        active_guides = (
            gg_q.with_entities(
                func.count(GoldGuideContribution.responder_discord_id.distinct())
            ).scalar()
            or 0
        )
        guide_dist_rows = (
            gg_q.with_entities(
                GoldGuideContribution.responder_discord_id,
                GoldGuideContribution.responder_username,
                func.count(GoldGuideContribution.id).label("cnt"),
            )
            .group_by(
                GoldGuideContribution.responder_discord_id,
                GoldGuideContribution.responder_username,
            )
            .order_by(func.count(GoldGuideContribution.id).desc())
            .limit(15)
            .all()
        )
        guide_distribution = [
            {"discord_id": did, "username": uname or did, "messages": cnt}
            for did, uname, cnt in guide_dist_rows
        ]

        # ── Forums / Ask ASU Staff ─────────────────────────────────────────────
        qna_q = db_session.query(QnaPost)
        if from_dt:
            qna_q = qna_q.filter(QnaPost.created_at >= from_dt)
        if to_dt:
            qna_q = qna_q.filter(QnaPost.created_at <= to_dt)
        all_posts = qna_q.all()
        total_posts = len(all_posts)
        bot_answered = sum(1 for p in all_posts if p.status == "satisfied")
        staff_answered = sum(1 for p in all_posts if p.status == "needs_help")

        tag_counts: dict[str, int] = {}
        for post in all_posts:
            if post.tags:
                try:
                    tags = _json.loads(post.tags)
                except Exception:
                    tags = []
                for tag in tags:
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1
        by_tag = sorted(
            [{"tag": t, "count": c} for t, c in tag_counts.items()],
            key=lambda x: -x["count"],
        )

    return jsonify(
        {
            "period": {
                "from_date": request.args.get("from_date", ""),
                "to_date": request.args.get("to_date", ""),
            },
            "core_activity": {
                "messages_sent": messages_sent,
                "unique_talkers": unique_talkers,
                "voice_hours": voice_hours,
                "unique_speakers": unique_speakers,
            },
            "growth_funnel": {
                "onboarding": {
                    "total_joins": total_joins,
                    "verified_users": period_verified,
                    "unverified_users": period_unverified,
                    "venue_users": None,
                },
                "retention": {
                    "verified_retention_rate": retention_rate,
                    "total_verified": total_verified_alltime,
                    "currently_in_server": in_server_count,
                    "verified_vs_unverified": {
                        "verified": total_verified_alltime,
                        "unverified": total_unverified_alltime,
                    },
                },
            },
            "channel_engagement": [
                {
                    **ch,
                    "voice_seconds": voice_by_channel.get(ch["channel_id"], {}).get("voice_seconds"),
                }
                for ch in channels
            ],
            "readership": {
                "monthly_visitors": None,
                "monthly_readers_per_channel": None,
                "weekly_readers_per_channel": None,
                "channel_followers": None,
            },
            "demographics": {
                "student_role": {
                    "First-Year": role_counts.get("First Year", 0),
                    "Transfer": role_counts.get("Transfer Student", 0),
                    "Graduate": role_counts.get("Graduate Student", 0),
                },
                "residency": {
                    "Arizona Resident": role_counts.get("Arizona Resident", 0),
                    "Out-of-State": role_counts.get("Out of State", 0),
                    "International": role_counts.get("International Student", 0),
                },
                "campus": {
                    "Tempe": role_counts.get("Tempe", 0),
                    "Downtown Phoenix": role_counts.get("Downtown Phoenix", 0),
                    "Polytechnic": role_counts.get("Polytechnic", 0),
                    "West Valley": role_counts.get("West Valley", 0),
                    "LA Center": role_counts.get("LA Center", 0),
                },
                "college": {name: role_counts.get(name, 0) for name in _COLLEGE_ROLES},
                "international_country": international_country,
            },
            "moderation": {
                "banned_users": banned_count,
                "period_bans": period_bans,
                "period_unbans": period_unbans,
                "support_tickets": None,
                "inappropriate_speech_incidents": None,
                "harassment_incidents": None,
                "spam_phishing_attempts": None,
            },
            "programs": {
                "gold_guides": {
                    "active_guides": active_guides,
                    "qna_sessions": total_posts,
                    "messages_sent": gg_total,
                    "contribution_distribution": guide_distribution,
                },
                "volunteers": {
                    "active_volunteers": None,
                    "messages_sent": None,
                    "avg_messages_per_volunteer": None,
                    "voice_hours": None,
                    "contribution_distribution": None,
                },
            },
            "forums": {
                "ask_asu_staff": {
                    "total_questions_answered": bot_answered + staff_answered,
                    "total_messages": total_posts,
                    "bot_answered": bot_answered,
                    "staff_answered": staff_answered,
                    "by_tag": by_tag,
                },
                "connect_by_major": {
                    "posts_created": connect_posts or None,
                    "messages_sent": None,
                    "activity_by_major": None,
                },
                "roommate_finder": {
                    "posts_by_campus": roommate_posts or None,
                },
                "all_forum_channels": [
                    {"channel_id": cid, "channel_name": cname or cid, "posts": posts}
                    for cid, cname, posts in forum_by_channel
                ],
            },
            "acquisition": {
                "source_medium": None,
                "users": None,
                "sessions": None,
                "pageviews": None,
                "bounce_rate": None,
                "session_duration": None,
            },
        }
    )


# ─── Salesforce Profile Cache ─────────────────────────────────────────────────

_sf_refresh_lock = _threading.Lock()
_sf_refresh_running = False
_sf_refresh_last: dict = {
    "started_at": None,
    "finished_at": None,
    "total": 0,
    "errors": 0,
    "error": None,
}


def _run_sf_refresh() -> None:
    """Background thread: async-fetch Salesforce profiles for all verified users."""
    global _sf_refresh_running
    import asyncio

    from utils.salesforce import async_bulk_fetch_profiles
    from utils.settings import CONFIG

    try:
        client_id = CONFIG.SALESFORCE_API_CLIENT_ID or ""
        client_secret = CONFIG.SALESFORCE_API_CLIENT_SECRET or ""
        if not client_id or not client_secret:
            _sf_refresh_last["error"] = "SALESFORCE_API_CLIENT_ID / SALESFORCE_API_CLIENT_SECRET not configured"
            return

        with session_scope() as db:
            rows = (
                db.query(User.asurite_id)
                .filter(User.verified == True, User.asurite_id.isnot(None))  # noqa: E712
                .all()
            )
        asuries = [r[0] for r in rows]
        _sf_refresh_last["total"] = len(asuries)

        profiles = asyncio.run(
            async_bulk_fetch_profiles(asuries, client_id, client_secret)
        )

        errors = 0
        now = datetime.utcnow()
        for p in profiles:
            try:
                with session_scope() as db:
                    existing = (
                        db.query(UserSalesforceProfile)
                        .filter(UserSalesforceProfile.asurite_id == p["asurite"])
                        .one_or_none()
                    )
                    if existing:
                        existing.country = p.get("country")
                        existing.state = p.get("state")
                        existing.is_international = bool(p.get("is_international"))
                        existing.has_opportunity = bool(p.get("has_opportunity"))
                        existing.fetch_error = p.get("error")
                        existing.fetched_at = now
                    else:
                        db.add(
                            UserSalesforceProfile(
                                asurite_id=p["asurite"],
                                country=p.get("country"),
                                state=p.get("state"),
                                is_international=bool(p.get("is_international")),
                                has_opportunity=bool(p.get("has_opportunity")),
                                fetch_error=p.get("error"),
                                fetched_at=now,
                            )
                        )
            except Exception:
                logger.exception("Error upserting Salesforce profile for %s", p.get("asurite"))
            if p.get("error"):
                errors += 1

        _sf_refresh_last["errors"] = errors
        _sf_refresh_last["finished_at"] = datetime.utcnow().isoformat()
    except Exception as exc:
        _sf_refresh_last["error"] = str(exc)
        _sf_refresh_last["finished_at"] = datetime.utcnow().isoformat()
        logger.exception("Salesforce refresh failed")
    finally:
        _sf_refresh_running = False


@admin_bp.route("/api/admin/salesforce/refresh", methods=["POST"])
@require_admin
def admin_salesforce_refresh():
    """Trigger async Salesforce profile refresh for all verified users."""
    global _sf_refresh_running

    with _sf_refresh_lock:
        if _sf_refresh_running:
            return jsonify({"status": "already_running", "last": _sf_refresh_last})
        _sf_refresh_running = True
        _sf_refresh_last["started_at"] = datetime.utcnow().isoformat()
        _sf_refresh_last["finished_at"] = None
        _sf_refresh_last["error"] = None
        _sf_refresh_last["errors"] = 0
        _sf_refresh_last["total"] = 0

    _threading.Thread(target=_run_sf_refresh, daemon=True).start()
    return jsonify({"status": "started"})


@admin_bp.route("/api/admin/salesforce/status", methods=["GET"])
@require_admin
def admin_salesforce_status():
    """Return Salesforce profile cache status."""
    with session_scope() as db:
        profiles_cached = db.query(UserSalesforceProfile).count()
        international_count = (
            db.query(UserSalesforceProfile)
            .filter(UserSalesforceProfile.is_international == True)  # noqa: E712
            .count()
        )
        error_count = (
            db.query(UserSalesforceProfile)
            .filter(UserSalesforceProfile.fetch_error.isnot(None))
            .count()
        )
        last_fetched_raw = (
            db.query(func.max(UserSalesforceProfile.fetched_at)).scalar()
        )

    last_fetched = (
        last_fetched_raw.replace(tzinfo=timezone.utc).astimezone(AZ_TZ).isoformat()
        if last_fetched_raw else None
    )

    return jsonify(
        {
            "profiles_cached": profiles_cached,
            "international_count": international_count,
            "error_count": error_count,
            "last_fetched": last_fetched,
            "refresh_running": _sf_refresh_running,
            "last_refresh": _sf_refresh_last,
        }
    )


# ─── Role Exceptions ──────────────────────────────────────────────────────────

def _serialize_exception(exc: UserRoleException) -> dict:
    return {
        "id": exc.id,
        "discord_user_id": exc.discord_user_id,
        "role_name": exc.role_name,
        "exception_type": exc.exception_type,
        "note": exc.note,
        "created_by": exc.created_by,
        "created_at": exc.created_at.isoformat() if exc.created_at else None,
    }


@admin_bp.route("/api/admin/exceptions/search")
@require_admin
def admin_exceptions_search():
    """Search guild members by display name / username (bot cache)."""
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify([])
    try:
        from asu_discord.api import search_members
        results = search_members(q, limit=25)
    except Exception:
        results = []
    return jsonify(results)


@admin_bp.route("/api/admin/exceptions/user/<discord_user_id>")
@require_admin
def admin_exceptions_for_user(discord_user_id: str):
    """Return existing exceptions + current DB roles for a user."""
    with session_scope() as db_session:
        exceptions = (
            db_session.query(UserRoleException)
            .filter(UserRoleException.discord_user_id == discord_user_id)
            .order_by(UserRoleException.created_at.desc())
            .all()
        )
        db_user = (
            db_session.query(User)
            .filter(User.discord_user_id == discord_user_id)
            .one_or_none()
        )
        db_roles = (
            db_session.query(UserRole)
            .filter(UserRole.user_id == db_user.id)
            .all()
            if db_user else []
        )

    try:
        from asu_discord.api import get_member_info
        member_info = get_member_info(discord_user_id)
    except Exception:
        member_info = None

    return jsonify({
        "discord_user_id": discord_user_id,
        "member_info": member_info,
        "db_user": {
            "asurite_id": db_user.asurite_id,
            "discord_username": db_user.discord_username,
            "verified": db_user.verified,
        } if db_user else None,
        "db_roles": [r.role_name for r in db_roles],
        "exceptions": [_serialize_exception(e) for e in exceptions],
    })


@admin_bp.route("/api/admin/exceptions/user/<discord_user_id>/pause", methods=["POST"])
@require_admin
def admin_exceptions_pause(discord_user_id: str):
    """Create a 'paused' exception for a role on a user."""
    data = request.get_json(silent=True) or {}
    role_name = (data.get("role_name") or "").strip()
    note = (data.get("note") or "").strip() or None

    from asu_discord.roles import ROLE_ID_MAP
    if role_name not in ROLE_ID_MAP:
        return jsonify({"error": f"Unknown role: {role_name!r}"}), 400

    admin_discord_id = (session.get("verification_state") or {}).get("discord_user_id")

    with session_scope() as db_session:
        # Upsert: remove any existing exception of either type for this role+user, then insert.
        db_session.query(UserRoleException).filter(
            UserRoleException.discord_user_id == discord_user_id,
            UserRoleException.role_name == role_name,
        ).delete()
        exc = UserRoleException(
            discord_user_id=discord_user_id,
            role_name=role_name,
            exception_type="paused",
            note=note,
            created_by=admin_discord_id,
        )
        db_session.add(exc)
        db_session.flush()
        result = _serialize_exception(exc)

    return jsonify(result), 201


@admin_bp.route("/api/admin/exceptions/user/<discord_user_id>/add", methods=["POST"])
@require_admin
def admin_exceptions_add(discord_user_id: str):
    """Create an 'added' exception for a role on a user (and immediately grant it)."""
    data = request.get_json(silent=True) or {}
    role_name = (data.get("role_name") or "").strip()
    note = (data.get("note") or "").strip() or None

    from asu_discord.roles import ROLE_ID_MAP
    if role_name not in ROLE_ID_MAP:
        return jsonify({"error": f"Unknown role: {role_name!r}"}), 400

    admin_discord_id = (session.get("verification_state") or {}).get("discord_user_id")

    # Try to assign the role immediately on Discord.
    try:
        from asu_discord.api import add_role_to_member, DiscordAPIError
        add_role_to_member(discord_user_id, role_name)
    except Exception as exc:
        logger.warning("Could not immediately add role %s to %s: %s", role_name, discord_user_id, exc)

    with session_scope() as db_session:
        db_session.query(UserRoleException).filter(
            UserRoleException.discord_user_id == discord_user_id,
            UserRoleException.role_name == role_name,
        ).delete()
        exc = UserRoleException(
            discord_user_id=discord_user_id,
            role_name=role_name,
            exception_type="added",
            note=note,
            created_by=admin_discord_id,
        )
        db_session.add(exc)
        db_session.flush()
        result = _serialize_exception(exc)

    return jsonify(result), 201


@admin_bp.route("/api/admin/exceptions/<int:exception_id>", methods=["DELETE"])
@require_admin
def admin_exceptions_delete(exception_id: int):
    """Delete a role exception (and optionally remove the Discord role for 'added' type)."""
    with session_scope() as db_session:
        exc = db_session.query(UserRoleException).filter(UserRoleException.id == exception_id).one_or_none()
        if exc is None:
            return jsonify({"error": "Not found"}), 404

        discord_user_id = exc.discord_user_id
        role_name = exc.role_name
        exc_type = exc.exception_type
        db_session.delete(exc)

    # For "added" exceptions: remove the role from Discord too.
    if exc_type == "added":
        try:
            from asu_discord.api import remove_role_from_member
            remove_role_from_member(discord_user_id, role_name)
        except Exception as e:
            logger.warning("Could not remove role %s from %s after deleting exception: %s", role_name, discord_user_id, e)

    return jsonify({"status": "deleted", "id": exception_id})


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

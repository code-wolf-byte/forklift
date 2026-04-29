from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable, List, Tuple
from zoneinfo import ZoneInfo

from clients.sftp_client import SftpClient
from utils.database import CronJobConfig, User, session_scope
from utils.settings import CONFIG, SFTP_CONFIG, SftpUploadConfig

AZ_TZ = ZoneInfo("America/Phoenix")
_SURVEY_URL = "https://enterpriseasu.qualtrics.com/jfe/form/SV_003BoaJdaKI7ZR4"

logger = logging.getLogger(__name__)

# Cron job call signature.
CronJob = Callable[..., None]


def _normalize_dt(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _get_last_run(job_name: str) -> datetime | None:
    """Read last_run_at (naive UTC) from the cron_job_config table."""
    with session_scope() as db_session:
        row = (
            db_session.query(CronJobConfig)
            .filter(CronJobConfig.job_name == job_name)
            .one_or_none()
        )
        return row.last_run_at if row else None


def _set_last_run(job_name: str, timestamp: datetime) -> None:
    """Persist last_run_at as naive UTC in the cron_job_config table."""
    naive_utc = timestamp.replace(tzinfo=None) if timestamp.tzinfo else timestamp
    with session_scope() as db_session:
        row = (
            db_session.query(CronJobConfig)
            .filter(CronJobConfig.job_name == job_name)
            .one_or_none()
        )
        if row is not None:
            row.last_run_at = naive_utc


def _fetch_verified_users(since: datetime | None) -> List[Tuple[str, datetime]]:
    since = _normalize_dt(since)
    with session_scope() as session:
        query = (
            session.query(User)
            .filter(User.verified.is_(True))
            .filter(User.verified_at.isnot(None))
        )
        if since is not None:
            query = query.filter(User.verified_at >= since)

        rows: List[Tuple[str, datetime]] = []
        for user in query.order_by(User.verified_at.asc()).all():
            verified_at = _normalize_dt(user.verified_at)
            if verified_at is None:
                continue
            rows.append((user.email, verified_at))
    return rows


def _build_csv(rows: Iterable[Tuple[str, datetime]], dt_column: str = "verified_at") -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["email", dt_column])
    for email, dt in rows:
        writer.writerow([email, dt.isoformat()])
    return buffer.getvalue().encode("utf-8")


def upload_emails_to_sftp() -> None:
    """Upload verified user emails to SFTP, only sending new rows since the last run."""
    if CONFIG.DEV_MODE:
        logger.info("FORKLIFT_DEV_MODE enabled; skipping SFTP upload")
        return

    if SFTP_CONFIG is None:
        logger.warning("SFTP configuration missing or disabled; skipping upload_emails_to_sftp")
        return

    job_name = "upload_emails_to_sftp"
    now = datetime.now(timezone.utc)
    last_run = _get_last_run(job_name)
    rows = _fetch_verified_users(last_run)

    if not rows:
        _set_last_run(job_name, now)
        logger.info("No verified users to upload; recorded last run at %s", now.isoformat())
        return

    csv_payload = _build_csv(rows)
    filename = f"{SFTP_CONFIG.filename_prefix}-{now.strftime('%Y%m%d')}.csv"
    remote_path = _upload_csv(SFTP_CONFIG, csv_payload, filename)

    _set_last_run(job_name, now)
    logger.info("Uploaded %d emails to SFTP at %s", len(rows), remote_path)


def _upload_csv(config: SftpUploadConfig, payload: bytes, filename: str) -> str:
    with SftpClient(config) as client:
        return client.upload_bytes(payload, config.remote_dir, filename)


_INCOMPLETE_VERIFICATION_FILENAME_PREFIX = "Devil2Devil_Incomplete"
_DEPARTED_FILENAME_PREFIX = "Devil2Devil_Left"


def _fetch_departed_users(since: datetime | None) -> List[Tuple[str, datetime]]:
    since = _normalize_dt(since)
    with session_scope() as session:
        query = (
            session.query(User)
            .filter(User.verified.is_(True))
            .filter(User.left_at.isnot(None))
        )
        if since is not None:
            query = query.filter(User.left_at >= since)

        rows: List[Tuple[str, datetime]] = []
        for user in query.order_by(User.left_at.asc()).all():
            left_at = _normalize_dt(user.left_at)
            if left_at is None:
                continue
            rows.append((user.email, left_at))
    return rows


def _fetch_incomplete_verification_users(since: datetime | None, now: datetime) -> List[Tuple[str, datetime]]:
    """Return users who completed CAS (step 1) but never linked Discord (step 2).

    Also stamps incomplete_sftp_exported_at on each fetched user so we can later
    track how many of them eventually verified.
    """
    since = _normalize_dt(since)
    now_naive = now.replace(tzinfo=None) if now.tzinfo else now
    with session_scope() as session:
        query = (
            session.query(User)
            .filter(User.email != "")
            .filter(User.verified.is_(False))
            .filter(User.discord_user_id.is_(None))
        )
        if since is not None:
            query = query.filter(User.created_at >= since)

        rows: List[Tuple[str, datetime]] = []
        for user in query.order_by(User.created_at.asc()).all():
            created_at = _normalize_dt(user.created_at)
            if created_at is None:
                continue
            rows.append((user.email, created_at))
            user.incomplete_sftp_exported_at = now_naive
    return rows


def upload_incomplete_verifications_to_sftp() -> None:
    """Upload emails of users who completed SSO but never linked Discord, incremental since last run."""
    if CONFIG.DEV_MODE:
        logger.info("FORKLIFT_DEV_MODE enabled; skipping SFTP upload")
        return

    if SFTP_CONFIG is None:
        logger.warning("SFTP configuration missing or disabled; skipping upload_incomplete_verifications_to_sftp")
        return

    job_name = "upload_incomplete_verifications_to_sftp"
    now = datetime.now(timezone.utc)
    last_run = _get_last_run(job_name)
    rows = _fetch_incomplete_verification_users(last_run, now)

    if not rows:
        _set_last_run(job_name, now)
        logger.info("No incomplete verifications to upload; recorded last run at %s", now.isoformat())
        return

    csv_payload = _build_csv(rows, dt_column="sso_completed_at")
    filename = f"{_INCOMPLETE_VERIFICATION_FILENAME_PREFIX}-{now.strftime('%Y%m%d')}.csv"
    remote_path = _upload_csv(SFTP_CONFIG, csv_payload, filename)

    _set_last_run(job_name, now)
    logger.info("Uploaded %d incomplete verification emails to SFTP at %s", len(rows), remote_path)


def upload_departed_to_sftp() -> None:
    """Upload departed verified user emails to SFTP, all on first run then incremental."""
    if CONFIG.DEV_MODE:
        logger.info("FORKLIFT_DEV_MODE enabled; skipping SFTP upload")
        return

    if SFTP_CONFIG is None:
        logger.warning("SFTP configuration missing or disabled; skipping upload_departed_to_sftp")
        return

    job_name = "upload_departed_to_sftp"
    now = datetime.now(timezone.utc)
    last_run = _get_last_run(job_name)
    rows = _fetch_departed_users(last_run)

    if not rows:
        _set_last_run(job_name, now)
        logger.info("No departed users to upload; recorded last run at %s", now.isoformat())
        return

    csv_payload = _build_csv(rows, dt_column="left_at")
    filename = f"{_DEPARTED_FILENAME_PREFIX}-{now.strftime('%Y%m%d')}.csv"
    remote_path = _upload_csv(SFTP_CONFIG, csv_payload, filename)

    _set_last_run(job_name, now)
    logger.info("Uploaded %d departed users to SFTP at %s", len(rows), remote_path)


def send_survey_messages() -> None:
    """Ping users verified exactly 3 weeks ago who are still in the server."""
    job_name = "send_survey_messages"

    with session_scope() as db_session:
        cfg = (
            db_session.query(CronJobConfig)
            .filter(CronJobConfig.job_name == job_name)
            .one_or_none()
        )
        channel_id = cfg.channel_id if cfg else None

    if not channel_id:
        logger.warning("send_survey_messages: no channel configured; skipping")
        return

    # Build a UTC window covering the full AZ day that was exactly 21 days ago.
    now_az = datetime.now(AZ_TZ)
    target_az_date = (now_az - timedelta(days=21)).date()
    window_start = (
        datetime(target_az_date.year, target_az_date.month, target_az_date.day, 0, 0, 0, tzinfo=AZ_TZ)
        .astimezone(timezone.utc)
        .replace(tzinfo=None)
    )
    window_end = (
        datetime(target_az_date.year, target_az_date.month, target_az_date.day, 23, 59, 59, tzinfo=AZ_TZ)
        .astimezone(timezone.utc)
        .replace(tzinfo=None)
    )

    with session_scope() as db_session:
        users = (
            db_session.query(User)
            .filter(User.verified.is_(True))
            .filter(User.verified_at >= window_start)
            .filter(User.verified_at <= window_end)
            .filter(User.left_at.is_(None))
            .filter(User.discord_user_id.isnot(None))
            .all()
        )
        discord_ids = [u.discord_user_id for u in users]

    now = datetime.now(timezone.utc)

    if not discord_ids:
        logger.info("send_survey_messages: no users verified 3 weeks ago still in server")
        _set_last_run(job_name, now)
        return

    from asu_discord.api import DiscordAPIError, send_channel_message

    failed = 0
    for discord_id in discord_ids:
        message = (
            f"<@{discord_id}> Hey! It's been 3 weeks since you joined Devil2Devil. "
            "We'd love to hear about your experience so far — "
            f"please take a moment to fill out [our survey](<{_SURVEY_URL}>)!"
        )
        try:
            send_channel_message(channel_id, message)
        except DiscordAPIError as exc:
            logger.error("send_survey_messages: failed to ping user %s: %s", discord_id, exc)
            failed += 1

    if failed:
        raise RuntimeError(f"send_survey_messages: {failed}/{len(discord_ids)} messages failed")

    _set_last_run(job_name, now)
    logger.info("send_survey_messages: sent survey pings to %d users in channel %s", len(discord_ids), channel_id)


def refresh_salesforce_roles() -> None:
    """Refresh Discord roles for all verified users based on current Salesforce data."""
    job_name = "refresh_salesforce_roles"

    if CONFIG.DEV_MODE:
        logger.info("FORKLIFT_DEV_MODE enabled; skipping Salesforce role refresh")
        return

    from asu_discord.api import DiscordAPIError, refresh_roles_from_profile
    from asu_discord.salesforce import get_student_profile

    now = datetime.now(timezone.utc)

    with session_scope() as db_session:
        users = (
            db_session.query(User)
            .filter(User.verified.is_(True))
            .filter(User.banned.is_(False))
            .filter(User.asurite_id.isnot(None))
            .filter(User.discord_user_id.isnot(None))
            .all()
        )
        user_data = [(u.asurite_id, u.discord_user_id) for u in users]

    if not user_data:
        logger.info("refresh_salesforce_roles: no verified users to process")
        _set_last_run(job_name, now)
        return

    logger.info("refresh_salesforce_roles: processing %d users", len(user_data))

    skipped = 0
    failed = 0
    refreshed = 0

    for asurite_id, discord_user_id in user_data:
        asurite = asurite_id.strip()
        if asurite.lower().endswith("@asu.edu"):
            asurite = asurite[: -len("@asu.edu")]

        try:
            profile = get_student_profile(asurite)
        except Exception as exc:
            logger.warning(
                "refresh_salesforce_roles: Salesforce lookup failed for %s: %s",
                asurite,
                exc,
            )
            skipped += 1
            continue

        if profile is None:
            logger.info("refresh_salesforce_roles: skipping %s: no profile returned", asurite)
            skipped += 1
            continue

        try:
            refresh_roles_from_profile(discord_user_id, profile)
            refreshed += 1
        except DiscordAPIError as exc:
            logger.error(
                "refresh_salesforce_roles: failed for %s (Discord ID %s): %s",
                asurite,
                discord_user_id,
                exc,
            )
            failed += 1

    _set_last_run(job_name, now)
    logger.info(
        "refresh_salesforce_roles: done. refreshed=%d skipped=%d failed=%d",
        refreshed,
        skipped,
        failed,
    )

    if failed:
        raise RuntimeError(
            f"refresh_salesforce_roles: {failed}/{len(user_data)} users failed role refresh"
        )


AVAILABLE_JOBS: dict[str, CronJob] = {
    "upload_emails_to_sftp": upload_emails_to_sftp,
    "upload_incomplete_verifications_to_sftp": upload_incomplete_verifications_to_sftp,
    "upload_departed_to_sftp": upload_departed_to_sftp,
    "send_survey_messages": send_survey_messages,
    "refresh_salesforce_roles": refresh_salesforce_roles,
}

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
_SURVEY_BATCH_SIZE = 50  # max mentions per Discord message

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

    survey_text = (
        "Hey! It's been 3 weeks since you joined Devil2Devil. "
        "We'd love to hear about your experience so far — "
        "please take a moment to fill out our survey here: "
    )

    # Send in batches to stay within Discord's 2000-character message limit.
    for i in range(0, len(discord_ids), _SURVEY_BATCH_SIZE):
        batch = discord_ids[i : i + _SURVEY_BATCH_SIZE]
        mentions = " ".join(f"<@{uid}>" for uid in batch)
        try:
            send_channel_message(channel_id, f"{mentions}\n\n{survey_text}")
        except DiscordAPIError as exc:
            logger.error("send_survey_messages: failed to send batch %d: %s", i // _SURVEY_BATCH_SIZE, exc)
            raise

    _set_last_run(job_name, now)
    logger.info("send_survey_messages: sent survey pings to %d users in channel %s", len(discord_ids), channel_id)


AVAILABLE_JOBS: dict[str, CronJob] = {
    "upload_emails_to_sftp": upload_emails_to_sftp,
    "upload_departed_to_sftp": upload_departed_to_sftp,
    "send_survey_messages": send_survey_messages,
}

from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, List, Tuple

from clients.sftp_client import SftpClient
from utils.database import User, session_scope
from utils.settings import CONFIG, SFTP_CONFIG, SftpUploadConfig

logger = logging.getLogger(__name__)

# Cron job call signature.
CronJob = Callable[..., None]


def _normalize_dt(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _load_last_run(state_path: Path) -> datetime | None:
    if not state_path.exists():
        return None
    try:
        raw = state_path.read_text(encoding="utf-8").strip()
        return datetime.fromisoformat(raw)
    except Exception:
        logger.warning("Could not parse last SFTP upload timestamp; treating as first run")
        return None


def _save_last_run(state_path: Path, timestamp: datetime) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(timestamp.isoformat(), encoding="utf-8")


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

    now = datetime.now(timezone.utc)
    last_run = _load_last_run(SFTP_CONFIG.state_path)
    rows = _fetch_verified_users(last_run)

    if not rows:
        _save_last_run(SFTP_CONFIG.state_path, now)
        logger.info("No verified users to upload; recorded last run at %s", now.isoformat())
        return

    csv_payload = _build_csv(rows)
    filename = f"{SFTP_CONFIG.filename_prefix}-{now.strftime('%Y%m%d')}.csv"
    remote_path = _upload_csv(SFTP_CONFIG, csv_payload, filename)

    _save_last_run(SFTP_CONFIG.state_path, now)
    logger.info("Uploaded %d emails to SFTP at %s", len(rows), remote_path)


def _upload_csv(config: SftpUploadConfig, payload: bytes, filename: str) -> str:
    with SftpClient(config) as client:
        return client.upload_bytes(payload, config.remote_dir, filename)


_DEPARTED_STATE_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "upload_departed_to_sftp.state"
)
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

    now = datetime.now(timezone.utc)
    last_run = _load_last_run(_DEPARTED_STATE_PATH)
    rows = _fetch_departed_users(last_run)

    if not rows:
        _save_last_run(_DEPARTED_STATE_PATH, now)
        logger.info("No departed users to upload; recorded last run at %s", now.isoformat())
        return

    csv_payload = _build_csv(rows, dt_column="left_at")
    filename = f"{_DEPARTED_FILENAME_PREFIX}-{now.strftime('%Y%m%d')}.csv"
    remote_path = _upload_csv(SFTP_CONFIG, csv_payload, filename)

    _save_last_run(_DEPARTED_STATE_PATH, now)
    logger.info("Uploaded %d departed users to SFTP at %s", len(rows), remote_path)


AVAILABLE_JOBS: dict[str, CronJob] = {
    "upload_emails_to_sftp": upload_emails_to_sftp,
    "upload_departed_to_sftp": upload_departed_to_sftp,
}

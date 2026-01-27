"""Service for writing verified user departures to Google Sheets."""

from __future__ import annotations

import logging
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials

from utils.database import User, session_scope
from utils.settings import GOOGLE_SHEETS_CONFIG

logger = logging.getLogger(__name__)

_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
]


def _get_client() -> gspread.Client | None:
    """Authenticate and return a gspread client, or None if not configured."""
    if GOOGLE_SHEETS_CONFIG is None:
        return None

    credentials = Credentials.from_service_account_file(
        str(GOOGLE_SHEETS_CONFIG.credentials_file),
        scopes=_SCOPES,
    )
    return gspread.authorize(credentials)


def write_user_left(email: str, left_at: datetime) -> bool:
    """
    Append a row with the user's email and left_at timestamp to the
    configured Google Sheet.

    Returns True if the row was written successfully, False otherwise.
    """
    if GOOGLE_SHEETS_CONFIG is None:
        logger.debug("Google Sheets integration not configured; skipping write")
        return False

    try:
        client = _get_client()
        if client is None:
            return False

        spreadsheet = client.open_by_key(GOOGLE_SHEETS_CONFIG.spreadsheet_id)
        worksheet = spreadsheet.worksheet(GOOGLE_SHEETS_CONFIG.worksheet_name)

        row = [email, left_at.strftime("%Y-%m-%d %H:%M:%S UTC")]
        worksheet.append_row(row, value_input_option="USER_ENTERED")

        logger.info(
            "Wrote departure record to Google Sheets for %s at %s",
            email,
            left_at,
        )
        return True

    except Exception:
        logger.exception("Failed to write departure record to Google Sheets")
        return False


def sync_departed_users() -> int:
    """
    Compare verified users with left_at in the database against rows
    already in the Google Sheet, and write any missing entries.

    Returns the number of new rows written.
    """
    if GOOGLE_SHEETS_CONFIG is None:
        logger.debug("Google Sheets integration not configured; skipping sync")
        return 0

    try:
        client = _get_client()
        if client is None:
            return 0

        spreadsheet = client.open_by_key(GOOGLE_SHEETS_CONFIG.spreadsheet_id)
        worksheet = spreadsheet.worksheet(GOOGLE_SHEETS_CONFIG.worksheet_name)

        existing_emails: set[str] = set()
        for row in worksheet.get_all_values():
            if row:
                existing_emails.add(row[0].strip().lower())

        with session_scope() as session:
            departed_users = (
                session.query(User)
                .filter(
                    User.verified.is_(True),
                    User.email.isnot(None),
                    User.left_at.isnot(None),
                )
                .all()
            )

            rows_to_write = []
            for user in departed_users:
                if user.email.strip().lower() not in existing_emails:
                    rows_to_write.append([
                        user.email,
                        user.left_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
                    ])

        if rows_to_write:
            worksheet.append_rows(rows_to_write, value_input_option="USER_ENTERED")
            logger.info(
                "Synced %d departed user(s) to Google Sheets", len(rows_to_write)
            )

        return len(rows_to_write)

    except Exception:
        logger.exception("Failed to sync departed users to Google Sheets")
        return 0

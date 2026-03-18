from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    inspect,
    text,
)
from sqlalchemy.orm import Session, declarative_base, relationship, scoped_session, sessionmaker

from utils.settings import CONFIG

engine = create_engine(CONFIG.DATABASE_URL, future=True)
SessionLocal = scoped_session(
    sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)
)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    asurite_id = Column(String(64), unique=True, index=True, nullable=False)
    email = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
    affiliations = Column(String(255), nullable=True)
    saml_session_index = Column(String(128), nullable=True)
    saml_attributes = Column(Text, nullable=True)
    discord_user_id = Column(String(64), unique=True, index=True, nullable=True)
    discord_username = Column(String(255), nullable=True)
    discord_global_name = Column(String(255), nullable=True)
    discord_avatar = Column(String(255), nullable=True)
    verified = Column(Boolean, default=False, nullable=False)
    verified_at = Column(DateTime, nullable=True)
    joined_at = Column(DateTime, nullable=True)
    left_at = Column(DateTime, nullable=True)
    banned = Column(Boolean, default=False, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    def _has_affiliation(self, target: str) -> bool:
        if not self.affiliations:
            return False
        normalized_target = target.lower()
        return any(
            normalized_target == affiliation.strip().lower()
            for affiliation in self.affiliations.split(",")
            if affiliation
        )

    @property
    def is_member(self) -> bool:
        return self._has_affiliation("member@asu.edu")

    @property
    def is_student(self) -> bool:
        return self._has_affiliation("student@asu.edu")

    @property
    def is_employee(self) -> bool:
        return self._has_affiliation("employee@asu.edu")


class UserRole(Base):
    """Tracks Discord roles assigned to users from Salesforce data."""

    __tablename__ = "user_roles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role_name = Column(String(128), nullable=False, index=True)
    role_discord_id = Column(BigInteger, nullable=False)
    source = Column(String(32), default="verification", nullable=False)
    assigned_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    user = relationship("User", backref="roles")


class QnaPost(Base):
    __tablename__ = "qna_posts"

    id = Column(Integer, primary_key=True, index=True)
    guild_id = Column(String(64), nullable=True)
    channel_id = Column(String(64), nullable=False)
    thread_id = Column(String(64), unique=True, index=True, nullable=False)
    owner_id = Column(String(64), nullable=True)
    title = Column(String(255), nullable=True)
    assistant_message_id = Column(String(64), nullable=True)
    question = Column(Text, nullable=True)
    answer = Column(Text, nullable=True)
    status = Column(String(32), default="pending", nullable=False)
    last_feedback_user_id = Column(String(64), nullable=True)
    last_feedback_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class QnaModule(Base):
    __tablename__ = "qna_modules"

    id = Column(Integer, primary_key=True, index=True)
    guild_id = Column(String(64), unique=True, nullable=False)
    enabled = Column(Boolean, default=False, nullable=False)
    commands = Column(Text, nullable=True)
    config = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class CronJobConfig(Base):
    """Per-job schedule configuration and last-run tracking."""

    __tablename__ = "cron_job_config"

    id = Column(Integer, primary_key=True)
    job_name = Column(String(128), unique=True, nullable=False, index=True)
    display_name = Column(String(255), nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    schedule_hour = Column(Integer, default=0, nullable=False)    # 0–23 in AZ time
    schedule_minute = Column(Integer, default=0, nullable=False)  # 0–59
    last_run_at = Column(DateTime, nullable=True)                 # naive UTC
    channel_id = Column(String(64), nullable=True)               # Discord channel snowflake
    survey_url = Column(String(2048), nullable=True)             # URL sent in survey messages
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class MessageLog(Base):
    """One row per Discord message — metadata + content."""

    __tablename__ = "message_logs"

    id = Column(Integer, primary_key=True)
    message_id = Column(String(64), unique=True, nullable=False, index=True)
    channel_id = Column(String(64), nullable=False, index=True)
    channel_name = Column(String(255), nullable=True)
    guild_id = Column(String(64), nullable=False, index=True)
    discord_user_id = Column(String(64), nullable=False, index=True)
    content = Column(Text, nullable=True)
    sent_at = Column(DateTime, nullable=False, index=True)  # naive UTC
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class MessageBackfill(Base):
    """Per-channel backfill progress tracking."""

    __tablename__ = "message_backfill"

    id = Column(Integer, primary_key=True)
    channel_id = Column(String(64), unique=True, nullable=False, index=True)
    channel_name = Column(String(255), nullable=True)
    status = Column(String(32), default="pending", nullable=False)  # pending/running/done/failed
    messages_fetched = Column(Integer, default=0, nullable=False)
    oldest_fetched_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    error = Column(Text, nullable=True)


# Default rows seeded on first startup.
_CRON_JOB_DEFAULTS = [
    {
        "job_name": "upload_emails_to_sftp",
        "display_name": "Upload Verified Emails to SFTP",
    },
    {
        "job_name": "upload_incomplete_verifications_to_sftp",
        "display_name": "Upload Incomplete Verifications to SFTP",
    },
    {
        "job_name": "upload_departed_to_sftp",
        "display_name": "Upload Departed Users to SFTP",
    },
    {
        "job_name": "send_survey_messages",
        "display_name": "Send Survey Messages",
        "schedule_hour": 11,
        "schedule_minute": 0,
    },
    {
        "job_name": "refresh_salesforce_roles",
        "display_name": "Refresh Salesforce Roles",
        "schedule_hour": 3,
        "schedule_minute": 0,
    },
]

# Legacy state-file paths — read once during migration, then ignored.
_LEGACY_STATE_FILES: dict[str, Path] = {
    "upload_emails_to_sftp": Path(__file__).resolve().parent.parent
    / "data"
    / "upload_emails_to_sftp.state",
    "upload_departed_to_sftp": Path(__file__).resolve().parent.parent
    / "data"
    / "upload_departed_to_sftp.state",
}


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_user_columns()
    _ensure_cron_job_config_columns()
    _ensure_message_log_columns()
    _seed_cron_job_config()


def _ensure_message_log_columns() -> None:
    """Add columns to message_logs introduced after the initial schema."""
    inspector = inspect(engine)
    if not inspector.has_table(MessageLog.__tablename__):
        return

    columns = {col["name"] for col in inspector.get_columns(MessageLog.__tablename__)}

    if "content" not in columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE message_logs ADD COLUMN content TEXT"))


def _ensure_cron_job_config_columns() -> None:
    """Add columns to cron_job_config that were introduced after the initial schema."""
    inspector = inspect(engine)
    if not inspector.has_table(CronJobConfig.__tablename__):
        return

    columns = {col["name"] for col in inspector.get_columns(CronJobConfig.__tablename__)}

    if "channel_id" not in columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE cron_job_config ADD COLUMN channel_id VARCHAR(64)"))

    if "survey_url" not in columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE cron_job_config ADD COLUMN survey_url VARCHAR(2048)"))


def _ensure_user_columns() -> None:
    inspector = inspect(engine)
    if not inspector.has_table(User.__tablename__):
        return

    columns = {col["name"] for col in inspector.get_columns(User.__tablename__)}

    ddl_statements = []
    if "banned" not in columns:
        ddl = "ALTER TABLE users ADD COLUMN banned BOOLEAN NOT NULL DEFAULT 0"
        if engine.dialect.name == "postgresql":
            ddl = "ALTER TABLE users ADD COLUMN IF NOT EXISTS banned BOOLEAN NOT NULL DEFAULT FALSE"
        ddl_statements.append(ddl)

    if "joined_at" not in columns:
        ddl_statements.append("ALTER TABLE users ADD COLUMN joined_at DATETIME")
    if "left_at" not in columns:
        ddl_statements.append("ALTER TABLE users ADD COLUMN left_at DATETIME")
    if "is_admin" not in columns:
        ddl = "ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT 0"
        if engine.dialect.name == "postgresql":
            ddl = "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT FALSE"
        ddl_statements.append(ddl)

    if not ddl_statements:
        return

    with engine.begin() as conn:
        for ddl in ddl_statements:
            conn.execute(text(ddl))


def _seed_cron_job_config() -> None:
    """Insert default CronJobConfig rows; migrate last_run from legacy state files."""
    with session_scope() as db_session:
        for defaults in _CRON_JOB_DEFAULTS:
            existing = (
                db_session.query(CronJobConfig)
                .filter(CronJobConfig.job_name == defaults["job_name"])
                .one_or_none()
            )
            if existing is not None:
                continue

            row = CronJobConfig(**defaults)

            # One-time migration: read last_run from legacy state file if present.
            legacy_path = _LEGACY_STATE_FILES.get(defaults["job_name"])
            if legacy_path and legacy_path.exists():
                try:
                    raw = legacy_path.read_text(encoding="utf-8").strip()
                    parsed = datetime.fromisoformat(raw)
                    # Normalize to naive UTC for DB storage.
                    if parsed.tzinfo is not None:
                        from datetime import timezone as _tz
                        parsed = parsed.astimezone(_tz.utc).replace(tzinfo=None)
                    row.last_run_at = parsed
                except Exception:
                    pass

            db_session.add(row)


def get_session() -> Session:
    return SessionLocal()


@contextmanager
def session_scope() -> Iterator[Session]:
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def save_user_roles(
    user_id: int,
    roles: list[tuple[str, int]],
    source: str = "verification",
) -> None:
    """
    Save or update roles for a user.

    Args:
        user_id: The database user ID (not Discord ID).
        roles: List of (role_name, role_discord_id) tuples.
        source: Source of role assignment (e.g., "verification", "salesforce_sync", "manual").
    """
    with session_scope() as session:
        # Delete existing roles for this user
        session.query(UserRole).filter(UserRole.user_id == user_id).delete()

        # Add new roles
        for role_name, role_discord_id in roles:
            role = UserRole(
                user_id=user_id,
                role_name=role_name,
                role_discord_id=role_discord_id,
                source=source,
            )
            session.add(role)


def get_user_roles(user_id: int) -> list[UserRole]:
    """Get all roles for a user."""
    with session_scope() as session:
        return session.query(UserRole).filter(UserRole.user_id == user_id).all()


def get_user_by_discord_id(discord_id: str) -> User | None:
    """Get a user by their Discord ID."""
    with session_scope() as session:
        return session.query(User).filter(User.discord_user_id == discord_id).first()

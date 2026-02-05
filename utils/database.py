from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
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


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_user_columns()


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

    if not ddl_statements:
        return

    with engine.begin() as conn:
        for ddl in ddl_statements:
            conn.execute(text(ddl))


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

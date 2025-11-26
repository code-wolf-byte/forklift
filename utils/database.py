from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from typing import Iterator

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    Text,
    create_engine,
    inspect,
    text,
)
from sqlalchemy.orm import Session, declarative_base, scoped_session, sessionmaker

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
    _ensure_banned_column()


def _ensure_banned_column() -> None:
    inspector = inspect(engine)
    if not inspector.has_table(User.__tablename__):
        return

    columns = {col["name"] for col in inspector.get_columns(User.__tablename__)}
    if "banned" in columns:
        return

    ddl = "ALTER TABLE users ADD COLUMN banned BOOLEAN NOT NULL DEFAULT 0"
    if engine.dialect.name == "postgresql":
        ddl = "ALTER TABLE users ADD COLUMN IF NOT EXISTS banned BOOLEAN NOT NULL DEFAULT FALSE"

    with engine.begin() as conn:
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

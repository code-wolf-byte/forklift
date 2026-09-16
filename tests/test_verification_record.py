"""Tests for the /verify email recording path."""

from __future__ import annotations

from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from asu_discord.cogs import verification
from asu_discord.cogs.verification import _asurite_from_email, _record_verification
from utils.database import Base, User


@pytest.fixture
def session(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, expire_on_commit=False)()

    @contextmanager
    def fake_scope():
        yield db
        db.commit()

    monkeypatch.setattr(verification, "session_scope", fake_scope)
    yield db
    db.close()


@pytest.mark.parametrize(
    "email,expected",
    [
        ("tupreti@asu.edu", "tupreti"),
        ("TUpreti@ASU.EDU", "tupreti"),
        ("tupreti@sub.asu.edu", "tupreti"),
        ("tupreti@notasu.edu", None),
        ("tupreti@gmail.com", None),
        ("@asu.edu", None),
        ("nonsense", None),
    ],
)
def test_asurite_from_email(email, expected):
    assert _asurite_from_email(email) == expected


def test_creates_record_from_asu_email(session):
    assert _record_verification("42", "tupreti@asu.edu") == "tupreti"

    user = session.query(User).one()
    assert (user.asurite_id, user.email, user.discord_user_id) == ("tupreti", "tupreti@asu.edu", "42")
    assert user.verified is True
    assert user.verified_at is not None


def test_updates_existing_record_matched_by_asurite(session):
    session.add(User(asurite_id="tupreti", email="old@asu.edu", verified=False))
    session.commit()

    assert _record_verification("42", "tupreti@asu.edu") == "tupreti"

    user = session.query(User).one()  # updated in place, not duplicated
    assert (user.email, user.discord_user_id, user.verified) == ("tupreti@asu.edu", "42", True)


def test_updates_existing_record_matched_by_discord_id_without_email(session):
    session.add(User(asurite_id="tupreti", email="tupreti@asu.edu", discord_user_id="42", verified=False))
    session.commit()

    assert _record_verification("42", "") == "tupreti"
    assert session.query(User).one().verified is True


def test_non_asu_email_updates_existing_record_but_creates_none(session):
    assert _record_verification("42", "someone@gmail.com") is None
    assert session.query(User).count() == 0

    session.add(User(asurite_id="tupreti", email="tupreti@asu.edu", discord_user_id="42"))
    session.commit()

    assert _record_verification("42", "someone@gmail.com") == "tupreti"
    assert session.query(User).one().email == "someone@gmail.com"

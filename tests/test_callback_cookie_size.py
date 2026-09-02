"""The Discord callback must not overflow the session cookie.

Regression guard for the production 502s: nginx logged "upstream sent too big
header" on /auth/discord/callback for students with long Salesforce histories.
StudentProfile.opportunities is unbounded (one real profile had 39 entries ->
112KB of JSON -> 11.8KB Set-Cookie even after itsdangerous' zlib pass), which
blows past nginx's 4K default proxy_buffer_size and the browser's 4K per-cookie
limit. Nothing reads the profile back out of the session, so it must stay out.
"""

from __future__ import annotations

import random
import string
from contextlib import contextmanager

import pytest
from flask import Flask
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from asu_discord.models import DiscordProfile, DiscordTokenData
from routes import discord as discord_routes
from tests.conftest import make_opportunity, make_student_profile
from utils.database import Base, User

# nginx's default proxy_buffer_size, and the browser's per-cookie limit.
HEADER_LIMIT = 4096


@pytest.fixture
def client(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    db.add(User(id=1, asurite_id="apuliroj", email="a@asu.edu"))
    db.commit()

    @contextmanager
    def fake_scope():
        yield db
        db.commit()

    # A long-tenured student: many opportunities, each carrying the extra Salesforce
    # fields that `model_config = {"extra": "allow"}` lets through. Salesforce ids are
    # high-entropy, so seed them from a fixed PRNG -- reusing one literal id across
    # rows would let zlib crush the cookie and hide the very overflow being tested.
    rng = random.Random(0)

    def sf_id(prefix: str) -> str:
        body = "".join(rng.choices(string.ascii_letters + string.digits, k=12))
        return f"{prefix}{body}AAZ"

    fat_profile = make_student_profile(
        asurite="apuliroj",
        opportunities=[
            make_opportunity(
                termCode=f"21{n:02d}",
                opportunityId=sf_id("006d"),
                accountId=sf_id("001d"),
                contactId=sf_id("003d"),
                termId=sf_id("a0Jd"),
                recordTypeId=sf_id("012d"),
                ownerId=sf_id("005d"),
                accountName="Archana Vannela",
                contactName="Archana Vannela",
                ownerEmail=f"advisor{n}@asu.edu",
                ownerName=f"Advisor Number {n}",
                recordTypeName="Undergraduate Prospect",
                academicPlanName=f"Program Number {n}",
                createdDate=f"20{15 + n % 10}-02-24T15:38:12.000+0000",
            )
            for n in range(40)
        ],
    )

    monkeypatch.setattr(discord_routes, "session_scope", fake_scope)
    monkeypatch.setattr(discord_routes, "exchange_code_for_token",
                        lambda code: DiscordTokenData(access_token="tok"))
    monkeypatch.setattr(discord_routes, "fetch_user_profile",
                        lambda tok: DiscordProfile(id="1308518536712421469", username="someuser"))
    monkeypatch.setattr(discord_routes, "get_student_profile", lambda asurite: fat_profile)
    monkeypatch.setattr(discord_routes, "assign_verified_role", lambda *a, **k: None)
    monkeypatch.setattr(discord_routes, "assign_roles_from_profile", lambda *a, **k: None)
    monkeypatch.setattr(discord_routes, "remove_roles_from_profile", lambda *a, **k: None)
    monkeypatch.setattr(discord_routes, "check_member_has_any_role", lambda uid, roles: False)
    monkeypatch.setattr("utils.salesforce.cache_sf_profile", lambda *a, **k: None)
    monkeypatch.setattr(discord_routes.CONFIG, "CAS_ENABLED", True)
    monkeypatch.setattr(discord_routes.CONFIG, "DISCORD_SUCCESS_REDIRECT", "/verified")
    if discord_routes.DISCORD_CONFIG is None:
        monkeypatch.setattr(discord_routes, "DISCORD_CONFIG", object())

    app = Flask(__name__)
    app.secret_key = "test-secret-key-for-signing-only"
    app.config.update(SESSION_COOKIE_NAME="forklift_session", TESTING=True)
    app.register_blueprint(discord_routes.discord_bp)

    @app.route("/verified")
    def verified():
        return "ok"

    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess["discord_oauth_state"] = "state-token"
            sess["verification_state"] = {
                "cas_complete": True, "user_id": 1, "asurite": "apuliroj",
                "email": "a@asu.edu",
            }
        yield c

    db.close()


def test_callback_set_cookie_fits_in_nginx_buffer(client):
    resp = client.get("/auth/discord/callback?code=abc&state=state-token")
    assert resp.status_code == 302, resp.get_data(as_text=True)

    cookies = [v for k, v in resp.headers if k == "Set-Cookie"]
    assert cookies, "callback set no session cookie"

    for value in cookies:
        header_bytes = len(f"Set-Cookie: {value}".encode())
        assert header_bytes <= HEADER_LIMIT, (
            f"session cookie is {header_bytes} bytes, over the {HEADER_LIMIT}-byte "
            "nginx proxy_buffer_size -> nginx answers 502 on the callback"
        )


def test_salesforce_profile_stays_out_of_the_session(client):
    client.get("/auth/discord/callback?code=abc&state=state-token")

    with client.session_transaction() as sess:
        assert "student_profile" not in sess
        assert "student_profile" not in sess["verification_state"]
        # the small, bounded fields the UI actually reads survive
        assert sess["verification_state"]["verified"] is True
        assert sess["verification_state"]["discord_username"] == "someuser"

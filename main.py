import os
from datetime import datetime

from flask import Flask, redirect, render_template, session, url_for

from routes.discord import discord_bp
from utils.database import init_db
from utils.metadata import ensure_metadata_on_startup, start_metadata_scheduler
from utils.settings import CONFIG, DISCORD_CONFIG

if CONFIG.SAML_ENABLED:
    from routes.saml import saml_bp
else:  # pragma: no cover - SAML disabled
    saml_bp = None  # type: ignore[assignment]


def _should_start_metadata_scheduler() -> bool:
    flag = os.environ.get("WERKZEUG_RUN_MAIN")
    return flag is None or flag == "true"


if CONFIG.SAML_ENABLED:
    ensure_metadata_on_startup()
init_db()
if CONFIG.SAML_ENABLED and _should_start_metadata_scheduler():
    start_metadata_scheduler()

app = Flask(__name__)
app.secret_key = CONFIG.SECRET_KEY
app.config["SESSION_COOKIE_NAME"] = CONFIG.SESSION_COOKIE_NAME
app.config["SESSION_COOKIE_SECURE"] = CONFIG.SESSION_COOKIE_SECURE
app.config["SESSION_COOKIE_SAMESITE"] = CONFIG.SESSION_COOKIE_SAMESITE

if CONFIG.SAML_ENABLED and saml_bp is not None:
    app.register_blueprint(saml_bp)
app.register_blueprint(discord_bp)

@app.context_processor
def inject_globals():
    return {"current_year": datetime.utcnow().year}


def _verification_context() -> dict:
    verification_state = session.get("verification_state") or {}
    saml_complete = bool(verification_state.get("saml_complete"))
    discord_complete = bool(
        verification_state.get("discord_complete") or verification_state.get("verified")
    )
    saml_user = session.get("saml_user") or {}
    discord_user = session.get("discord_user") or {}
    verification_error = session.pop("verification_error", None)

    try:
        saml_login_url = url_for("saml.saml_login")
    except Exception:
        saml_login_url = None

    try:
        discord_login_url = url_for("discord.discord_login")
    except Exception:
        discord_login_url = None

    try:
        logout_url = url_for("saml.saml_logout")
    except Exception:
        logout_url = None

    context = {
        "verification_state": verification_state,
        "saml_complete": saml_complete,
        "discord_complete": discord_complete,
        "saml_user": saml_user,
        "discord_user": discord_user,
        "saml_login_url": saml_login_url,
        "discord_login_url": discord_login_url,
        "verification_error": verification_error,
        "discord_configured": DISCORD_CONFIG is not None,
        "logout_url": logout_url,
        "saml_enabled": CONFIG.SAML_ENABLED,
    }
    return context


@app.route("/")
def hello_world():
    context = _verification_context()
    return render_template("index.html", **context)


@app.route("/health")
def health():
    return {"status": "healthy"}


@app.route("/verified")
def verified():
    context = _verification_context()
    if not context["discord_complete"]:
        return redirect(url_for("hello_world"))
    return render_template("index.html", **context)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)

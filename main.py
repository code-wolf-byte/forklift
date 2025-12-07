import asyncio
import logging
import os
import threading
from datetime import datetime
from typing import Callable

from flask import Flask, redirect, render_template, session, url_for

from cron import cron_manager, start_upload_scheduler
from routes.discord import discord_bp
from utils.database import init_db
from utils.settings import CONFIG, DISCORD_CONFIG

logging.basicConfig(level=logging.INFO)

if CONFIG.SAML_ENABLED:
    from routes.saml import saml_bp
else:  # pragma: no cover - SAML disabled
    saml_bp = None  # type: ignore[assignment]


_should_start_metadata_scheduler: Callable[[], bool] = lambda: (
    os.environ.get("WERKZEUG_RUN_MAIN") in (None, "true")
)


_discord_bot_thread: threading.Thread | None = None
logger = logging.getLogger(__name__)


_should_start_discord_bot: Callable[[], bool] = lambda: (
    CONFIG.DISCORD_BOT_AUTOSTART and _should_start_metadata_scheduler()
)


def _start_discord_bot_thread() -> None:
    global _discord_bot_thread

    if DISCORD_CONFIG is None:
        logger.warning("Discord bot autostart skipped: DISCORD_CONFIG is not set")
        return
    if _discord_bot_thread and _discord_bot_thread.is_alive():
        return

    def _run_bot() -> None:
        from asu_discord import create_bot
        from asu_discord.shared import register_bot

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        bot = create_bot()
        register_bot(bot, loop=loop)

        async def _runner():
            await bot.start(DISCORD_CONFIG.bot_token)  # type: ignore[arg-type]

        try:
            loop.run_until_complete(_runner())
        except Exception:  # pragma: no cover - defensive
            logger.exception("Discord bot thread exited unexpectedly")
        finally:
            loop.close()

    _discord_bot_thread = threading.Thread(
        target=_run_bot, name="discord-bot", daemon=True
    )
    _discord_bot_thread.start()
    logger.info(
        "Started Discord bot background thread for guild %s", DISCORD_CONFIG.guild_id
    )


if CONFIG.SAML_ENABLED:
    cron_manager.run_jobs(
        job_names=("refresh_saml_metadata",),
        start_metadata_scheduler=_should_start_metadata_scheduler(),
    )
if _should_start_metadata_scheduler():
    start_upload_scheduler()
init_db()
if _should_start_discord_bot():
    _start_discord_bot_thread()

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
    student_profile = session.get("student_profile") or verification_state.get(
        "student_profile"
    )
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
        "student_profile": student_profile,
    }
    return context


@app.route("/")
def index():
    context = _verification_context()
    return render_template("index.html", **context)


@app.route("/health")
def health():
    return {"status": "healthy"}


@app.route("/verification-error")
def verification_error():
    context = _verification_context()
    if not context.get("verification_error"):
        return redirect(url_for("hello_world"))
    return render_template("index.html", **context), 400


@app.route("/verified")
def verified():
    context = _verification_context()
    if not context["discord_complete"]:
        return redirect(url_for("hello_world"))
    return render_template("index.html", **context)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)

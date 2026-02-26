import asyncio
import logging
import os
import threading
from datetime import datetime
from typing import Callable

from flask import Flask, abort, jsonify, redirect, render_template, send_from_directory, session, url_for

from cron import start_upload_scheduler
from routes.discord import discord_bp
from routes.cas import cas_bp
from services.google_sheets import sync_departed_users
from utils.database import init_db
from utils.settings import CONFIG, DISCORD_CONFIG

logging.basicConfig(level=logging.INFO)


_should_start_background_tasks: Callable[[], bool] = lambda: (
    os.environ.get("WERKZEUG_RUN_MAIN") in (None, "true")
)


_discord_bot_thread: threading.Thread | None = None
logger = logging.getLogger(__name__)


_should_start_discord_bot: Callable[[], bool] = lambda: (
    CONFIG.DISCORD_BOT_AUTOSTART and _should_start_background_tasks()
)


class BlueprintRegistrar:
    """Centralized blueprint registration."""

    def __init__(self, *, cas_enabled: bool) -> None:
        self.cas_enabled = cas_enabled

    def register_all(self, app: Flask) -> None:
        if self.cas_enabled:
            app.register_blueprint(cas_bp)
        app.register_blueprint(discord_bp)


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
    logger.info("Started Discord bot background thread for guild %s", DISCORD_CONFIG.guild_id)


if _should_start_background_tasks():
    init_db()
    start_upload_scheduler()
    sync_departed_users()
else:
    init_db()
if _should_start_discord_bot():
    _start_discord_bot_thread()

app = Flask(__name__)
app.secret_key = CONFIG.SECRET_KEY
app.config["SESSION_COOKIE_NAME"] = CONFIG.SESSION_COOKIE_NAME
app.config["SESSION_COOKIE_SECURE"] = CONFIG.SESSION_COOKIE_SECURE
app.config["SESSION_COOKIE_SAMESITE"] = CONFIG.SESSION_COOKIE_SAMESITE

registrar = BlueprintRegistrar(cas_enabled=CONFIG.CAS_ENABLED)
registrar.register_all(app)

REACT_BUILD_DIR = os.getenv(
    "REACT_BUILD_DIR",
    os.path.join(os.path.dirname(__file__), "asu-unity-react", "dist"),
)


@app.context_processor
def inject_globals():
    return {"current_year": datetime.utcnow().year}


def _verification_context() -> dict:
    verification_state = session.get("verification_state") or {}
    cas_complete = bool(verification_state.get("cas_complete"))
    discord_complete = bool(
        verification_state.get("discord_complete") or verification_state.get("verified")
    )
    cas_user = session.get("cas_user") or {}
    discord_user = session.get("discord_user") or {}
    student_profile = session.get("student_profile") or verification_state.get(
        "student_profile"
    )
    verification_error = session.pop("verification_error", None)

    try:
        cas_login_url = url_for("cas.cas_login")
    except Exception:
        cas_login_url = None

    try:
        discord_login_url = url_for("discord.discord_login")
    except Exception:
        discord_login_url = None

    try:
        logout_url = url_for("cas.cas_logout")
    except Exception:
        logout_url = None

    context = {
        "verification_state": verification_state,
        "cas_complete": cas_complete,
        "discord_complete": discord_complete,
        "cas_user": cas_user,
        "discord_user": discord_user,
        "cas_login_url": cas_login_url,
        "discord_login_url": discord_login_url,
        "verification_error": verification_error,
        "discord_configured": DISCORD_CONFIG is not None,
        "logout_url": logout_url,
        "cas_enabled": CONFIG.CAS_ENABLED,
        "student_profile": student_profile,
    }
    return context


@app.route("/api/status")
def api_status():
    context = _verification_context()
    return jsonify(context)


@app.route("/health")
def health():
    return {"status": "healthy"}


@app.route("/verification-error")
def verification_error():
    return redirect(url_for("index"))


@app.route("/verified")
def verified():
    return redirect(url_for("index"))


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def index(path):
    react_index = os.path.join(REACT_BUILD_DIR, "index.html")
    if os.path.exists(react_index):
        # Serve static assets (JS, CSS, images) directly
        if path and os.path.exists(os.path.join(REACT_BUILD_DIR, path)):
            return send_from_directory(REACT_BUILD_DIR, path)
        # SPA fallback — all other paths serve index.html
        return send_from_directory(REACT_BUILD_DIR, "index.html")
    # Dev fallback: no React build present, serve old Jinja template
    if path:
        abort(404)
    context = _verification_context()
    return render_template("index.html", **context)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)

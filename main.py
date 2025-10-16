from datetime import datetime

from flask import Flask, render_template

from routes import discord_bp, saml_bp
from utils.database import init_db
from utils.metadata import ensure_metadata_on_startup
from utils.settings import CONFIG

ensure_metadata_on_startup()
init_db()

app = Flask(__name__)
app.secret_key = CONFIG.SECRET_KEY
app.config["SESSION_COOKIE_NAME"] = CONFIG.SESSION_COOKIE_NAME
app.config["SESSION_COOKIE_SECURE"] = CONFIG.SESSION_COOKIE_SECURE
app.config["SESSION_COOKIE_SAMESITE"] = CONFIG.SESSION_COOKIE_SAMESITE

app.register_blueprint(saml_bp)
app.register_blueprint(discord_bp)

@app.context_processor
def inject_globals():
    return {"current_year": datetime.utcnow().year}


@app.route("/")
def hello_world():
    return render_template("index.html")


@app.route("/health")
def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)

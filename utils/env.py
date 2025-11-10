"""Helpers to load environment variables for local development."""

from __future__ import annotations

from pathlib import Path
from threading import Lock

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency
    load_dotenv = None  # type: ignore[assignment]

_LOCK = Lock()
_LOADED = False


def ensure_loaded() -> None:
    """Load the project .env file once for local runs."""
    global _LOADED
    if _LOADED or load_dotenv is None:
        return
    with _LOCK:
        if _LOADED:
            return
        project_root = Path(__file__).resolve().parent.parent
        env_path = project_root / ".env"
        # load_dotenv tolerates missing files; override=False keeps exported vars intact.
        load_dotenv(dotenv_path=env_path, override=False)
        _LOADED = True


# Load immediately so imports that read os.environ see .env values.
ensure_loaded()


__all__ = ["ensure_loaded"]

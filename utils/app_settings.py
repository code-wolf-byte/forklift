"""Admin-editable runtime settings.

Precedence: ``app_settings`` DB row → env var → hardcoded default. The code
defaults live where they always did; this module only layers overrides on top,
so an empty table means the application behaves exactly as before.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, Iterable

import yaml

from utils.database import AppSetting, session_scope
from utils.settings import CONFIG, DISCORD_CONFIG

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "verification.yaml"
_CACHE_TTL_S = 30.0

# Fallbacks used when config/verification.yaml is missing or unreadable.
_FALLBACK_TERM_CODE = "2267"
_FALLBACK_ACTIVE_TERM_CODES = ["2267", "2261"]
_FALLBACK_UNVERIFIED_ROLE_ID = "1207441184218161182"
_FALLBACK_GOLD_GUIDE_ROLE_ID = "1187156709597270157"


def _yaml_config() -> dict:
    try:
        with _CONFIG_PATH.open() as fh:
            return yaml.safe_load(fh) or {}
    except OSError:
        logger.warning("verification.yaml not readable at %s; using built-in defaults", _CONFIG_PATH)
        return {}


def _build_defaults() -> dict[str, Any]:
    from asu_discord.roles import DEFAULT_ROLE_ID_MAP

    cfg = _yaml_config()
    verified_role_id = DISCORD_CONFIG.verified_role_id if DISCORD_CONFIG else None
    unverified_role_id = (
        (DISCORD_CONFIG.unverified_role_id if DISCORD_CONFIG else None)
        or _FALLBACK_UNVERIFIED_ROLE_ID
    )
    return {
        "verification_enabled": True,
        "qna_forum_channel_id": CONFIG.QNA_FORUM_CHANNEL_ID,
        "verified_role_id": verified_role_id,
        "unverified_role_id": unverified_role_id,
        "gold_guide_role_id": _FALLBACK_GOLD_GUIDE_ROLE_ID,
        "qna_helper_role_id": CONFIG.QNA_HELPER_ROLE_ID,
        "admin_restricted_role_ids": [
            str(r) for r in cfg.get("admin", {}).get("restricted_role_ids", [])
        ],
        "role_id_map": dict(DEFAULT_ROLE_ID_MAP),
        "target_term_code": str(
            cfg.get("verification", {}).get("target_term_code", _FALLBACK_TERM_CODE)
        ),
        "active_term_codes": list(_FALLBACK_ACTIVE_TERM_CODES),
    }


_defaults: dict[str, Any] | None = None
_defaults_lock = threading.Lock()


def defaults() -> dict[str, Any]:
    """Code/env/yaml defaults, built once."""
    global _defaults
    if _defaults is None:
        with _defaults_lock:
            if _defaults is None:
                _defaults = _build_defaults()
    return _defaults


KEYS: tuple[str, ...] = (
    "verification_enabled",
    "qna_forum_channel_id",
    "verified_role_id",
    "unverified_role_id",
    "gold_guide_role_id",
    "qna_helper_role_id",
    "admin_restricted_role_ids",
    "role_id_map",
    "target_term_code",
    "active_term_codes",
)

# Keys holding a single Discord snowflake, and those holding a list of them.
SNOWFLAKE_KEYS = frozenset(
    {
        "qna_forum_channel_id",
        "verified_role_id",
        "unverified_role_id",
        "gold_guide_role_id",
        "qna_helper_role_id",
    }
)
SNOWFLAKE_LIST_KEYS = frozenset({"admin_restricted_role_ids"})
BOOL_KEYS = frozenset({"verification_enabled"})

# ponytail: 30s TTL over a whole-table read. Per-key invalidation only if this
# grows past a few dozen rows.
_cache: dict[str, Any] = {}
_cache_expires_at: float = 0.0
_cache_lock = threading.Lock()


def _overrides() -> dict[str, Any]:
    """Return the DB overrides, refreshing the cache when stale."""
    global _cache, _cache_expires_at

    now = time.monotonic()
    with _cache_lock:
        if now < _cache_expires_at:
            return _cache

    loaded: dict[str, Any] = {}
    try:
        with session_scope() as db_session:
            for row in db_session.query(AppSetting).all():
                try:
                    loaded[row.key] = json.loads(row.value)
                except (TypeError, ValueError):
                    logger.warning("Ignoring malformed app_settings value for %r", row.key)
    except Exception:
        # A settings read must never take down a request or the bot.
        logger.exception("Failed to load app_settings; falling back to defaults")
        return {}

    with _cache_lock:
        _cache = loaded
        _cache_expires_at = time.monotonic() + _CACHE_TTL_S
    return loaded


def clear_cache() -> None:
    global _cache_expires_at
    with _cache_lock:
        _cache_expires_at = 0.0


def get(key: str) -> Any:
    """Return the effective value for ``key`` (DB override, else default)."""
    if key not in KEYS:
        raise KeyError(f"Unknown setting: {key}")
    overrides = _overrides()
    if key in overrides:
        return overrides[key]
    return defaults()[key]


def get_all() -> dict[str, dict[str, Any]]:
    """Per-key value, default, override flag and audit info — for the admin API."""
    overrides = _overrides()
    meta: dict[str, tuple[str | None, str | None]] = {}
    try:
        with session_scope() as db_session:
            for row in db_session.query(AppSetting).all():
                meta[row.key] = (
                    row.updated_at.isoformat() if row.updated_at else None,
                    row.updated_by,
                )
    except Exception:
        logger.exception("Failed to read app_settings audit info")

    result = {}
    for key in KEYS:
        updated_at, updated_by = meta.get(key, (None, None))
        result[key] = {
            "value": overrides.get(key, defaults()[key]),
            "default": defaults()[key],
            "is_overridden": key in overrides,
            "updated_at": updated_at,
            "updated_by": updated_by,
        }
    return result


# ── Validation ────────────────────────────────────────────────────────────────


class SettingsValidationError(ValueError):
    """Raised when a submitted setting value is structurally invalid."""


def _is_snowflake(value: Any) -> bool:
    text = str(value).strip()
    return text.isdigit() and 17 <= len(text) <= 20


def _clean_snowflake(key: str, value: Any) -> str:
    if not _is_snowflake(value):
        raise SettingsValidationError(f"{key}: {value!r} is not a valid Discord ID")
    return str(value).strip()


def _clean_term_code(key: str, value: Any) -> str:
    text = str(value).strip()
    if not (text.isdigit() and len(text) == 4):
        raise SettingsValidationError(f"{key}: {value!r} is not a 4-digit term code")
    return text


def _require_list(key: str, value: Any) -> list:
    if not isinstance(value, (list, tuple)):
        raise SettingsValidationError(f"{key}: expected a list")
    return list(value)


def validate(key: str, value: Any) -> Any:
    """Return the normalized value for ``key``, or raise SettingsValidationError."""
    if key not in KEYS:
        raise SettingsValidationError(f"Unknown setting: {key}")

    if key in BOOL_KEYS:
        if not isinstance(value, bool):
            raise SettingsValidationError(f"{key}: expected true or false")
        return value

    if key in SNOWFLAKE_KEYS:
        if value in (None, ""):
            if key in {"verified_role_id", "unverified_role_id", "gold_guide_role_id"}:
                raise SettingsValidationError(f"{key} cannot be empty")
            return None
        return _clean_snowflake(key, value)

    if key in SNOWFLAKE_LIST_KEYS:
        return [_clean_snowflake(key, item) for item in _require_list(key, value)]

    if key == "target_term_code":
        return _clean_term_code(key, value)

    if key == "active_term_codes":
        codes = [_clean_term_code(key, item) for item in _require_list(key, value)]
        if not codes:
            raise SettingsValidationError("active_term_codes cannot be empty")
        return codes

    if key == "role_id_map":
        if not isinstance(value, dict):
            raise SettingsValidationError("role_id_map: expected an object")
        known = set(defaults()["role_id_map"])
        unknown = sorted(set(value) - known)
        if unknown:
            raise SettingsValidationError(
                "role_id_map: unknown role name(s): " + ", ".join(unknown)
            )
        cleaned: dict[str, int] = {}
        for name, role_id in value.items():
            if role_id in (None, ""):
                continue  # a blanked role is simply unmapped
            cleaned[name] = int(_clean_snowflake(f"role_id_map[{name}]", role_id))
        return cleaned

    raise SettingsValidationError(f"Unhandled setting: {key}")  # pragma: no cover


def iter_snowflakes(key: str, value: Any) -> Iterable[str]:
    """Yield every Discord ID contained in a validated value (for existence checks)."""
    if key in SNOWFLAKE_KEYS:
        if value:
            yield str(value)
    elif key in SNOWFLAKE_LIST_KEYS:
        yield from (str(item) for item in value)
    elif key == "role_id_map":
        yield from (str(item) for item in value.values())


# ── Writes ────────────────────────────────────────────────────────────────────


def set_many(updates: dict[str, Any], *, updated_by: str | None = None) -> None:
    """Validate and persist overrides. A ``None`` value resets that key to its default."""
    resets = [key for key, value in updates.items() if value is None and key in KEYS]
    cleaned = {
        key: validate(key, value)
        for key, value in updates.items()
        if key not in resets
    }

    with session_scope() as db_session:
        for key in resets:
            db_session.query(AppSetting).filter(AppSetting.key == key).delete()
        for key, value in cleaned.items():
            row = (
                db_session.query(AppSetting)
                .filter(AppSetting.key == key)
                .one_or_none()
            )
            payload = json.dumps(value)
            if row is None:
                db_session.add(
                    AppSetting(key=key, value=payload, updated_by=updated_by)
                )
            else:
                row.value = payload
                row.updated_by = updated_by

    clear_cache()
    logger.info(
        "app_settings updated by %s: %s",
        updated_by or "unknown",
        ", ".join(sorted(set(cleaned) | set(resets))) or "(nothing)",
    )

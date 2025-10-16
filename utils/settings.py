"""Application settings that are not specific to SAML metadata."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_value(name: str, *, default: str | None = None) -> str | None:
    value = os.getenv(name, default)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _env_list(name: str, *, default: Iterable[str] | None = None, separator: str = ",") -> List[str]:
    raw = os.getenv(name)
    if raw is None:
        return list(default) if default is not None else []
    items = [part.strip() for part in raw.split(separator)]
    return [item for item in items if item]


@dataclass(slots=True)
class AppConfig:
    """Expose high-level application configuration."""

    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{(Path(__file__).resolve().parent.parent / 'forklift.db').as_posix()}",
    )
    SECRET_KEY: str = os.getenv("FLASK_SECRET_KEY", os.getenv("SECRET_KEY", "change-me"))
    SESSION_COOKIE_NAME: str = os.getenv("SESSION_COOKIE_NAME", "forklift_session")
    SESSION_COOKIE_SECURE: bool = _env_bool("SESSION_COOKIE_SECURE", default=False)
    SESSION_COOKIE_SAMESITE: str = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
    DISCORD_SUCCESS_REDIRECT: str | None = _env_value("DISCORD_SUCCESS_REDIRECT")
    DISCORD_FAILURE_REDIRECT: str | None = _env_value("DISCORD_FAILURE_REDIRECT")
    SAML_ATTRIBUTE_MAP: Dict[str, List[str]] = field(init=False)

    def __post_init__(self) -> None:
        if not self.SECRET_KEY or self.SECRET_KEY == "change-me":
            self.SECRET_KEY = "change-me"
        self.SAML_ATTRIBUTE_MAP = {
            "asurite": _env_list("SAML_ATTR_ASURITE", default=["uid", "asuEduID", "asuEduPersonID"]),
            "email": _env_list("SAML_ATTR_EMAIL", default=["mail", "email"]),
            "full_name": _env_list("SAML_ATTR_FULL_NAME", default=["displayName"]),
            "first_name": _env_list("SAML_ATTR_FIRST_NAME", default=["givenName"]),
            "last_name": _env_list("SAML_ATTR_LAST_NAME", default=["sn"]),
            "affiliations": _env_list("SAML_ATTR_AFFILIATIONS", default=["eduPersonAffiliation"]),
        }


@dataclass(slots=True)
class DiscordConfig:
    client_id: str
    client_secret: str
    redirect_uri: str
    bot_token: str
    guild_id: str
    verified_role_id: str
    scope: str = "identify guilds.join"
    api_base: str = "https://discord.com/api/v10"
    authorize_base: str = "https://discord.com/oauth2/authorize"
    token_url: str = "https://discord.com/api/oauth2/token"

    @classmethod
    def from_env(cls) -> "DiscordConfig":
        required_names = {
            "client_id": "DISCORD_CLIENT_ID",
            "client_secret": "DISCORD_CLIENT_SECRET",
            "redirect_uri": "DISCORD_REDIRECT_URI",
            "bot_token": "DISCORD_BOT_TOKEN",
            "guild_id": "DISCORD_GUILD_ID",
            "verified_role_id": "DISCORD_VERIFIED_ROLE_ID",
        }
        payload: Dict[str, str] = {}
        missing: List[str] = []

        for field, env_name in required_names.items():
            value = _env_value(env_name)
            if value is None:
                missing.append(env_name)
            else:
                payload[field] = value

        scope = _env_value("DISCORD_SCOPE", default="identify guilds.join")

        if missing:
            missing_vars = ", ".join(missing)
            raise RuntimeError(f"Missing Discord environment variables: {missing_vars}")

        return cls(scope=scope, **payload)


CONFIG = AppConfig()

try:
    DISCORD_CONFIG = DiscordConfig.from_env()
except RuntimeError:
    DISCORD_CONFIG = None  # type: ignore[assignment]


__all__ = ["CONFIG", "DISCORD_CONFIG", "DiscordConfig", "AppConfig"]

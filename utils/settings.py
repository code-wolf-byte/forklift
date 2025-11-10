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
    DEV_MODE: bool = _env_bool("FORKLIFT_DEV_MODE", default=False)
    DATABASE_URL: str = field(init=False)
    SECRET_KEY: str = os.getenv("FLASK_SECRET_KEY", os.getenv("SECRET_KEY", "change-me"))
    SESSION_COOKIE_NAME: str = os.getenv("SESSION_COOKIE_NAME", "forklift_session")
    SESSION_COOKIE_SECURE: bool = _env_bool("SESSION_COOKIE_SECURE", default=False)
    SESSION_COOKIE_SAMESITE: str = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
    DISCORD_SUCCESS_REDIRECT: str | None = _env_value("DISCORD_SUCCESS_REDIRECT")
    DISCORD_FAILURE_REDIRECT: str | None = _env_value("DISCORD_FAILURE_REDIRECT")
    SAML_ATTRIBUTE_MAP: Dict[str, List[str]] = field(init=False)
    SAML_ENABLED: bool = field(init=False)

    def __post_init__(self) -> None:
        default_db_path = self.BASE_DIR / "forklift.db"
        default_db_url = f"sqlite:///{default_db_path.as_posix()}"
        env_db_url = os.getenv("DATABASE_URL")
        db_url = env_db_url.strip() if env_db_url else default_db_url

        if not db_url:
            db_url = default_db_url

        if self.DEV_MODE and db_url.startswith("sqlite") and "/app/" in db_url:
            db_url = default_db_url

        sqlite_prefix = "sqlite:///"
        if db_url.startswith(sqlite_prefix):
            sqlite_path = db_url[len(sqlite_prefix) :]
            if sqlite_path:
                file_path = Path(sqlite_path)
                try:
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                except OSError:
                    if self.DEV_MODE:
                        db_url = default_db_url
                        file_path = default_db_path
                        file_path.parent.mkdir(parents=True, exist_ok=True)
                    else:
                        raise

        self.DATABASE_URL = db_url
        if not self.SECRET_KEY or self.SECRET_KEY == "change-me":
            self.SECRET_KEY = "change-me"
        default_asurite = [
            "uid",
            "asuEduID",
            "asuEduPersonID",
            "eduPersonPrincipalName",
            "urn:oid:0.9.2342.19200300.100.1.1",
            "urn:oid:1.3.6.1.4.1.5923.1.1.1.6",
        ]
        default_email = [
            "mail",
            "email",
            "urn:oid:0.9.2342.19200300.100.1.3",
            "urn:oid:1.2.840.113549.1.9.1",
        ]
        default_full_name = [
            "displayName",
            "cn",
            "urn:oid:2.16.840.1.113730.3.1.241",
            "urn:oid:2.5.4.3",
        ]
        default_first_name = ["givenName", "urn:oid:2.5.4.42"]
        default_last_name = ["sn", "surname", "urn:oid:2.5.4.4"]
        default_affiliations = [
            "eduPersonAffiliation",
            "urn:oid:1.3.6.1.4.1.5923.1.1.1.1",
        ]
        self.SAML_ATTRIBUTE_MAP = {
            "asurite": _env_list("SAML_ATTR_ASURITE", default=default_asurite),
            "email": _env_list("SAML_ATTR_EMAIL", default=default_email),
            "full_name": _env_list("SAML_ATTR_FULL_NAME", default=default_full_name),
            "first_name": _env_list("SAML_ATTR_FIRST_NAME", default=default_first_name),
            "last_name": _env_list("SAML_ATTR_LAST_NAME", default=default_last_name),
            "affiliations": _env_list("SAML_ATTR_AFFILIATIONS", default=default_affiliations),
        }
        self.SAML_ENABLED = not self.DEV_MODE


@dataclass(slots=True)
class DiscordConfig:
    client_id: str
    client_secret: str
    redirect_uri: str
    bot_token: str
    guild_id: str
    verified_role_id: str
    test_guild_ids: tuple[int, ...] = ()
    scope: str = "identify"
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

        scope = _env_value("DISCORD_SCOPE", default="identify")
        test_guild_ids_raw = _env_list("DISCORD_TEST_GUILD_IDS")
        test_guild_ids: List[int] = []
        for raw_id in test_guild_ids_raw:
            try:
                test_guild_ids.append(int(raw_id))
            except ValueError as exc:
                raise RuntimeError(f"Invalid guild id in DISCORD_TEST_GUILD_IDS: {raw_id}") from exc

        if missing:
            missing_vars = ", ".join(missing)
            raise RuntimeError(f"Missing Discord environment variables: {missing_vars}")

        return cls(scope=scope, test_guild_ids=tuple(test_guild_ids), **payload)


CONFIG = AppConfig()

try:
    DISCORD_CONFIG = DiscordConfig.from_env()
except RuntimeError:
    DISCORD_CONFIG = None  # type: ignore[assignment]


__all__ = ["CONFIG", "DISCORD_CONFIG", "DiscordConfig", "AppConfig"]

"""Flask route blueprints."""

from .discord import discord_bp
from .saml import saml_bp

__all__ = ["saml_bp", "discord_bp"]

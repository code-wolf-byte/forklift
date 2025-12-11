"""Flask route blueprints."""

from .discord import discord_bp
from .cas import cas_bp

__all__ = ["cas_bp", "discord_bp"]

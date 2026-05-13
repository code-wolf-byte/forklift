from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import discord
import yaml
from discord.ext import commands
from discord.commands import Option, slash_command
from sqlalchemy import func, select

from utils.settings import DISCORD_CONFIG
from utils.database import DiscordMember, User, UserRoleException, session_scope, save_user_roles, get_user_by_discord_id, get_exceptions_for_discord_id
from services.google_sheets import write_user_left
from ..models import SalesforceOpportunity, StudentProfile
from ..roles import ROLE_ID_MAP
from ..salesforce import get_student_profile
from utils.salesforce import cache_sf_profile

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "verification.yaml"
with _CONFIG_PATH.open() as _f:
    _VERIFICATION_CONFIG: dict = yaml.safe_load(_f).get("verification", {})

TEST_GUILD_IDS: list[int] = []
if DISCORD_CONFIG and DISCORD_CONFIG.test_guild_ids:
    TEST_GUILD_IDS = [int(gid) for gid in DISCORD_CONFIG.test_guild_ids]

SLASH_COMMAND_KWARGS = {
    "name": "setup_verification",
    "description": "Post the Devil2Devil verification instructions.",
    "dm_permission": False,
    "default_member_permissions": discord.Permissions(manage_guild=True),
}
if TEST_GUILD_IDS:
    SLASH_COMMAND_KWARGS["guild_ids"] = TEST_GUILD_IDS


def _moderation_command_kwargs(name: str, description: str) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "name": name,
        "description": description,
        "dm_permission": False,
        "default_member_permissions": discord.Permissions(manage_roles=True),
    }
    if TEST_GUILD_IDS:
        kwargs["guild_ids"] = TEST_GUILD_IDS
    return kwargs


def _admin_command_kwargs(name: str, description: str) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "name": name,
        "description": description,
        "dm_permission": False,
        "default_member_permissions": discord.Permissions(administrator=True),
    }
    if TEST_GUILD_IDS:
        kwargs["guild_ids"] = TEST_GUILD_IDS
    return kwargs


TARGET_TERM_CODE: str = _VERIFICATION_CONFIG.get("target_term_code", "2267")

CAMPUS_ROLES: list[str] = [
    "Tempe",
    "Downtown Phoenix",
    "Polytechnic",
    "LA Center",
    "West Valley",
    "Online",
]


def _is_enrolled_or_admitted(opp: SalesforceOpportunity) -> bool:
    stage = (opp.stageName or "").strip().lower()
    return stage in {"enrolled", "admitted"}


def _normalize_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def _select_enrolled_opps(
    opportunities: list[SalesforceOpportunity],
) -> list[SalesforceOpportunity]:
    return [opp for opp in opportunities if _is_enrolled_or_admitted(opp)]


# Each entry is (match_fn, role_name). Evaluated in order; first match wins.
_COLLEGE_ROLE_MATCHERS: list[tuple[Callable[[str], bool], str]] = [
    (lambda n: "ira a" in n and "fulton" in n,                      "Ira A. Fulton Schools of Engineering"),
    (lambda n: "barrett" in n,                                       "Barrett The Honors College"),
    (lambda n: "liberal arts" in n and "sciences" in n,             "College of Liberal Arts and Sciences"),
    (lambda n: "global futures" in n,                                "College of Global Futures"),
    (lambda n: "nursing" in n and "health" in n,                    "Edson College of Nursing and Health Innovation"),
    (lambda n: "herberger" in n or ("design" in n and "arts" in n), "Herberger Institute for Design and the Arts"),
    (lambda n: "thunderbird" in n,                                   "Thunderbird School of Global Management"),
    (lambda n: "mary lou fulton" in n or "teachers college" in n,   "Mary Lou Fulton Teachers College"),
    (lambda n: "new college" in n,                                   "New College of Interdisciplinary Arts and Sciences"),
    (lambda n: "integrative sciences and arts" in n,                "College of Integrative Sciences and Arts"),
    (lambda n: "w.p. carey" in n or ("carey" in n and "business" in n), "W.P. Carey School of Business"),
    (lambda n: "cronkite" in n or "journalism" in n,                "Walter Cronkite School of Journalism and Mass Communication"),
    (lambda n: "watts" in n or "public service" in n,               "Watts College of Public Service and Community Solutions"),
    (lambda n: "university college" in n,                            "University College"),
]


def _college_role_from_name(college_name: Any) -> str | None:
    name = _normalize_str(college_name)
    if not name:
        return None
    for match, role in _COLLEGE_ROLE_MATCHERS:
        if match(name):
            return role
    return None


_CAMPUS_LOCATION_MAP: dict[str, str] = {
    "tempe": "Tempe",
    "downtown phoenix": "Downtown Phoenix",
    "polytechnic": "Polytechnic",
    "online": "Online",
    "west valley": "West Valley",
    "la center": "LA Center",
    "los angeles": "LA Center",
}


def _campus_role_from_location(location_raw: str | None) -> str | None:
    return _CAMPUS_LOCATION_MAP.get(_normalize_str(location_raw))


def _campus_role_from_opportunity(opp: SalesforceOpportunity) -> str | None:
    return _campus_role_from_location(opp.locationName)


def _campus_role_from_profile(student_profile: StudentProfile) -> str | None:
    return _campus_role_from_location(student_profile.locationName or student_profile.campus)


def role_names_from_student_profile(student_profile: StudentProfile) -> set[str]:
    """
    Derive logical role names from a Salesforce student profile.

    The returned names correspond to keys in ROLE_ID_MAP.
    """
    roles: set[str] = set()
    enrolled_opps = _select_enrolled_opps(student_profile.opportunities)

    # 1. Term-specific classification for target term (e.g., 2267)
    for opp in enrolled_opps:
        term_code = _normalize_str(opp.termCode)
        if term_code != TARGET_TERM_CODE:
            continue
        career = _normalize_str(opp.career)
        opp_type = _normalize_str(opp.type)
        if career == "graduate":
            roles.add("Graduate Student")
        elif career == "undergraduate":
            if "transfer" in opp_type:
                roles.add("Transfer Student")
            elif "freshman" in opp_type or "first time freshman" in opp_type:
                roles.add("First Year")

    # 2. Fallback level roles if target-term classification did not apply
    has_level_role = any(
        r in roles for r in ("Graduate Student", "First Year", "Transfer Student")
    )
    if not has_level_role:
        for opp in enrolled_opps:
            if _normalize_str(opp.career) == "graduate":
                roles.add("Graduate Student")
                has_level_role = True
                break

    if not has_level_role:
        for opp in enrolled_opps:
            if _normalize_str(opp.termCode) != TARGET_TERM_CODE and _normalize_str(opp.career) == "undergraduate":
                roles.add("Upperclassmen")
                break

    # 3. International / First-generation / Enrollment Deposit per enrolled opportunity
    for opp in enrolled_opps:
        if opp.internationalStudent is not None:
            if bool(opp.internationalStudent) or _normalize_str(opp.internationalStudent) in {"true", "yes", "y", "1"}:
                roles.add("International Student")
        if opp.firstGeneration is not None:
            if bool(opp.firstGeneration) or _normalize_str(opp.firstGeneration) in {"true", "yes", "y", "1"}:
                roles.add("First Generation Student")
        deposit_paid = bool(opp.enrollmentDepositPaid) or _normalize_str(opp.enrollmentDepositStatus) == "paid"
        if deposit_paid:
            roles.add("Commited")

    # 4. College and campus roles per enrolled opportunity
    for opp in enrolled_opps:
        college_role = _college_role_from_name(opp.collegeName)
        if college_role:
            roles.add(college_role)
        campus_role = _campus_role_from_opportunity(opp)
        if campus_role:
            roles.add(campus_role)

    # 5. Profile-level fallbacks (summary fields built by salesforce.py)
    if not has_level_role:
        career = _normalize_str(student_profile.career)
        if career == "graduate":
            roles.add("Graduate Student")
        elif career == "undergraduate":
            if student_profile.transfer:
                roles.add("Transfer Student")
            elif student_profile.firstYear:
                roles.add("First Year")
            elif student_profile.current is True:
                roles.add("Upperclassmen")

    if student_profile.international or student_profile.is_international:
        roles.add("International Student")

    if student_profile.depositPaid or student_profile.enrollmentDepositPaid:
        roles.add("Commited")

    if student_profile.inState:
        roles.add("Arizona Resident")
    elif student_profile.outOfState:
        roles.add("Out of State")

    if isinstance(student_profile.college, str) and student_profile.college in ROLE_ID_MAP:
        roles.add(student_profile.college)

    campus_role = _campus_role_from_profile(student_profile)
    if campus_role:
        roles.add(campus_role)

    return roles


class VerificationCog(commands.Cog):
    """Cog responsible for managing the Devil2Devil verification role."""

    VERIFICATION_URL = "https://verify.devil2devil.asu.edu"
    ASU_LOGO_URL = "https://verify.devil2devil.asu.edu/static/img/asu-logo-vertical.png"
    EMBED_COLOR = discord.Color.from_rgb(140, 29, 64)

    def __init__(
        self,
        bot: commands.Bot,
        *,
        guild_id: int,
        verified_role_id: int,
        unverified_role_id: int = 1207441184218161182,
    ) -> None:
        self.bot = bot
        self.guild_id = guild_id
        self.verified_role_id = verified_role_id
        self.unverified_role_id = unverified_role_id

    def _get_verified_role(
        self, guild: Optional[discord.Guild]
    ) -> Optional[discord.Role]:
        if guild is None:
            return None
        if guild.id != self.guild_id:
            logger.debug(
                "VerificationCog invoked for guild %s (expected %s)",
                guild.id,
                self.guild_id,
            )
            return None
        return guild.get_role(self.verified_role_id)

    def _get_unverified_role(
        self, guild: Optional[discord.Guild]
    ) -> Optional[discord.Role]:
        if guild is None:
            logger.debug("No guild provided to _get_unverified_role")
            return None
        if guild.id != self.guild_id:
            logger.debug(
                "VerificationCog invoked for guild %s (expected %s)",
                guild.id,
                self.guild_id,
            )
            return None
        return guild.get_role(self.unverified_role_id)

    async def _remove_role(
        self,
        member: discord.Member,
        role: Optional[discord.Role],
        *,
        label: str,
        reason: str,
    ) -> bool:
        if role is None:
            logger.info("No configured %s role available when processing member %s", label, member.id)
            return False
        if role not in member.roles:
            logger.info("Member %s does not currently have the %s role %s", member.id, label, role.id)
            return False
        try:
            await member.remove_roles(role, reason=reason)
        except discord.HTTPException as exc:  # pragma: no cover - network failure
            logger.warning("Failed to remove %s role %s from member %s: %s", label, role.id, member.id, exc)
            return False
        logger.info("Removed %s role %s from member %s", label, role.id, member.id)
        return True

    async def _remove_verified_role(
        self, guild: Optional[discord.Guild], member: discord.Member, *, reason: str
    ) -> bool:
        return await self._remove_role(member, self._get_verified_role(guild), label="verified", reason=reason)

    async def _remove_unverified_role(
        self, guild: Optional[discord.Guild], member: discord.Member, *, reason: str
    ) -> bool:
        return await self._remove_role(member, self._get_unverified_role(guild), label="unverified", reason=reason)

    async def _resolve_guild(self) -> discord.Guild:
        guild = self.bot.get_guild(self.guild_id)
        if guild is None:
            try:
                guild = await self.bot.fetch_guild(self.guild_id)
            except discord.HTTPException as exc:
                raise RuntimeError("Unable to load the Discord guild") from exc
        if guild is None:
            raise RuntimeError("Discord guild is not available")
        return guild

    async def _resolve_member(self, guild: discord.Guild, user_id: int) -> discord.Member:
        member = guild.get_member(user_id)
        if member is None:
            try:
                member = await guild.fetch_member(user_id)
            except discord.NotFound as exc:
                raise RuntimeError(f"Discord user {user_id} is not a member of the guild") from exc
            except discord.HTTPException as exc:
                raise RuntimeError("Unable to load Discord member information") from exc
        return member

    async def _apply_ban_discord_roles(
        self, guild: discord.Guild, member: discord.Member, *, reason: str
    ) -> None:
        """Strip all verification-managed roles and assign the unverified role."""
        await self._remove_verified_role(guild, member, reason=reason)

        managed_role_ids = set(ROLE_ID_MAP.values())
        roles_to_remove = [r for r in member.roles if r.id in managed_role_ids]
        if roles_to_remove:
            try:
                await member.remove_roles(*roles_to_remove, reason=reason)
            except discord.HTTPException as exc:
                logger.warning("Failed to remove managed roles from member %s: %s", member.id, exc)

        unverified_role = self._get_unverified_role(guild)
        if unverified_role is not None and unverified_role not in member.roles:
            try:
                await member.add_roles(unverified_role, reason=reason)
            except discord.HTTPException as exc:
                logger.warning("Failed to add unverified role to member %s: %s", member.id, exc)

    async def _require_home_guild(self, ctx: discord.ApplicationContext) -> bool:
        if ctx.guild_id != self.guild_id or ctx.guild is None:
            await ctx.respond(
                "This command is only available in the Devil2Devil server.",
                ephemeral=True,
            )
            return False
        return True

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        guild = self.bot.get_guild(self.guild_id)
        if guild is None:
            logger.warning(
                "VerificationCog could not locate guild %s yet", self.guild_id
            )
        else:
            logger.info("VerificationCog ready in guild %s (%s)", guild.id, guild.name)
            asyncio.ensure_future(self._strip_unverified_role_from_verified_members(guild))
            asyncio.ensure_future(self._backfill_discord_members(guild))

    async def _strip_unverified_role_from_verified_members(self, guild: discord.Guild) -> None:
        """On startup, remove the unverified role from any member already verified in the DB."""
        unverified_role = self._get_unverified_role(guild)
        if unverified_role is None:
            logger.info("No unverified role configured; skipping startup strip")
            return

        with session_scope() as session:
            verified_ids = [
                row[0]
                for row in session.query(User.discord_user_id)
                .filter(User.verified == True, User.discord_user_id.isnot(None))  # noqa: E712
                .all()
            ]

        removed = 0
        for discord_id_str in verified_ids:
            try:
                member = guild.get_member(int(discord_id_str))
            except (TypeError, ValueError):
                continue
            if member is None or unverified_role not in member.roles:
                continue
            try:
                await member.remove_roles(unverified_role, reason="Startup: remove unverified role from verified member")
                removed += 1
            except discord.HTTPException as exc:
                logger.warning("Failed to remove unverified role from %s on startup: %s", discord_id_str, exc)

        logger.info("Startup strip complete: removed unverified role from %d member(s)", removed)

    async def _backfill_discord_members(self, guild: discord.Guild) -> None:
        """On startup, ensure every current guild member has a DiscordMember row."""
        with session_scope() as session:
            existing_ids = {
                row[0]
                for row in session.query(DiscordMember.discord_user_id).all()
            }
            new_rows = []
            for member in guild.members:
                discord_id = str(member.id)
                if discord_id in existing_ids:
                    continue
                joined = (
                    member.joined_at.replace(tzinfo=None)
                    if member.joined_at
                    else datetime.utcnow()
                )
                new_rows.append(
                    DiscordMember(
                        discord_user_id=discord_id,
                        discord_username=str(member),
                        joined_at=joined,
                    )
                )
            if new_rows:
                session.bulk_save_objects(new_rows)
        logger.info("Discord member backfill complete: inserted %d row(s)", len(new_rows))

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Track every guild join in DiscordMember; also update User if already linked."""
        if member.guild.id != self.guild_id:
            return

        now = datetime.utcnow()
        discord_id = str(member.id)

        with session_scope() as session:
            dm = (
                session.query(DiscordMember)
                .filter(DiscordMember.discord_user_id == discord_id)
                .one_or_none()
            )
            if dm is None:
                session.add(
                    DiscordMember(
                        discord_user_id=discord_id,
                        discord_username=str(member),
                        joined_at=now,
                    )
                )
            else:
                dm.discord_username = str(member)
                dm.joined_at = now
                dm.left_at = None

            user = (
                session.query(User)
                .filter(User.discord_user_id == discord_id)
                .one_or_none()
            )
            if user is not None:
                user.joined_at = now
                user.left_at = None

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        """Track every guild leave in DiscordMember; also update User if linked."""
        if member.guild.id != self.guild_id:
            return

        now = datetime.utcnow()
        discord_id = str(member.id)

        with session_scope() as session:
            dm = (
                session.query(DiscordMember)
                .filter(DiscordMember.discord_user_id == discord_id)
                .one_or_none()
            )
            if dm is not None:
                dm.left_at = now

            user = (
                session.query(User)
                .filter(User.discord_user_id == discord_id)
                .one_or_none()
            )
            if user is not None:
                user.left_at = now
                if user.verified and user.email:
                    write_user_left(user.email, now)

    # Alias to match common terminology
    on_member_leave = on_member_remove

    @slash_command(
        **_moderation_command_kwargs(
            "verify", "Assign the verification role to a member."
        )
    )
    async def verify_member(
        self,
        ctx: discord.ApplicationContext,
        member: discord.Member = Option(discord.Member, "Member to verify"),
    ) -> None:
        """Assign the verification role to a member."""
        if not await self._require_home_guild(ctx):
            return

        role = self._get_verified_role(ctx.guild)
        if role is None:
            await ctx.respond("Unable to locate the configured verification role for this server.")
            return

        if role in member.roles:
            await ctx.respond(f"{member.mention} already has the verification role.")
            return

        reason = f"Manual verification by {ctx.author}"
        await member.add_roles(role, reason=reason)
        await self._remove_unverified_role(ctx.guild, member, reason=reason)

        try:
            with session_scope() as session:
                user = session.query(User).filter(User.discord_user_id == str(member.id)).one_or_none()
            asurite = user.asurite_id if user else None
            if asurite:
                profile = await asyncio.to_thread(get_student_profile, asurite)
                if "asurite" in profile:
                    asyncio.create_task(asyncio.to_thread(cache_sf_profile, asurite, profile))
                if not profile.get("error"):
                    await self.assign_roles_from_profile(member.id, profile)
        except Exception:
            logger.exception("Failed to assign Salesforce-based roles for user %s", member.id)
            await ctx.respond(
                f"{member.mention} has been marked as verified, "
                "but there was an error assigning additional roles.",
            )
            return

        await ctx.respond(f"{member.mention} has been marked as verified. ✅")

    async def verify_member_by_id(
        self, user_id: int, *, asurite: str | None = None
    ) -> None:
        """Assign the verified role to a Discord user identified by ID."""
        await self.bot.wait_until_ready()
        guild = await self._resolve_guild()
        role = self._get_verified_role(guild)
        if role is None:
            raise RuntimeError("Configured verification role could not be found")
        member = await self._resolve_member(guild, user_id)
        if role in member.roles:
            logger.info("Member %s already has the verification role", user_id)
            return
        reason = f"Automatic verification for {asurite}" if asurite else "Automatic verification"
        await member.add_roles(role, reason=reason)
        await self._remove_unverified_role(guild, member, reason=reason)
        logger.info("Assigned verification role to Discord user %s (ASURITE: %s)", user_id, asurite)

    async def unverify_member_by_id(
        self, user_id: int, *, reason: str | None = None
    ) -> bool:
        """Remove the verified role from a Discord user identified by ID."""
        await self.bot.wait_until_ready()
        guild = await self._resolve_guild()
        member = await self._resolve_member(guild, user_id)
        return await self._remove_verified_role(guild, member, reason=reason or "Automatic re-verification")

    async def add_role_to_member_by_id(self, user_id: int, role_name: str) -> None:
        """Add a named role (from ROLE_ID_MAP) to a guild member by Discord user ID."""
        await self.bot.wait_until_ready()
        role_id = ROLE_ID_MAP.get(role_name)
        if role_id is None:
            raise ValueError(f"Unknown role name: {role_name!r}")
        guild = await self._resolve_guild()
        member = await self._resolve_member(guild, user_id)
        role = guild.get_role(role_id)
        if role is None:
            raise RuntimeError(f"Role {role_name!r} (id {role_id}) not found in guild")
        if role not in member.roles:
            await member.add_roles(role, reason="Manual exception — admin role add")

    async def remove_role_from_member_by_id(self, user_id: int, role_name: str) -> None:
        """Remove a named role (from ROLE_ID_MAP) from a guild member by Discord user ID."""
        await self.bot.wait_until_ready()
        role_id = ROLE_ID_MAP.get(role_name)
        if role_id is None:
            raise ValueError(f"Unknown role name: {role_name!r}")
        guild = await self._resolve_guild()
        member = await self._resolve_member(guild, user_id)
        role = guild.get_role(role_id)
        if role is None:
            return  # Already absent, nothing to do.
        if role in member.roles:
            await member.remove_roles(role, reason="Manual exception — admin role remove")

    async def assign_roles_from_profile(
        self, user_id: int, student_profile: StudentProfile
    ) -> None:
        """Assign additional Discord roles for a user based on Salesforce data."""
        await self.bot.wait_until_ready()
        guild = await self._resolve_guild()
        member = await self._resolve_member(guild, user_id)

        logical_role_names = role_names_from_student_profile(student_profile)
        if not logical_role_names:
            logger.info("No additional roles derived from Salesforce profile for user %s", user_id)
            return

        exceptions = await asyncio.to_thread(get_exceptions_for_discord_id, str(user_id))
        paused_roles = {e.role_name for e in exceptions if e.exception_type == "paused"}

        roles_to_add: list[discord.Role] = []
        for logical_name in sorted(logical_role_names):
            if logical_name in paused_roles:
                logger.debug("Skipping paused role %s for user %s", logical_name, user_id)
                continue
            role_id = ROLE_ID_MAP.get(logical_name)
            if role_id is None:
                logger.debug("No configured Discord role id for %s", logical_name)
                continue
            role = guild.get_role(role_id)
            if role is None:
                logger.warning("Configured role id %s for %s not found in guild %s", role_id, logical_name, guild.id)
                continue
            if role not in member.roles:
                roles_to_add.append(role)

        if not roles_to_add:
            logger.info("No new Discord roles to assign for user %s from Salesforce profile", user_id)
            return

        reason = f"Automatic Salesforce-based role assignment for {student_profile.asurite}" if student_profile.asurite else "Automatic Salesforce-based role assignment"
        await member.add_roles(*roles_to_add, reason=reason)
        logger.info("Assigned Salesforce-based roles %s to Discord user %s", [r.id for r in roles_to_add], user_id)
        await self._save_roles_to_database(user_id, logical_role_names, source="verification")

    async def _save_roles_to_database(
        self, discord_user_id: int, role_names: set[str], source: str = "verification"
    ) -> None:
        """Save the user's Salesforce-derived roles to the database."""
        try:
            db_user = await asyncio.to_thread(get_user_by_discord_id, str(discord_user_id))
            if db_user is None:
                logger.warning(
                    "Cannot save roles to database: no database user for Discord ID %s",
                    discord_user_id,
                )
                return

            roles_to_save: list[tuple[str, int]] = []
            for role_name in sorted(role_names):
                role_id = ROLE_ID_MAP.get(role_name)
                if role_id is not None:
                    roles_to_save.append((role_name, role_id))

            if roles_to_save:
                await asyncio.to_thread(save_user_roles, db_user.id, roles_to_save, source)
                logger.info(
                    "Saved %d roles to database for user %s (Discord ID: %s)",
                    len(roles_to_save),
                    db_user.asurite_id,
                    discord_user_id,
                )
        except Exception:
            logger.exception(
                "Failed to save roles to database for Discord user %s", discord_user_id
            )

    async def remove_roles_from_profile(
        self, user_id: int, student_profile: StudentProfile
    ) -> None:
        """Remove Discord roles for a user based on Salesforce data."""
        await self.bot.wait_until_ready()
        guild = await self._resolve_guild()
        member = await self._resolve_member(guild, user_id)

        logical_role_names = role_names_from_student_profile(student_profile)
        if not logical_role_names:
            logger.info("No Salesforce-derived roles to remove for user %s", user_id)
            return

        roles_to_remove: list[discord.Role] = []
        for logical_name in sorted(logical_role_names):
            role_id = ROLE_ID_MAP.get(logical_name)
            if role_id is None:
                logger.debug("No configured Discord role id for %s", logical_name)
                continue
            role = guild.get_role(role_id)
            if role is None:
                logger.warning("Configured role id %s for %s not found in guild %s", role_id, logical_name, guild.id)
                continue
            if role in member.roles:
                roles_to_remove.append(role)

        if not roles_to_remove:
            logger.info("No Salesforce-derived roles to remove for user %s", user_id)
            return

        reason = f"Automatic Salesforce-based role removal for {student_profile.asurite}" if student_profile.asurite else "Automatic Salesforce-based role removal"
        await member.remove_roles(*roles_to_remove, reason=reason)
        logger.info("Removed Salesforce-based roles %s from Discord user %s", [r.id for r in roles_to_remove], user_id)

    async def refresh_roles_from_profile(
        self, user_id: int, student_profile: StudentProfile
    ) -> None:
        """Remove all ROLE_ID_MAP roles from a member and re-assign based on Salesforce profile."""
        await self.bot.wait_until_ready()
        guild = await self._resolve_guild()
        member = await self._resolve_member(guild, user_id)

        exceptions = await asyncio.to_thread(get_exceptions_for_discord_id, str(user_id))
        paused_roles = {e.role_name for e in exceptions if e.exception_type == "paused"}
        added_roles = {e.role_name for e in exceptions if e.exception_type == "added"}
        protected_role_ids = {
            ROLE_ID_MAP[name]
            for name in (paused_roles | added_roles)
            if name in ROLE_ID_MAP
        }

        # Remove all known Salesforce-managed roles currently held by the member,
        # except those protected by a paused or added exception.
        roles_to_remove = [
            guild.get_role(role_id)
            for role_id in ROLE_ID_MAP.values()
            if role_id not in protected_role_ids
        ]
        roles_to_remove = [r for r in roles_to_remove if r is not None and r in member.roles]
        if roles_to_remove:
            await member.remove_roles(*roles_to_remove, reason="Salesforce role refresh")

        # Assign new roles derived from the updated Salesforce profile,
        # skipping paused roles and always including added roles.
        logical_role_names = role_names_from_student_profile(student_profile)
        effective_names = (logical_role_names - paused_roles) | added_roles
        roles_to_add: list[discord.Role] = []
        for logical_name in sorted(effective_names):
            role_id = ROLE_ID_MAP.get(logical_name)
            if role_id is None:
                continue
            role = guild.get_role(role_id)
            if role is None:
                logger.warning(
                    "Configured role id %s for %s not found in guild %s",
                    role_id,
                    logical_name,
                    guild.id,
                )
                continue
            if role in member.roles:
                continue
            roles_to_add.append(role)

        if roles_to_add:
            await member.add_roles(*roles_to_add, reason="Salesforce role refresh")

        if effective_names:
            await self._save_roles_to_database(user_id, effective_names, source="refresh")

        logger.info(
            "Refreshed Salesforce roles for Discord user %s: -%d/+%d roles, assigned=[%s]",
            user_id,
            len(roles_to_remove),
            len(roles_to_add),
            ", ".join(sorted(effective_names)) if effective_names else "none",
        )

    @slash_command(
        **_moderation_command_kwargs(
            "unverify", "Remove the verification role from a member."
        )
    )
    async def unverify_member(
        self,
        ctx: discord.ApplicationContext,
        member: discord.Member = Option(discord.Member, "Member to unverify"),
    ) -> None:
        """Remove the verification role from a member."""
        if not await self._require_home_guild(ctx):
            return

        role = self._get_verified_role(ctx.guild)
        if role is None:
            await ctx.respond(
                "Unable to locate the configured verification role for this server."
            )
            return

        if role not in member.roles:
            await ctx.respond(f"{member.mention} is not currently verified.")
            return

        await member.remove_roles(role, reason=f"Manual unverification by {ctx.author}")
        await ctx.respond(f"{member.mention} no longer has the verification role.")

    @slash_command(
        **_moderation_command_kwargs(
            "blacklist",
            "Ban an ASURITE from verification and remove their verification role.",
        )
    )
    async def ban_asurite(
        self,
        ctx: discord.ApplicationContext,
        member: discord.Member = Option(discord.Member, "Discord member to ban", required=False, default=None),
        asurite: str = Option(str, "ASURITE ID to ban", required=False, default=None),
    ) -> None:
        """Ban an ASURITE from verification and revoke their Discord access."""
        if not await self._require_home_guild(ctx):
            return

        if member is None and not (asurite or "").strip():
            await ctx.respond(
                "Please provide either a Discord member or an ASURITE ID to ban.",
                ephemeral=True,
            )
            return

        await ctx.defer(ephemeral=True)

        # If a Discord member was given, resolve their ASURITE from the DB first.
        if member is not None:
            with session_scope() as db_session:
                linked = (
                    db_session.query(User)
                    .filter(User.discord_user_id == str(member.id))
                    .one_or_none()
                )
            if linked is None or not linked.asurite_id:
                await ctx.followup.send(
                    f"{member.mention} has no ASURITE linked in the system.",
                    ephemeral=True,
                )
                return
            asurite = linked.asurite_id

        target = (asurite or "").strip()
        normalized = target.lower()
        stored_asurite: str | None = None
        discord_user_id: int | None = None
        already_banned = False
        missing_user = False

        with session_scope() as db_session:
            stmt = select(User).where(func.lower(User.asurite_id) == normalized)
            user = db_session.execute(stmt).scalar_one_or_none()

            if user is None:
                missing_user = True
            else:
                stored_asurite = user.asurite_id
                try:
                    if user.discord_user_id:
                        discord_user_id = int(user.discord_user_id)
                except (TypeError, ValueError):
                    discord_user_id = None

                if user.banned:
                    already_banned = True
                else:
                    user.banned = True
                    user.verified = False
                    user.verified_at = None

        if missing_user:
            await ctx.followup.send(
                f"No verification record found for {target}.",
                ephemeral=True,
            )
            return

        notes: list[str] = []
        member: Optional[discord.Member] = None
        if discord_user_id is not None:
            member = ctx.guild.get_member(discord_user_id)
            if member is None:
                try:
                    member = await ctx.guild.fetch_member(discord_user_id)
                except discord.NotFound:
                    member = None
                except discord.HTTPException as exc:  # pragma: no cover - network failure
                    logger.warning(
                        "Unable to load guild member %s for ban action: %s",
                        discord_user_id,
                        exc,
                    )
                    member = None

        if member is not None:
            reason = f"Verification blacklist by {ctx.author}"
            await self._apply_ban_discord_roles(ctx.guild, member, reason=reason)
            notes.append(f"Removed all roles and assigned unverified role to {member.mention}.")
        elif discord_user_id is not None:
            notes.append(
                "Linked Discord account not found in the guild; no role changes made."
            )

        if already_banned:
            await ctx.followup.send(
                f"{stored_asurite or target} is already banned from verification."
                + (f" {' '.join(notes)}" if notes else ""),
                ephemeral=True,
            )
            return

        await ctx.followup.send(
            (
                f"{stored_asurite or target} has been banned from verification."
                + (f" {' '.join(notes)}" if notes else "")
            ),
            ephemeral=True,
        )

    @slash_command(
        **_moderation_command_kwargs(
            "whitelist",
            "Remove a blacklist ban and restore verification roles for a member.",
        )
    )
    async def whitelist_member(
        self,
        ctx: discord.ApplicationContext,
        member: discord.Member = Option(discord.Member, "Discord member to whitelist"),
    ) -> None:
        """Clear a blacklist ban and re-verify the member."""
        if not await self._require_home_guild(ctx):
            return

        await ctx.defer(ephemeral=True)

        asurite: str | None = None
        not_banned = False
        no_record = False

        with session_scope() as db_session:
            db_user = (
                db_session.query(User)
                .filter(User.discord_user_id == str(member.id))
                .one_or_none()
            )
            if db_user is None:
                no_record = True
            elif not db_user.banned:
                not_banned = True
            else:
                db_user.banned = False
                db_user.verified = True
                db_user.verified_at = datetime.now(timezone.utc).replace(tzinfo=None)
                asurite = db_user.asurite_id

        if no_record:
            await ctx.followup.send(
                f"{member.mention} has no verification record in the system.",
                ephemeral=True,
            )
            return

        if not_banned:
            await ctx.followup.send(
                f"{member.mention} is not currently blacklisted.",
                ephemeral=True,
            )
            return

        reason = f"Whitelist by {ctx.author}"

        # Remove unverified role, add verified role.
        await self._remove_unverified_role(ctx.guild, member, reason=reason)
        verified_role = self._get_verified_role(ctx.guild)
        if verified_role is not None and verified_role not in member.roles:
            try:
                await member.add_roles(verified_role, reason=reason)
            except discord.HTTPException as exc:
                logger.warning(
                    "Failed to add verified role to member %s during whitelist: %s",
                    member.id,
                    exc,
                )

        # Re-assign Salesforce-derived roles.
        if asurite:
            try:
                profile = await asyncio.to_thread(get_student_profile, asurite)
                if "asurite" in profile:
                    asyncio.create_task(asyncio.to_thread(cache_sf_profile, asurite, profile))
                if not profile.get("error"):
                    await self.assign_roles_from_profile(member.id, profile)
            except Exception:
                logger.exception(
                    "Failed to assign Salesforce-based roles for user %s during whitelist",
                    member.id,
                )
                await ctx.followup.send(
                    f"{member.mention} has been removed from the blacklist and re-verified, "
                    "but there was an error re-assigning additional roles.",
                    ephemeral=True,
                )
                return

        await ctx.followup.send(
            f"{member.mention} has been removed from the blacklist and re-verified. ✅",
            ephemeral=True,
        )

    def _build_verification_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="Verification",
            description=(
                "This Discord is for students admitted to Arizona State University. "
                "To get access to the full server please verify you've been accepted into Arizona State University."
            ),
            color=self.EMBED_COLOR,
        )
        embed.set_image(url=self.ASU_LOGO_URL)
        return embed

    def _build_verification_view(self) -> discord.ui.View:
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Verify Here", url=self.VERIFICATION_URL))
        return view

    @slash_command(**SLASH_COMMAND_KWARGS)
    async def setup_verification(self, ctx: discord.ApplicationContext) -> None:
        """Slash command to seed the verification prompt embed in-channel."""
        if not await self._require_home_guild(ctx):
            return

        if ctx.channel is None:
            await ctx.respond(
                "Unable to determine the target channel for this command.",
                ephemeral=True,
            )
            return

        await ctx.defer(ephemeral=True)

        embed = self._build_verification_embed()
        view = self._build_verification_view()
        await ctx.channel.send(embed=embed, view=view)

        await ctx.followup.send(
            "Verification prompt posted with the Verify Here button.", ephemeral=True
        )

    @slash_command(
        **{
            "name": "changecampus",
            "description": "Update your campus role in the Devil2Devil server.",
            "dm_permission": False,
            **({"guild_ids": TEST_GUILD_IDS} if TEST_GUILD_IDS else {}),
        }
    )
    async def changecampus(
        self,
        ctx: discord.ApplicationContext,
        campus: str = Option(
            str,
            "Your campus",
            choices=CAMPUS_ROLES,
            required=True,
        ),
    ) -> None:
        """Allow a verified member to self-correct their campus role."""
        if not await self._require_home_guild(ctx):
            return

        await ctx.defer(ephemeral=True)

        with session_scope() as db_session:
            db_user = (
                db_session.query(User)
                .filter(User.discord_user_id == str(ctx.author.id))
                .one_or_none()
            )
            if db_user is None or not db_user.verified:
                await ctx.followup.send(
                    "You must be verified to change your campus role.",
                    ephemeral=True,
                )
                return

        guild = ctx.guild
        member = ctx.author
        reason = f"Campus change via /changecampus: {campus!r}"

        # Swap campus roles on Discord
        roles_to_remove = [
            guild.get_role(ROLE_ID_MAP[name])
            for name in CAMPUS_ROLES
            if name != campus and name in ROLE_ID_MAP
        ]
        roles_to_remove = [r for r in roles_to_remove if r is not None and r in member.roles]
        if roles_to_remove:
            try:
                await member.remove_roles(*roles_to_remove, reason=reason)
            except discord.HTTPException as exc:
                logger.warning("Failed to remove campus roles from %s: %s", member.id, exc)

        new_role_id = ROLE_ID_MAP.get(campus)
        if new_role_id is not None:
            new_role = guild.get_role(new_role_id)
            if new_role is not None and new_role not in member.roles:
                try:
                    await member.add_roles(new_role, reason=reason)
                except discord.HTTPException as exc:
                    logger.warning("Failed to add campus role %r to %s: %s", campus, member.id, exc)

        # Write exceptions so Salesforce syncs honour the user's choice:
        # "added" for the selected campus, "paused" for all others.
        discord_user_id = str(ctx.author.id)
        with session_scope() as db_session:
            db_session.query(UserRoleException).filter(
                UserRoleException.discord_user_id == discord_user_id,
                UserRoleException.role_name.in_(CAMPUS_ROLES),
            ).delete(synchronize_session=False)

            db_session.add(UserRoleException(
                discord_user_id=discord_user_id,
                role_name=campus,
                exception_type="added",
                note="User self-selected via /changecampus",
                created_by=discord_user_id,
            ))
            for other in CAMPUS_ROLES:
                if other != campus:
                    db_session.add(UserRoleException(
                        discord_user_id=discord_user_id,
                        role_name=other,
                        exception_type="paused",
                        note=f"Suppressed by /changecampus selection: {campus!r}",
                        created_by=discord_user_id,
                    ))

        await ctx.followup.send(
            f"Your campus has been updated to **{campus}**. ✅\n"
            "An admin can review or override this in the admin panel.",
            ephemeral=True,
        )

    @slash_command(**_admin_command_kwargs("email", "Look up the ASU email for a verified member."))
    async def get_member_email(
        self,
        ctx: discord.ApplicationContext,
        user: discord.Member = Option(discord.Member, "Discord member to look up"),
    ) -> None:
        """Return the verified ASU email for a Discord member. Only visible to the invoker."""
        if not await self._require_home_guild(ctx):
            return

        with session_scope() as db_session:
            db_user = (
                db_session.query(User)
                .filter(User.discord_user_id == str(user.id))
                .one_or_none()
            )

        if db_user is None:
            await ctx.respond(
                f"{user.mention} has no verification record in the system.",
                ephemeral=True,
            )
            return

        if not db_user.email:
            await ctx.respond(
                f"{user.mention} is in the system but has no email on record.",
                ephemeral=True,
            )
            return

        lines = [f"**{user.mention}**"]
        lines.append(f"Email: `{db_user.email}`")
        if db_user.asurite_id:
            lines.append(f"ASURITE: `{db_user.asurite_id}`")
        lines.append(f"Verified: {'✅' if db_user.verified else '❌'}")

        await ctx.respond("\n".join(lines), ephemeral=True)

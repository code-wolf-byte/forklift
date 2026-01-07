from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

import discord
from discord.ext import commands
from discord.commands import Option, slash_command
from sqlalchemy import func, select

from utils.settings import DISCORD_CONFIG
from utils.database import User, session_scope
from ..roles import ROLE_ID_MAP

logger = logging.getLogger(__name__)

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


TARGET_TERM_CODE = "2267"


def _is_enrolled_or_admitted(opp: dict[str, Any]) -> bool:
    stage = (opp.get("stageName") or "").strip().lower()
    return stage in {"enrolled", "admitted"}


def _normalize_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def _select_enrolled_opps(
    opportunities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [opp for opp in opportunities if _is_enrolled_or_admitted(opp)]


def _college_role_from_name(college_name: Any) -> str | None:
    """
    Map a Salesforce collegeName to one of the configured college roles.
    Uses simple substring matching on a normalized, lower-cased name.
    """
    name = _normalize_str(college_name)
    if not name:
        return None

    if "ira a" in name and "fulton" in name:
        return "Ira A. Fulton Schools of Engineering"
    if "barrett" in name:
        return "Barrett The Honors College"
    if "liberal arts" in name and "sciences" in name:
        return "College of Liberal Arts and Sciences"
    if "global futures" in name:
        return "College of Global Futures"
    if "nursing" in name and "health" in name:
        return "Edson College of Nursing and Health Innovation"
    if "herberger" in name or ("design" in name and "arts" in name):
        return "Herberger Institute for Design and the Arts"
    if "thunderbird" in name:
        return "Thunderbird School of Global Management"
    if "mary lou fulton" in name or "teachers college" in name:
        return "Mary Lou Fulton Teachers College"
    if "new college" in name:
        return "New College of Interdisciplinary Arts and Sciences"
    if "integrative sciences and arts" in name:
        return "College of Integrative Sciences and Arts"
    if "w.p. carey" in name or ("carey" in name and "business" in name):
        return "W.P. Carey School of Business"
    if "cronkite" in name or "journalism" in name:
        return "Walter Cronkite School of Journalism and Mass Communication"
    if "watts" in name or "public service" in name:
        return "Watts College of Public Service and Community Solutions"
    if "university college" in name:
        return "University College"
    return None


def _campus_role_from_opportunity(opp: dict[str, Any]) -> str | None:
    location = _normalize_str(opp.get("currentLocation") or opp.get("locationName"))
    if not location:
        return None

    if "tempe" in location:
        return "Tempe"
    if "downtown" in location and "phoenix" in location:
        return "Downtown Phoenix"
    if "polytechnic" in location:
        return "Polytechnic"
    if "la center" in location or "la centre" in location:
        return "LA Center"
    return None


def role_names_from_student_profile(student_profile: dict[str, Any]) -> set[str]:
    """
    Derive logical role names from a Salesforce student profile payload.

    The returned names correspond to keys in ROLE_ID_MAP.
    """
    roles: set[str] = set()

    opportunities_raw = student_profile.get("opportunities") or []
    if not isinstance(opportunities_raw, list):
        return roles

    opportunities: list[dict[str, Any]] = [
        opp for opp in opportunities_raw if isinstance(opp, dict)
    ]
    if not opportunities:
        return roles

    enrolled_opps = _select_enrolled_opps(opportunities)

    # 1. Term-specific classification for target term (e.g., 2267)
    for opp in enrolled_opps:
        term_code = _normalize_str(opp.get("termCode"))
        if term_code != TARGET_TERM_CODE:
            continue

        career = _normalize_str(opp.get("career"))
        opp_type = _normalize_str(opp.get("type"))

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
        # If the student has any enrolled/admitted graduate opportunity in a
        # non-target term, still classify them as a graduate student.
        for opp in enrolled_opps:
            career = _normalize_str(opp.get("career"))
            if career == "graduate":
                roles.add("Graduate Student")
                has_level_role = True
                break

    if not has_level_role:
        # Otherwise, treat any enrolled/admitted undergraduate in a non-target
        # term as an upperclassman.
        for opp in enrolled_opps:
            term_code = _normalize_str(opp.get("termCode"))
            career = _normalize_str(opp.get("career"))
            if term_code != TARGET_TERM_CODE and career == "undergraduate":
                roles.add("Upperclassmen")
                break

    # 3. International / First-generation based on any enrolled/admitted opportunity
    for opp in enrolled_opps:
        if opp.get("internationalStudent") is not None:
            if bool(opp.get("internationalStudent")) or _normalize_str(
                opp.get("internationalStudent")
            ) in {"true", "yes", "y", "1"}:
                roles.add("International Student")
        if opp.get("firstGeneration") is not None:
            if bool(opp.get("firstGeneration")) or _normalize_str(
                opp.get("firstGeneration")
            ) in {"true", "yes", "y", "1"}:
                roles.add("First Generation Student")

    # 4. College and campus roles, again using any enrolled/admitted opportunity
    for opp in enrolled_opps:
        college_role = _college_role_from_name(opp.get("collegeName"))
        if college_role:
            roles.add(college_role)

        campus_role = _campus_role_from_opportunity(opp)
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
        expected_guild_id = 1187144343400751234
        unverified_role_id = 1207441184218161182
        if guild.id != expected_guild_id:
            logger.debug(
                "VerificationCog invoked for guild %s (expected %s)",
                guild.id,
                expected_guild_id,
            )
            return None
        return guild.get_role(unverified_role_id)

    async def _remove_verified_role(
        self,
        guild: Optional[discord.Guild],
        member: discord.Member,
        *,
        reason: str,
    ) -> bool:
        role = self._get_verified_role(guild)
        if role is None:
            logger.info(
                "No configured verified role available when processing member %s",
                member.id,
            )
            return False
        if role not in member.roles:
            logger.info(
                "Member %s does not currently have the verified role %s",
                member.id,
                role.id,
            )
            return False
        try:
            await member.remove_roles(role, reason=reason)
        except discord.HTTPException as exc:  # pragma: no cover - network failure
            logger.warning(
                "Failed to remove verified role %s from member %s: %s",
                role.id,
                member.id,
                exc,
            )
            return False

        logger.info("Removed verified role %s from member %s", role.id, member.id)
        return True

    async def _remove_unverified_role(
        self,
        guild: Optional[discord.Guild],
        member: discord.Member,
        *,
        reason: str,
    ) -> bool:
        role = self._get_unverified_role(guild)
        if role is None:
            logger.info(
                "No configured unverified role available when processing member %s",
                member.id,
            )
            return False
        if role not in member.roles:
            logger.info(
                "Member %s does not currently have the unverified role %s",
                member.id,
                role.id,
            )
            return False
        try:
            await member.remove_roles(role, reason=reason)
        except discord.HTTPException as exc:  # pragma: no cover - network failure
            logger.warning(
                "Failed to remove unverified role %s from member %s: %s",
                role.id,
                member.id,
                exc,
            )
            return False

        logger.info(
            "Removed unverified role %s from member %s", role.id, member.id
        )
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

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Track when a linked Discord user joins the guild."""
        if member.guild.id != self.guild_id:
            return

        with session_scope() as session:
            user = (
                session.query(User)
                .filter(User.discord_user_id == str(member.id))
                .one_or_none()
            )
            if user is None:
                return

            user.joined_at = datetime.utcnow()
            user.left_at = None

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        """Track when a linked Discord user leaves the guild."""
        if member.guild.id != self.guild_id:
            return

        with session_scope() as session:
            user = (
                session.query(User)
                .filter(User.discord_user_id == str(member.id))
                .one_or_none()
            )
            if user is None:
                return

            user.left_at = datetime.utcnow()

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
        member: Option(discord.Member, "Member to verify"),
    ) -> None:
        """Assign the verification role to a member."""
        if ctx.guild_id != self.guild_id or ctx.guild is None:
            await ctx.respond(
                "This command is only available in the Devil2Devil server.",
                ephemeral=True,
            )
            return

        role = self._get_verified_role(ctx.guild)
        if role is None:
            await ctx.respond(
                "Unable to locate the configured verification role for this server."
            )
            return

        if role in member.roles:
            await ctx.respond(f"{member.mention} already has the verification role.")
            return

        reason = f"Manual verification by {ctx.author}"
        await member.add_roles(role, reason=reason)

        await self._remove_unverified_role(ctx.guild, member, reason=reason)

        await ctx.respond(f"{member.mention} has been marked as verified. ✅")

    async def verify_member_by_id(
        self, user_id: int, *, asurite: str | None = None
    ) -> None:
        """Assign the verified role to a Discord user identified by ID."""
        await self.bot.wait_until_ready()

        guild = self.bot.get_guild(self.guild_id)
        if guild is None:
            try:
                guild = await self.bot.fetch_guild(self.guild_id)
            except discord.HTTPException as exc:  # pragma: no cover - network failure
                raise RuntimeError(
                    "Unable to load the Discord guild for verification"
                ) from exc

        if guild is None:
            raise RuntimeError("Discord guild is not available for verification")

        role = self._get_verified_role(guild)
        if role is None:
            raise RuntimeError("Configured verification role could not be found")

        member = guild.get_member(user_id)
        if member is None:
            try:
                member = await guild.fetch_member(user_id)
            except discord.NotFound as exc:
                raise RuntimeError(
                    f"Discord user {user_id} is not a member of the guild"
                ) from exc
            except discord.HTTPException as exc:  # pragma: no cover - network failure
                raise RuntimeError("Unable to load Discord member information") from exc

        if role in member.roles:
            logger.info("Member %s already has the verification role", user_id)
            return

        reason = "Automatic verification"
        if asurite:
            reason = f"{reason} for {asurite}"

        await member.add_roles(role, reason=reason)

        await self._remove_unverified_role(guild, member, reason=reason)

        logger.info(
            "Assigned verification role to Discord user %s (ASURITE: %s)",
            user_id,
            asurite,
        )

    async def assign_roles_from_profile(
        self, user_id: int, student_profile: dict[str, Any]
    ) -> None:
        """Assign additional Discord roles for a user based on Salesforce data."""
        await self.bot.wait_until_ready()

        guild = self.bot.get_guild(self.guild_id)
        if guild is None:
            try:
                guild = await self.bot.fetch_guild(self.guild_id)
            except discord.HTTPException as exc:  # pragma: no cover - network failure
                raise RuntimeError(
                    "Unable to load the Discord guild for role assignment"
                ) from exc

        if guild is None:
            raise RuntimeError("Discord guild is not available for role assignment")

        member = guild.get_member(user_id)
        if member is None:
            try:
                member = await guild.fetch_member(user_id)
            except discord.NotFound as exc:
                raise RuntimeError(
                    f"Discord user {user_id} is not a member of the guild"
                ) from exc
            except discord.HTTPException as exc:  # pragma: no cover - network failure
                raise RuntimeError("Unable to load Discord member information") from exc

        logical_role_names = role_names_from_student_profile(student_profile)
        if not logical_role_names:
            logger.info(
                "No additional roles derived from Salesforce profile for user %s",
                user_id,
            )
            return

        roles_to_add: list[discord.Role] = []
        for logical_name in sorted(logical_role_names):
            role_id = ROLE_ID_MAP.get(logical_name)
            if role_id is None:
                logger.debug("No configured Discord role id for %s", logical_name)
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

        if not roles_to_add:
            logger.info(
                "No new Discord roles to assign for user %s from Salesforce profile",
                user_id,
            )
            return

        reason = "Automatic Salesforce-based role assignment"
        asurite = student_profile.get("asurite")
        if isinstance(asurite, str) and asurite:
            reason = f"{reason} for {asurite}"

        await member.add_roles(*roles_to_add, reason=reason)

        logger.info(
            "Assigned Salesforce-based roles %s to Discord user %s",
            [r.id for r in roles_to_add],
            user_id,
        )

    @slash_command(
        **_moderation_command_kwargs(
            "unverify", "Remove the verification role from a member."
        )
    )
    async def unverify_member(
        self,
        ctx: discord.ApplicationContext,
        member: Option(discord.Member, "Member to unverify"),
    ) -> None:
        """Remove the verification role from a member."""
        if ctx.guild_id != self.guild_id or ctx.guild is None:
            await ctx.respond(
                "This command is only available in the Devil2Devil server.",
                ephemeral=True,
            )
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
            "ban",
            "Ban an ASURITE from verification and remove their verification role.",
        )
    )
    async def ban_asurite(
        self,
        ctx: discord.ApplicationContext,
        asurite: Option(str, "ASURITE ID to ban"),
    ) -> None:
        """Ban an ASURITE from verification and revoke their Discord access."""
        if ctx.guild_id != self.guild_id or ctx.guild is None:
            await ctx.respond(
                "This command is only available in the Devil2Devil server.",
                ephemeral=True,
            )
            return

        target = (asurite or "").strip()
        if not target:
            await ctx.respond("Please provide an ASURITE to ban.", ephemeral=True)
            return

        await ctx.defer(ephemeral=True)

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
            removed = await self._remove_verified_role(
                ctx.guild,
                member,
                reason=f"Verification ban by {ctx.author}",
            )
            if removed:
                notes.append(
                    f"Removed verification role from linked account {member.mention}."
                )
            else:
                notes.append(
                    "No verification role changes were required for the linked account."
                )
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
        if ctx.guild_id != self.guild_id:
            await ctx.respond(
                "This command is only available in the Devil2Devil server.",
                ephemeral=True,
            )
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

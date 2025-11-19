from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

import discord
from discord.commands import slash_command
from discord.ext import commands

try:  # pragma: no cover - optional dependency
    from .forklift_qna import ForkmanQNA
except ImportError:  # pragma: no cover - optional dependency
    ForkmanQNA = None  # type: ignore[assignment]


from utils.database import QnaModule, QnaPost, session_scope
from utils.settings import CONFIG, DISCORD_CONFIG

logger = logging.getLogger(__name__)

DEFAULT_COMMAND_STATE = {"qna-enable": True, "qna-disable": True}
SATISFACTORY_CUSTOM_ID = "qna:satisfied"
ASSISTANCE_CUSTOM_ID = "qna:assist"
TEST_GUILD_IDS: list[int] = []
if DISCORD_CONFIG and DISCORD_CONFIG.test_guild_ids:
    TEST_GUILD_IDS = list(DISCORD_CONFIG.test_guild_ids)


def _moderation_command_kwargs(name: str, description: str) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "name": name,
        "description": description,
        "dm_permission": False,
        "default_member_permissions": discord.Permissions(manage_guild=True),
    }
    if TEST_GUILD_IDS:
        kwargs["guild_ids"] = TEST_GUILD_IDS
    return kwargs


def _normalize_id(raw: Optional[str]) -> Optional[int]:
    if not raw:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        logger.warning("Invalid Discord snowflake configured: %s", raw)
        return None
class QnACog(commands.Cog):
    """Cog that mirrors Forkman Q&A functionality with Bedrock knowledge base responses."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.forum_channel_id = _normalize_id(CONFIG.QNA_FORUM_CHANNEL_ID)
        self.helper_role_id = _normalize_id(CONFIG.QNA_HELPER_ROLE_ID)
        self.knowledge_base_id = CONFIG.QNA_KNOWLEDGE_BASE_ID
        self.model_arn = CONFIG.QNA_MODEL_ARN
        self.aws_region = CONFIG.QNA_AWS_REGION
        self.aws_access_key_id = CONFIG.AWS_ACCESS_KEY_ID
        self.aws_secret_access_key = CONFIG.AWS_SECRET_ACCESS_KEY
        self._enabled_cache: dict[int, bool] = {}
        self._active_views: set[QnAFeedbackView] = set()

    def _is_ready(self) -> bool:
        return bool(
            self.forum_channel_id
            and self.knowledge_base_id
            and self.model_arn
            and ForkmanQNA
        )

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if not self._is_ready():
            logger.info(
                "QnACog loaded but incomplete configuration prevents automation "
                "(channel: %s, knowledge_base: %s, model: %s, forkman_available: %s)",
                self.forum_channel_id,
                bool(self.knowledge_base_id),
                bool(self.model_arn),
                bool(ForkmanQNA),
            )
            return

        forum_channel = (
            self.bot.get_channel(self.forum_channel_id)
            if self.forum_channel_id
            else None
        )
        if isinstance(forum_channel, discord.ForumChannel):
            logger.info(
                "QnACog monitoring Q&A forum channel %s (%s).",
                forum_channel.id,
                forum_channel.name,
            )
        else:
            logger.warning(
                "QnACog could not locate the configured forum channel id %s.",
                self.forum_channel_id,
            )

    @slash_command(
        **_moderation_command_kwargs("qna-enable", "Enable the AI Q&A assistant")
    )
    async def qna_enable(self, ctx: discord.ApplicationContext) -> None:
        if not ctx.guild_id:
            await ctx.respond(
                "This command can only be used inside a Discord server.", ephemeral=True
            )
            return

        guild_id = ctx.guild_id
        enabled = True
        changed = False
        commands_json = json.dumps(DEFAULT_COMMAND_STATE)
        with session_scope() as db_session:
            module = (
                db_session.query(QnaModule)
                .filter_by(guild_id=str(guild_id))
                .one_or_none()
            )
            if module is None:
                module = QnaModule(
                    guild_id=str(guild_id),
                    enabled=enabled,
                    commands=commands_json,
                    config="{}",
                )
                db_session.add(module)
                changed = True
            else:
                changed = module.enabled != enabled
                module.enabled = enabled
                if not module.commands:
                    module.commands = commands_json
        self._enabled_cache[guild_id] = enabled
        message = (
            "Q&A assistant enabled for this server."
            if changed
            else "Q&A assistant is already enabled."
        )
        if not self._is_ready():
            message += " (Note: configuration is incomplete, so responses may not be generated yet.)"
        await ctx.respond(message, ephemeral=True)

    @slash_command(
        **_moderation_command_kwargs("qna-disable", "Disable the AI Q&A assistant")
    )
    async def qna_disable(self, ctx: discord.ApplicationContext) -> None:
        if not ctx.guild_id:
            await ctx.respond(
                "This command can only be used inside a Discord server.", ephemeral=True
            )
            return

        guild_id = ctx.guild_id
        enabled = False
        changed = False
        commands_json = json.dumps(DEFAULT_COMMAND_STATE)
        with session_scope() as db_session:
            module = (
                db_session.query(QnaModule)
                .filter_by(guild_id=str(guild_id))
                .one_or_none()
            )
            if module is None:
                module = QnaModule(
                    guild_id=str(guild_id),
                    enabled=enabled,
                    commands=commands_json,
                    config="{}",
                )
                db_session.add(module)
                changed = True
            else:
                changed = module.enabled != enabled
                module.enabled = enabled
                if not module.commands:
                    module.commands = commands_json
        self._enabled_cache[guild_id] = enabled
        if changed:
            await ctx.respond("Q&A assistant disabled for this server.", ephemeral=True)
        else:
            await ctx.respond("Q&A assistant is already disabled.", ephemeral=True)

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread) -> None:
        if (
            not self._is_ready()
            or thread.guild is None
            or not self._is_enabled(thread.guild.id)
            or thread.parent_id != self.forum_channel_id
        ):
            return
        starter_message = await self._fetch_starter_message(thread)
        author_id = starter_message.author.id if starter_message else None
        if author_id is not None and starter_message and starter_message.author:
            if starter_message.author.bot:
                return
        message = (
            f"Hi <@{author_id}>, I'm Forkman, your friendly support bot. "
            "I'm looking through our knowledge base to see if I can answer your question. :wave:"
        )
        await thread.send(message)
        thread_title = thread.name.strip()
        question_text = (
            (starter_message.content or "").strip() if starter_message else ""
        )
        result = await self._generate_answer(
            thread_title=thread_title,
            question_text=question_text,
            author_id=author_id,
        )
        if not result:
            failure = (
                "Uh oh, I couldn't find an answer to your question. "
                "Please try again later or ping a moderator."
            )
            await thread.send(failure)
            return

        if not result.get("ok"):
            await thread.send(
                result.get(
                    "full_message",
                    "Uh oh, I couldn't find an answer to your question. Please try again later.",
                )
            )
            return

        answer_text = result.get("answer") or result.get("full_message")
        if not answer_text:
            answer_text = (
                "I wasn't able to craft a response, please try again or ping a moderator."
            )
        rating_prompt = result.get("rating_prompt")
        if rating_prompt:
            answer_text = f"{answer_text}\n\n{rating_prompt}"
        await thread.send(answer_text, view=QnAFeedbackView(self))

    async def handle_feedback(
        self,
        interaction: discord.Interaction,
        *,
        status: str,
        view: Optional[QnAFeedbackView] = None,
        ping_helper: bool = False,
    ) -> None:
        if not self._is_enabled(interaction.guild_id):
            await interaction.response.send_message(
                "The Q&A assistant is currently disabled.", ephemeral=True
            )
            return

        if ping_helper:
            if self.helper_role_id:
                message = f"<@&{self.helper_role_id}> Assistance requested."
            else:
                message = ""
            await interaction.response.send_message(message)
        else:
            await interaction.response.send_message(
                "Thank you for your feedback!", ephemeral=True
            )

        await self._finalize_feedback(interaction, status=status, view=view)

    async def _finalize_feedback(
        self,
        interaction: discord.Interaction,
        *,
        status: str,
        view: Optional[QnAFeedbackView],
    ) -> None:
        thread_id = str(interaction.channel_id)
        user_id = interaction.user.id if interaction.user else None

        with session_scope() as db_session:
            record = (
                db_session.query(QnaPost).filter_by(thread_id=thread_id).one_or_none()
            )
            if record is not None:
                record.status = status
                if user_id:
                    record.last_feedback_user_id = str(user_id)
                record.last_feedback_at = discord.utils.utcnow()

        try:
            await interaction.message.edit(embed=None, view=None)
        except discord.HTTPException:
            logger.warning(
                "Failed to clear feedback components for message %s",
                interaction.message.id,
            )
        if view:
            view.stop()
            self._active_views.discard(view)

    async def _fetch_starter_message(
        self, thread: discord.Thread
    ) -> Optional[discord.Message]:
        try:
            return await thread.fetch_message(thread.id)
        except discord.NotFound:
            logger.debug("Starter message not found for thread %s", thread.id)
        except discord.HTTPException:
            logger.warning("Unable to fetch starter message for thread %s", thread.id)
        return None

    def _build_forkman_kwargs(self) -> Optional[dict[str, Any]]:
        return ForkmanQNA(
            region_name=self.aws_region,
            knowledge_base_id=self.knowledge_base_id,
            model_arn=self.model_arn,
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key,
        )

    async def _generate_answer(
        self,
        *,
        thread_title: str,
        question_text: str,
        author_id: Optional[int],
    ) -> Optional[dict[str, Any]]:
        qna = ForkmanQNA(
            region_name=self.aws_region,
            knowledge_base_id=self.knowledge_base_id,
            model_arn=self.model_arn,
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key,
        )
        if not qna:
            return None
        answer = qna.get_answer(
            thread_title=thread_title,
            message_content=question_text,
            user_id=str(author_id) if author_id else None,
        )

        return answer["response"] if answer["ok"] else None


    def _is_enabled(self, guild_id: Optional[int]) -> bool:
        if guild_id is None:
            return False

        cached = self._enabled_cache.get(guild_id)
        if cached is not None:
            return cached

        with session_scope() as db_session:
            module = (
                db_session.query(QnaModule)
                .filter_by(guild_id=str(guild_id))
                .one_or_none()
            )
            if module is None:
                module = QnaModule(
                    guild_id=str(guild_id),
                    enabled=False,
                    commands=json.dumps(DEFAULT_COMMAND_STATE),
                    config="{}",
                )
                db_session.add(module)
            enabled = module.enabled

        self._enabled_cache[guild_id] = enabled
        return enabled


class QnAFeedbackView(discord.ui.View):
    """Reusable feedback view that routes interactions back to the cog."""

    def __init__(self, cog: QnACog) -> None:
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="It was great!",
        style=discord.ButtonStyle.success,
        emoji="\N{WHITE HEAVY CHECK MARK}",
        custom_id=SATISFACTORY_CUSTOM_ID,
    )
    async def handle_satisfied(  # type: ignore[override]
        self,
        _: discord.ui.Button,
        interaction: discord.Interaction,
    ) -> None:
        await self.cog.handle_feedback(
            interaction,
            status="satisfied",
            view=self,
        )

    @discord.ui.button(
        label="I still need help...",
        style=discord.ButtonStyle.danger,
        emoji="\N{SQUARED SOS}",
        custom_id=ASSISTANCE_CUSTOM_ID,
    )
    async def handle_assistance(  # type: ignore[override]
        self,
        _: discord.ui.Button,
        interaction: discord.Interaction,
    ) -> None:
        await self.cog.handle_feedback(
            interaction,
            status="needs_help",
            view=self,
            ping_helper=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(QnACog(bot))

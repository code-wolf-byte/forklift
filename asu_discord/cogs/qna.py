from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

import discord
from discord.commands import slash_command
from discord.ext import commands

try:  # pragma: no cover - optional dependency
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError
except ImportError:  # pragma: no cover - optional dependency
    boto3 = None  # type: ignore[assignment]

    class BotoCoreError(Exception):
        """Fallback boto core error."""

    class ClientError(Exception):
        """Fallback boto client error."""


from utils.database import QnaModule, QnaPost, session_scope
from utils.settings import CONFIG, DISCORD_CONFIG

logger = logging.getLogger(__name__)

DEFAULT_COMMAND_STATE = {"qna-enable": True, "qna-disable": True}
SATISFACTORY_CUSTOM_ID = "qna:satisfied"
ASSISTANCE_CUSTOM_ID = "qna:assist"
INITIAL_GREETING = (
    "Hi {user}, I'm Forklift, your friendly support bot. "
    "I'm looking through our knowledge base to see if I can answer your question. :wave:"
)
FEEDBACK_DESCRIPTION = (
    "We're still improving our answers! Please rate the quality of the answer below."
)

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

class FeedbackButtons(discord.ui.View):
    
    @discord.ui.button(label="It was great!", style=discord.ButtonStyle.success, emoji="👍")
    async def satisfied_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.send_message("Thank you for your feedback!")

    @discord.ui.button(label="I still need help...", style=discord.ButtonStyle.danger, emoji="👎")
    async def needs_help_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.send_message("<@1213199035968528434> Assistance requested.")
class QnACog(commands.Cog):
    """Cog that mirrors Forkman Q&A functionality with Bedrock knowledge base responses."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.forum_channel_id = _normalize_id(CONFIG.QNA_FORUM_CHANNEL_ID)
        self.helper_role_id = _normalize_id(CONFIG.QNA_HELPER_ROLE_ID)
        self.knowledge_base_id = CONFIG.QNA_KNOWLEDGE_BASE_ID
        self.model_arn = CONFIG.QNA_MODEL_ARN
        self.aws_region = CONFIG.QNA_AWS_REGION
        self._enabled_cache: dict[int, bool] = {}
        self._active_views: set[QnAFeedbackView] = set()
        self._bedrock_client = boto3.client("bedrock-agent-runtime", region_name=self.aws_region, aws_access_key_id=CONFIG.AWS_ACCESS_KEY_ID, aws_secret_access_key=CONFIG.AWS_SECRET_ACCESS_KEY)
                                            

    def _build_bedrock_client(self):
        if boto3 is None:
            logger.warning("boto3 is not installed; QnA responses will be disabled.")
            return None
        if not self.knowledge_base_id:
            logger.info(
                "QNA_KNOWLEDGE_BASE_ID missing; Bedrock client will not be created."
            )
            return None
        try:
            kwargs = {"region_name": self.aws_region} if self.aws_region else {}
            return boto3.client("bedrock-agent-runtime", **kwargs)
        except Exception:  # pragma: no cover - defensive
            logger.exception("Failed to create Bedrock Agent Runtime client.")
            return None

    def _is_ready(self) -> bool:
        return bool(
            self.forum_channel_id and self.knowledge_base_id and self._bedrock_client
        )

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if not self._is_ready():
            logger.info(
                "QnACog loaded but incomplete configuration prevents automation "
                "(channel: %s, knowledge_base: %s, client_ready: %s)",
                self.forum_channel_id,
                bool(self.knowledge_base_id),
                bool(self._bedrock_client),
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
            
        message = f"Hi <@{author_id}>, I'm Forkman, your friendly support bot. I'm looking through our knowledge base to see if I can answer your question. :wave:"
        await thread.send(message)
        thread_title = thread.name.strip()
        question_text = ((starter_message.content or "").strip() if starter_message else "")
        query = f"{thread_title}\n{question_text}".strip()
        answer = await self.answer_question(thread_title=thread_title, question_text=question_text)
        if not answer:
            failure = "Uh oh, I couldn't find an answer to your question. Please try again later or ping a moderator."
            await thread.send(failure)
        else:
            await thread.send(answer, view=QnAFeedbackView(self))

    def answer_question(self, thread_title: str, question_text: str) -> Optional[str]:
        query = f"{thread_title}\n{question_text}".strip()
        
        try:
            response = self._bedrock_client.retrieve_and_generate(
                input={"text": query},
                retrieveAndGenerateConfiguration={
                    "type": "KNOWLEDGE_BASE",
                    "knowledgeBaseConfiguration": {
                        "modelArn": self.model_arn,
                        "knowledgeBaseId": self.knowledge_base_id,
                    },
                },
            )
            return response.get("output", {}).get("text")
        except Exception as e:
            logger.error("Error generating answer: %s", e)
            return None

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

    async def _generate_answer(self, query: str) -> Optional[str]:
        if not query or not self._bedrock_client or not self.knowledge_base_id:
            return None

        def _call_bedrock() -> Optional[str]:
            try:
                response = self._bedrock_client.retrieve_and_generate(
                    input={"text": query},
                    retrieveAndGenerateConfiguration={
                        "type": "KNOWLEDGE_BASE",
                        "knowledgeBaseConfiguration": {
                            "modelArn": self.model_arn,
                            "knowledgeBaseId": self.knowledge_base_id,
                        },
                    },
                )
            except (BotoCoreError, ClientError) as exc:
                logger.error("Bedrock retrieve_and_generate failed: %s", exc)
                return None

            output = response.get("output") if isinstance(response, dict) else None
            if not output:
                return None
            return output.get("text")

        return await asyncio.to_thread(_call_bedrock)

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

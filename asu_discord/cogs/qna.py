from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import discord
from discord.commands import slash_command
from discord.ext import commands

try:  # pragma: no cover - optional dependency
    from .forklift_qna import ForkmanQNA
except ImportError:  # pragma: no cover - optional dependency
    ForkmanQNA = None  # type: ignore[assignment]

from utils.database import GoldGuideContribution, QnaModule, QnaPost, session_scope
from utils.settings import CONFIG, DISCORD_CONFIG

logger = logging.getLogger(__name__)

DEFAULT_COMMAND_STATE = {"qna-enable": True, "qna-disable": True}
SATISFACTORY_CUSTOM_ID = "qna:satisfied"
ASSISTANCE_CUSTOM_ID = "qna:assist"
GOLD_GUIDE_ROLE_ID = 1187156709597270157
GOLD_GUIDE_TAG_SUBSTRING = "gold guide"
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
        self._backfill_task: Optional[asyncio.Task] = None
        self._backfill_progress: dict = {
            "status": "idle",
            "threads_total": 0,
            "threads_processed": 0,
            "posts_upserted": 0,
            "contributions_inserted": 0,
            "started_at": None,
            "completed_at": None,
            "error": None,
        }

    def _is_ready(self) -> bool:
        return bool(
            self.forum_channel_id
            and self.knowledge_base_id
            and self.model_arn
            and ForkmanQNA
        )

    @property
    def backfill_running(self) -> bool:
        return self._backfill_task is not None and not self._backfill_task.done()

    def start_backfill(self) -> bool:
        """Schedule a backfill task on the bot's event loop. Returns False if already running."""
        if self.backfill_running:
            logger.info("QnACog: backfill already running — ignoring request")
            return False
        logger.info("QnACog: scheduling QnA backfill task")
        self._backfill_task = asyncio.ensure_future(self._run_backfill())
        return True

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if not self.forum_channel_id:
            logger.info(
                "QnACog loaded but incomplete configuration prevents automation "
                "(channel: %s, knowledge_base: %s, model: %s, forkman_available: %s)",
                self.forum_channel_id,
                bool(self.knowledge_base_id),
                bool(self.model_arn),
                bool(ForkmanQNA),
            )
            return

        forum_channel = self.bot.get_channel(self.forum_channel_id)
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

        # Auto-backfill QnaPost records and Gold Guide contributions on each startup.
        # The backfill is idempotent — threads already in the DB are skipped quickly.
        self.start_backfill()

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

    # ── Backfill ─────────────────────────────────────────────────────────────

    @staticmethod
    def _backfill_has_feedback_buttons(msg: discord.Message) -> bool:
        for row in msg.components:
            for component in row.children:
                if getattr(component, "custom_id", None) in (
                    SATISFACTORY_CUSTOM_ID, ASSISTANCE_CUSTOM_ID
                ):
                    return True
        return False

    @staticmethod
    async def _classify_thread_for_backfill(
        thread: discord.Thread, bot_id: int, gold_guide_ids: set[int]
    ) -> dict:
        """Scan thread history once; return status, answer info, and GG messages."""
        result: dict = {
            "status": "no_bot_msg",
            "answer_text": None,
            "assistant_msg_id": None,
            "gold_guide_msgs": [],  # list of (msg_id, author_id, author_name, created_at)
        }
        messages: list[discord.Message] = []
        try:
            async for msg in thread.history(limit=None, oldest_first=True):
                messages.append(msg)
        except Exception as exc:
            logger.warning("Could not read thread %s: %s", thread.id, exc)
            return result

        for msg in messages:
            if msg.author.id == bot_id:
                if "Assistance requested" in msg.content:
                    result["status"] = "needs_help"
                elif QnACog._backfill_has_feedback_buttons(msg):
                    if result["status"] not in ("needs_help",):
                        result["status"] = "pending"
                    if result["assistant_msg_id"] is None:
                        result["assistant_msg_id"] = str(msg.id)
                        result["answer_text"] = msg.content or None
                else:
                    if result["assistant_msg_id"] is None and "Hi <@" not in msg.content:
                        result["assistant_msg_id"] = str(msg.id)
                        result["answer_text"] = msg.content or None
                    if result["status"] == "no_bot_msg":
                        result["status"] = "satisfied"
            elif msg.author.id in gold_guide_ids:
                result["gold_guide_msgs"].append((
                    str(msg.id),
                    str(msg.author.id),
                    msg.author.name,
                    msg.created_at.replace(tzinfo=None),
                ))
        return result

    async def _run_backfill(self) -> None:
        p = self._backfill_progress
        p.update({
            "status": "running",
            "threads_total": 0,
            "threads_processed": 0,
            "posts_upserted": 0,
            "contributions_inserted": 0,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
            "error": None,
        })

        try:
            guild_id = int(DISCORD_CONFIG.guild_id) if DISCORD_CONFIG and DISCORD_CONFIG.guild_id else None
            if not guild_id:
                raise RuntimeError("DISCORD_CONFIG.guild_id is not set")
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                raise RuntimeError(f"Guild not found in cache")

            forum_channel = guild.get_channel(self.forum_channel_id)
            if not isinstance(forum_channel, discord.ForumChannel):
                raise RuntimeError(f"QnA forum channel {self.forum_channel_id} not found or wrong type")

            # Build Gold Guide member ID set
            gold_guide_role = guild.get_role(GOLD_GUIDE_ROLE_ID)
            gold_guide_ids: set[int] = set()
            if gold_guide_role:
                gold_guide_ids = {m.id for m in gold_guide_role.members}
            logger.info("QnA backfill: Gold Guide members found: %d", len(gold_guide_ids))

            tag_name_by_id = {t.id: t.name for t in forum_channel.available_tags}

            # Collect all threads (archived + active)
            seen: dict[int, discord.Thread] = {}
            async for thread in forum_channel.archived_threads(limit=None):
                seen[thread.id] = thread
            for thread in forum_channel.threads:
                seen[thread.id] = thread
            all_threads = list(seen.values())
            p["threads_total"] = len(all_threads)
            logger.info("QnA backfill: processing %d threads", len(all_threads))

            bot_id = self.bot.user.id

            for thread in all_threads:
                tag_names = [tag_name_by_id.get(t.id, str(t.id)) for t in thread.applied_tags]
                has_gg_tag = any(GOLD_GUIDE_TAG_SUBSTRING in n.lower() for n in tag_names)
                created_at = thread.created_at.replace(tzinfo=None) if thread.created_at else datetime.utcnow()

                # Check if already fully backfilled (has tags set)
                with session_scope() as db_session:
                    record = db_session.query(QnaPost).filter_by(thread_id=str(thread.id)).one_or_none()
                    already_done = record is not None and record.tags is not None

                if already_done:
                    # Still scan for any new Gold Guide messages not yet recorded
                    with session_scope() as db_session:
                        existing_msg_ids = {
                            r.message_id
                            for r in db_session.query(GoldGuideContribution.message_id)
                            .filter_by(thread_id=str(thread.id))
                            .all()
                        }
                    if not gold_guide_ids:
                        p["threads_processed"] += 1
                        continue
                    try:
                        async for msg in thread.history(limit=None, oldest_first=True):
                            if msg.author.id in gold_guide_ids and str(msg.id) not in existing_msg_ids:
                                with session_scope() as db_session:
                                    if not db_session.query(GoldGuideContribution).filter_by(message_id=str(msg.id)).one_or_none():
                                        db_session.add(GoldGuideContribution(
                                            guild_id=str(guild.id),
                                            channel_id=str(forum_channel.id),
                                            channel_name=forum_channel.name,
                                            thread_id=str(thread.id),
                                            thread_title=thread.name,
                                            message_id=str(msg.id),
                                            responder_discord_id=str(msg.author.id),
                                            responder_username=msg.author.name,
                                            responded_at=msg.created_at.replace(tzinfo=None),
                                        ))
                                        p["contributions_inserted"] += 1
                    except Exception as exc:
                        logger.warning("Could not scan GG messages for thread %s: %s", thread.id, exc)
                    p["threads_processed"] += 1
                    continue

                info = await self._classify_thread_for_backfill(thread, bot_id, gold_guide_ids)

                with session_scope() as db_session:
                    record = db_session.query(QnaPost).filter_by(thread_id=str(thread.id)).one_or_none()
                    if record is None:
                        db_session.add(QnaPost(
                            guild_id=str(guild.id),
                            channel_id=str(forum_channel.id),
                            thread_id=str(thread.id),
                            title=thread.name,
                            tags=json.dumps(tag_names),
                            status=info["status"],
                            answer=info["answer_text"],
                            assistant_message_id=info["assistant_msg_id"],
                            gold_guide_pinged=has_gg_tag,
                            created_at=created_at,
                        ))
                    else:
                        if record.tags is None:
                            record.tags = json.dumps(tag_names)
                        if record.status in (None, "pending") and info["status"] != "no_bot_msg":
                            record.status = info["status"]
                        if record.answer is None and info["answer_text"]:
                            record.answer = info["answer_text"]
                        if record.assistant_message_id is None and info["assistant_msg_id"]:
                            record.assistant_message_id = info["assistant_msg_id"]
                        if not record.gold_guide_pinged and has_gg_tag:
                            record.gold_guide_pinged = True
                    p["posts_upserted"] += 1

                    for msg_id, author_id, author_name, responded_at in info["gold_guide_msgs"]:
                        if not db_session.query(GoldGuideContribution).filter_by(message_id=msg_id).one_or_none():
                            db_session.add(GoldGuideContribution(
                                guild_id=str(guild.id),
                                channel_id=str(forum_channel.id),
                                channel_name=forum_channel.name,
                                thread_id=str(thread.id),
                                thread_title=thread.name,
                                message_id=msg_id,
                                responder_discord_id=author_id,
                                responder_username=author_name,
                                responded_at=responded_at,
                            ))
                            p["contributions_inserted"] += 1

                p["threads_processed"] += 1

            p["status"] = "done"
            p["completed_at"] = datetime.now(timezone.utc).isoformat()
            logger.info(
                "QnA backfill complete: %d posts upserted, %d contributions inserted",
                p["posts_upserted"], p["contributions_inserted"],
            )

        except Exception as exc:
            logger.exception("QnA backfill failed: %s", exc)
            p["status"] = "failed"
            p["error"] = str(exc)
            p["completed_at"] = datetime.now(timezone.utc).isoformat()

    # ── Thread lifecycle ──────────────────────────────────────────────────────

    @staticmethod
    def _get_tag_names(thread: discord.Thread) -> list[str]:
        return [tag.name for tag in thread.applied_tags]

    @staticmethod
    def _has_gold_guide_tag(thread: discord.Thread) -> bool:
        return any(
            GOLD_GUIDE_TAG_SUBSTRING in tag.name.lower()
            for tag in thread.applied_tags
        )

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

        tag_names = self._get_tag_names(thread)
        question_text = (starter_message.content or "").strip() if starter_message else ""

        # Create initial QnaPost record
        with session_scope() as db_session:
            if not db_session.query(QnaPost).filter_by(thread_id=str(thread.id)).one_or_none():
                db_session.add(QnaPost(
                    guild_id=str(thread.guild.id),
                    channel_id=str(thread.parent_id),
                    thread_id=str(thread.id),
                    owner_id=str(author_id) if author_id else None,
                    title=thread.name,
                    question=question_text,
                    tags=json.dumps(tag_names),
                    status="pending",
                ))

        await thread.send(
            f"Hi <@{author_id}>, I'm Forkman, your friendly support bot. "
            "I'm looking through our knowledge base to see if I can answer your question. :wave:"
        )

        thread_title = thread.name.strip()
        result = await self._generate_answer(
            thread_title=thread_title,
            question_text=question_text,
            author_id=author_id,
        )

        answer_msg = None
        if not result:
            await thread.send(
                "Uh oh, I couldn't find an answer to your question. "
                "Please try again later or ping a moderator."
            )
        elif not result.get("ok"):
            if result.get("retries_exhausted"):
                await thread.send(
                    f"<@{author_id}> I tried 3 times but wasn't able to get an answer to your question. "
                    "A staff member has been notified and will follow up shortly.",
                    allowed_mentions=discord.AllowedMentions(users=True),
                )
                await thread.send(
                    f"<@689510313971810437> Forkman failed to answer after 3 attempts in this thread.",
                    allowed_mentions=discord.AllowedMentions(users=True),
                )
            else:
                await thread.send(
                    result.get(
                        "full_message",
                        "Uh oh, I couldn't find an answer to your question. Please try again later.",
                    )
                )
        else:
            answer_text = result.get("answer") or result.get("full_message")
            if not answer_text:
                answer_text = "I wasn't able to craft a response, please try again or ping a moderator."
            rating_prompt = result.get("rating_prompt")
            if rating_prompt:
                answer_text = f"{answer_text}\n\n{rating_prompt}"
            answer_msg = await thread.send(answer_text, view=QnAFeedbackView(self))

        # Store answer details in DB
        if answer_msg and result and result.get("ok"):
            with session_scope() as db_session:
                record = db_session.query(QnaPost).filter_by(thread_id=str(thread.id)).one_or_none()
                if record is not None:
                    record.answer = result.get("answer") or result.get("full_message")
                    record.assistant_message_id = str(answer_msg.id)

        # Ping Gold Guides if the thread carries a Gold Guide tag
        if self._has_gold_guide_tag(thread):
            await thread.send(
                f"<@&{GOLD_GUIDE_ROLE_ID}> A question tagged for Gold Guide assistance has been posted!",
                allowed_mentions=discord.AllowedMentions(roles=True),
            )
            with session_scope() as db_session:
                record = db_session.query(QnaPost).filter_by(thread_id=str(thread.id)).one_or_none()
                if record is not None:
                    record.gold_guide_pinged = True

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Record a contribution whenever a Gold Guide member posts in a QnA thread."""
        if message.author.bot:
            return
        if not isinstance(message.channel, discord.Thread):
            return
        if message.channel.parent_id != self.forum_channel_id:
            return
        if not isinstance(message.author, discord.Member):
            return
        if not any(r.id == GOLD_GUIDE_ROLE_ID for r in message.author.roles):
            return

        thread = message.channel
        parent_name: str | None = thread.parent.name if thread.parent else None

        with session_scope() as db_session:
            if not db_session.query(GoldGuideContribution).filter_by(message_id=str(message.id)).one_or_none():
                db_session.add(GoldGuideContribution(
                    guild_id=str(message.guild.id) if message.guild else None,
                    channel_id=str(thread.parent_id),
                    channel_name=parent_name,
                    thread_id=str(thread.id),
                    thread_title=thread.name,
                    message_id=str(message.id),
                    responder_discord_id=str(message.author.id),
                    responder_username=message.author.name,
                    responded_at=message.created_at.replace(tzinfo=None),
                ))

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
                role = discord.utils.get(
                    interaction.guild.roles, id=self.helper_role_id
                )
                message = (
                    f"{role.mention} Assistance requested."
                    if role
                    else "Assistance requested."
                )
            else:
                message = ""
            await interaction.response.send_message(
                message,
                allowed_mentions=discord.AllowedMentions(roles=True),
            )
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

        max_attempts = 3
        response = None
        for attempt in range(1, max_attempts + 1):
            response = qna.get_answer(
                thread_title=thread_title,
                message_content=question_text,
                user_id=str(author_id) if author_id else None,
            )
            logger.info(f"Answer from ForkmanQNA (attempt {attempt}): {response}")
            if response["ok"]:
                logger.info(
                    "Generated answer for thread '%s' (author: %s) on attempt %d",
                    thread_title,
                    author_id,
                    attempt,
                )
                del qna
                return response
            logger.warning(
                "Failed to generate answer for thread '%s' (author: %s), attempt %d/%d: %s",
                thread_title,
                author_id,
                attempt,
                max_attempts,
                response.get("full_message"),
            )
            if attempt < max_attempts:
                await asyncio.sleep(2)

        del qna
        response["retries_exhausted"] = True
        return response

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

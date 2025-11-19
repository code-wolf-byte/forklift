import logging
import os
from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)


class ForkmanQNA:
    def __init__(
        self,
        knowledge_base_id: str,
        model_arn: str,
        region_name: Optional[str] = None,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        aws_session_token: Optional[str] = None,
    ) -> None:
        """
        :param knowledge_base_id: Your Bedrock Knowledge Base ID.
        :param model_arn: The Bedrock model ARN
                          (e.g. "arn:aws:bedrock:us-east-1::foundation-model/us.anthropic.claude-3-5-sonnet-20241022-v2:0").
        :param region_name: AWS region (e.g. "us-east-1"). If None, uses default from env/config.
        """
        self.knowledge_base_id = knowledge_base_id
        self.model_arn = model_arn
        self.region_name = region_name
        self.aws_access_key_id = aws_access_key_id
        self.aws_secret_access_key = aws_secret_access_key
        self.aws_session_token = aws_session_token

        self.client = boto3.client(
            "bedrock-agent-runtime",
            region_name=region_name,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            aws_session_token=aws_session_token,
        )

    @staticmethod
    def build_query(thread_title: str, message_content: str) -> str:
        """
        Matches the Go logic: channel.Name + " " + msg.Content
        """
        query = f"{thread_title} {message_content}".strip()
        logger.debug(
            "Built ForkmanQNA query (thread=%s, length=%s)", thread_title, len(query)
        )
        return query

    def get_answer(
        self,
        thread_title: str,
        message_content: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Call Bedrock retrieve_and_generate and return a structured result.

        :param thread_title: Equivalent to the Discord thread name.
        :param message_content: The actual user question/content.
        :param user_id: Optional user ID to mention in the greeting (e.g. Discord user ID).
        :param session_id: Optional session ID for multi-turn; if not provided a new one is generated.
        :return: dict with keys:
            - ok: bool
            - full_message: str (greeting + separator + answer OR error message)
            - greeting: str
            - answer: Optional[str]
            - rating_prompt: Optional[str]
            - raw_response: Optional[dict] (Bedrock raw response when successful)
        """
        query = self.build_query(thread_title, message_content)
        logger.debug(
            "Submitting query to Bedrock (thread=%s, user=%s, session=%s)",
            thread_title,
            user_id,
            session_id,
        )

        kb_config: Dict[str, Any] = {"knowledgeBaseId": self.knowledge_base_id}
        if self.model_arn:
            kb_config["modelArn"] = self.model_arn

        try:
            response = self.client.retrieve_and_generate(
                input={"text": query},
                retrieveAndGenerateConfiguration={
                    "type": "KNOWLEDGE_BASE",
                    "knowledgeBaseConfiguration": kb_config,
                },
            )
            self.client = None
            self.client = boto3.client(
                "bedrock-agent-runtime",
                region_name=self.region_name,
                aws_access_key_id=self.aws_access_key_id,
                aws_secret_access_key=self.aws_secret_access_key,
                aws_session_token=self.aws_session_token,
            )

            logger.debug(
                "Bedrock retrieve_and_generate succeeded (kb=%s, model=%s)",
                self.knowledge_base_id,
                self.model_arn,
            )
        except (BotoCoreError, ClientError) as e:
            logger.exception(
                "Bedrock retrieve_and_generate failed (kb=%s, model=%s)",
                self.knowledge_base_id,
                self.model_arn,
            )
            error_msg = (
                "Uh oh, I couldn't find an answer to your question. "
                f"An error occurred contacting Bedrock: {e}"
            )
            return {
                "ok": False,
                "full_message": error_msg,
                "answer": None,
                "rating_prompt": None,
                "raw_response": None,
            }

        output = (response or {}).get("output") or {}
        answer_text = output.get("text")

        if not answer_text:
            logger.info(
                "Bedrock response did not include answer text (thread=%s, user=%s)",
                thread_title,
                user_id,
            )
            error_msg = (
                "Uh oh, I couldn't find an answer to your question. Please try again later."
            )
            return {
                "ok": False,
                "full_message": error_msg,
                "answer": None,
                "rating_prompt": None,
                "raw_response": response,
            }

        full_message = "\n----------------------\n" + answer_text
        rating_prompt = (
            "We're still improving our answers! Please rate the quality of the answer."
        )
        logger.debug(
            "Returning ForkmanQNA answer (thread=%s, user=%s, chars=%s)",
            thread_title,
            user_id,
            len(answer_text),
        )

        return {
            "ok": True,
            "full_message": full_message,
            "answer": answer_text,
            "rating_prompt": rating_prompt,
            "raw_response": response,
        }


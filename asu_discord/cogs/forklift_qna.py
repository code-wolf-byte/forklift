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
    def _extract_citation_links(response: Dict[str, Any]) -> list[str]:
        """Extract unique source URLs from Bedrock citations, preserving order."""
        seen: set[str] = set()
        urls: list[str] = []
        for citation in (response or {}).get("citations", []):
            for ref in citation.get("retrievedReferences", []):
                location = ref.get("location") or {}
                url = (location.get("webLocation") or {}).get("url")
                if url and url not in seen:
                    seen.add(url)
                    urls.append(url)
        return urls

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

        kb_config: Dict[str, Any] = {
            "knowledgeBaseId": self.knowledge_base_id,
            "generationConfiguration": {
                "promptTemplate": {
                    "textPromptTemplate": (
                        "You are Forkman, a helpful Q&A assistant for the Devil2Devil Discord server about Arizona State University.\n"
                        "Answer questions as Forkman and not the model that is mention I or me instead of the model\n"
                        "Answer the question using ONLY the information in the search results below Follow the following rules about answering questions:\n\n"
                        "## Tone\n\n"
                        "* Be friendly, welcoming, and supportive.\n"
                        "* Use a conversational tone that feels like a helpful student mentor.\n"
                        "* Be direct, clear, and sincere.\n"
                        "* Stay positive and encouraging without sounding overly enthusiastic or robotic.\n"
                        "* Avoid corporate, formal, or overly academic language.\n\n"
                        "## Response Structure\n\n"
                        "* Answer the user's question as directly as possible.\n"
                        "* Keep responses concise and easy to scan.\n"
                        "* Use short paragraphs and bullet points when helpful.\n"
                        "* Break up long explanations into smaller sections.\n"
                        "* Prioritize the most important information first.\n"
                        "* Start your answers with the helpful information and recommendations\n"
                        "* The tone should be  ambitious, bold, visionary, inspiring, aspirational, optimistic, determined, future-focused, authoritative, leading the way, strong, active, capable, committed, purposeful, and honest.\n"
                        "## Things to Avoid\n\n"
                        "* Do not mention searching, retrieving, or looking through a knowledge base.\n"
                        "* Do not say \"I don't know.\"\n"
                        "* Do not reference internal systems, documents, databases, or sources.\n"
                        "* Do not mention search results to the user, assume you are talking to a friend\n"
                        "* Avoid filler phrases such as:\n\n"
                        "  * \"Based on the information available...\"\n"
                        "  * \"According to the knowledge base...\"\n"
                        "  * \"After reviewing the documentation...\"\n"
                        "* Avoid overly long responses unless the user asks for detailed information.\n\n"
                        "## Formatting\n\n"
                        "* Use plain language.\n"
                        "* Keep sentences relatively short.\n"
                        "* Use lists for steps, requirements, or options.\n"
                        "* Make information easy to read on mobile devices.\n\n"
                        "## Fallback\n"
                        "If you cannot answer the question do not be direct, explain the query that the user persisits and then follow the following: \n"
                        "- If you cannot answer the question - direct the user contact us form https://admission.asu.edu/contact\n"
                        "- If you cannot answer the question and the question and had key words about financial aid, scholarships, payments or money, direct them use contact us form https://tuition.asu.edu/contact\n"
                        "- If you cannot answer the question and the question and had key words about housing, roommates, room assignments, and dorms, and direct them use contact us form https://housing.asu.edu/contact-us\n\n"
                        "$search_results$\n\n"
                        "Using the information from above search results to provide answer to user's question. In your answer make sure to first quote the images (by mentioning image title or image ID) from which you can identify relevant information, then followed by your reasoning steps and answer.\n\n"
                        "$output_format_instructions$\n\n"
                        "Here is the user's query:\n$query$"
                    )
                }
            },
        }
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
            # Detect model access / marketplace subscription errors specifically
            error_code = getattr(e, "response", {}).get("Error", {}).get("Code", "")
            error_detail = str(e)
            if "aws-marketplace" in error_detail or "ModelAccess" in error_detail or (
                error_code == "ValidationException" and "not authorized" in error_detail
            ):
                user_msg = (
                    "Uh oh, I couldn't find an answer to your question. "
                    "The AI model is currently unavailable — please try again later or ping a moderator."
                )
            else:
                user_msg = (
                    "Uh oh, I couldn't find an answer to your question. "
                    "Please try again later or ping a moderator."
                )
            return {
                "ok": False,
                "full_message": user_msg,
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

        citation_links = self._extract_citation_links(response)
        if citation_links:
            sources_block = "\n\n**Sources:**\n" + "\n".join(
                f"- [{url}](<{url}>)" for url in citation_links
            )
            answer_text = answer_text + sources_block

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


import logging
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

CREATEAI_QUERY_URL = "https://api-main-beta.aiml.asu.edu/query"
DEFAULT_TIMEOUT = 60
RATING_PROMPT = (
    "We're still improving our answers! Please rate the quality of the answer."
)

SYSTEM_PROMPT = (
    "You are Forkman, a helpful Q&A assistant for the Devil2Devil Discord server about Arizona State University.\n"
    "Answer questions as Forkman and not the model that is mention I or me instead of the model\n"
    "Answer the question using ONLY the information in the knowledge base. Follow the following rules about answering questions:\n\n"
    "## Tone\n\n"
    "* Be friendly, welcoming, and supportive.\n"
    "* Use a conversational tone that feels like a helpful student mentor.\n"
    "* Be direct, clear, and sincere.\n"
    "* Stay positive and encouraging without sounding overly enthusiastic or robotic.\n"
    "* Avoid corporate, formal, or overly academic language.\n\n"
    "## Response Structure\n\n"
    "* Answer the user's question as directly as possible.\n"
    "* Keep responses concise and easy to scan: under about 150 words unless the user asks for more detail.\n"
    "* For follow-up questions, answer only what is new; do not repeat earlier answers.\n"
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
    "- If you cannot answer the question and the question and had key words about housing, roommates, room assignments, and dorms, and direct them use contact us form https://housing.asu.edu/contact-us\n"
)


class ForkmanQNA:
    def __init__(self, token: str, url: str = CREATEAI_QUERY_URL) -> None:
        """
        :param token: CreateAI project service token.
        :param url: CreateAI query endpoint.
        """
        self.token = token.strip()
        self.url = url

    @staticmethod
    def build_query(
        thread_title: str,
        message_content: str,
        history: Optional[List[Tuple[str, str]]] = None,
    ) -> str:
        """
        Matches the Go logic: channel.Name + " " + msg.Content.
        With history, earlier (speaker, text) turns are prepended as a transcript.
        """
        query = f"{thread_title} {message_content}".strip()
        if history:
            transcript = "\n\n".join(f"{speaker}: {text}" for speaker, text in history)
            query = (
                f"Conversation so far:\n{transcript}\n\n"
                f"Answer the user's latest message:\n{query}"
            )
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
        history: Optional[List[Tuple[str, str]]] = None,
    ) -> Dict[str, Any]:
        """
        Query CreateAI and return a structured result.

        :param thread_title: Equivalent to the Discord thread name.
        :param message_content: The actual user question/content.
        :param user_id: Optional user ID, used for logging.
        :param session_id: Optional session ID, used for logging.
        :param history: Optional earlier (speaker, text) turns of the conversation.
        :return: dict with keys:
            - ok: bool
            - full_message: str (separator + answer OR error message)
            - answer: Optional[str]
            - rating_prompt: Optional[str]
            - raw_response: Optional[dict] (CreateAI raw response when one was received)
        """
        query = self.build_query(thread_title, message_content, history)
        logger.debug(
            "Submitting query to CreateAI (thread=%s, user=%s, session=%s)",
            thread_title,
            user_id,
            session_id,
        )

        try:
            resp = requests.post(
                self.url,
                json={"query": query, "model_params": {"system_prompt": SYSTEM_PROMPT}},
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json",
                },
                timeout=DEFAULT_TIMEOUT,
            )
            resp.raise_for_status()
            response = resp.json()
        except (requests.RequestException, ValueError):
            logger.exception("CreateAI query failed (thread=%s)", thread_title)
            return {
                "ok": False,
                "full_message": (
                    "Uh oh, I couldn't find an answer to your question. "
                    "Please try again later or ping a moderator."
                ),
                "answer": None,
                "rating_prompt": None,
                "raw_response": None,
            }

        answer_text = (response or {}).get("response")

        if not answer_text:
            logger.info(
                "CreateAI response did not include answer text (thread=%s, user=%s)",
                thread_title,
                user_id,
            )
            return {
                "ok": False,
                "full_message": (
                    "Uh oh, I couldn't find an answer to your question. Please try again later."
                ),
                "answer": None,
                "rating_prompt": None,
                "raw_response": response,
            }

        full_message = "\n----------------------\n" + answer_text
        rating_prompt = RATING_PROMPT
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

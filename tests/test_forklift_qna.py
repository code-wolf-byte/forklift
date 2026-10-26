"""Tests for asu_discord/cogs/forklift_qna.py — mocked CreateAI HTTP."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import requests

from asu_discord.cogs.forklift_qna import CREATEAI_QUERY_URL, ForkmanQNA

POST = "asu_discord.cogs.forklift_qna.requests.post"
TOK = "tok\n"


def _resp(payload) -> MagicMock:
    resp = MagicMock(spec=requests.Response)
    resp.json.return_value = payload
    return resp


def test_token_is_stripped():
    assert ForkmanQNA(TOK).token == "tok"


def test_build_query():
    assert ForkmanQNA.build_query("Housing", "  when?  ") == "Housing   when?"
    assert ForkmanQNA.build_query("", "hi") == "hi"


def test_success_sends_query_and_returns_answer():
    with patch(POST, return_value=_resp({"response": "Tempe!"})) as mock_post:
        result = ForkmanQNA(TOK).get_answer("Campus", "where is ASU?")

    assert result["ok"] is True
    assert result["answer"] == "Tempe!"
    assert result["full_message"].endswith("Tempe!")
    assert result["rating_prompt"]
    assert result["raw_response"] == {"response": "Tempe!"}

    args, kwargs = mock_post.call_args
    assert args[0] == CREATEAI_QUERY_URL
    assert kwargs["json"]["query"] == "Campus where is ASU?"
    assert kwargs["headers"]["Authorization"] == "Bearer tok"
    assert kwargs["timeout"]


def test_http_error_returns_failure():
    resp = _resp({})
    resp.raise_for_status.side_effect = requests.HTTPError("401")
    with patch(POST, return_value=resp):
        result = ForkmanQNA(TOK).get_answer("t", "q")

    assert result["ok"] is False
    assert result["answer"] is None
    assert result["raw_response"] is None
    assert "Uh oh" in result["full_message"]


def test_network_error_returns_failure():
    with patch(POST, side_effect=requests.ConnectionError("down")):
        assert ForkmanQNA(TOK).get_answer("t", "q")["ok"] is False


def test_invalid_json_returns_failure():
    resp = _resp(None)
    resp.json.side_effect = ValueError("not json")
    with patch(POST, return_value=resp):
        assert ForkmanQNA(TOK).get_answer("t", "q")["ok"] is False


def test_empty_answer_returns_failure_with_raw_response():
    with patch(POST, return_value=_resp({"response": ""})):
        result = ForkmanQNA(TOK).get_answer("t", "q")

    assert result["ok"] is False
    assert result["raw_response"] == {"response": ""}


def test_build_query_with_history():
    query = ForkmanQNA.build_query(
        "Housing", "which campus?", [("User", "when?"), ("Forkman", "August.")]
    )
    assert "User: when?\n\nForkman: August." in query
    assert query.endswith("Housing which campus?")


def test_history_is_sent_to_createai():
    with patch(POST, return_value=_resp({"response": "Tempe"})) as mock_post:
        ForkmanQNA(TOK).get_answer("t", "q", history=[("User", "hi")])
    assert "User: hi" in mock_post.call_args.kwargs["json"]["query"]

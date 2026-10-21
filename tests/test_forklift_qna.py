"""ForkmanQNA tool loop, asu.edu filtering and source handling, with AWS stubbed out."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from asu_discord.cogs.forklift_qna import ForkmanQNA

GATEWAY = "https://gw-123.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp"


def make_qna() -> ForkmanQNA:
    return ForkmanQNA(
        gateway_url=GATEWAY,
        model_arn="test-model",
        region_name="us-west-2",
        aws_access_key_id="AKIDTEST",
        aws_secret_access_key="secret",
    )


def converse_reply(content: list[dict], stop: str) -> dict:
    return {"output": {"message": {"role": "assistant", "content": content}}, "stopReason": stop}


def test_search_filters_to_asu_and_parses_sse():
    qna = make_qna()
    assert qna.gateway_region == "us-east-1"
    payload = {"results": [
        {"url": "https://tuition.asu.edu/cost", "title": "Cost", "text": "..."},
        {"url": "https://example.com/asu-tuition", "title": "Blog", "text": "..."},
        {"url": "https://notasu.edu/x", "title": "Lookalike", "text": "..."},
    ]}
    sse = "event: message\ndata: " + json.dumps(
        {"jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": json.dumps(payload)}]}}
    )
    with patch("asu_discord.cogs.forklift_qna.requests.post") as post:
        post.return_value = MagicMock(status_code=200, text=sse)
        results = qna.search_asu("tuition")

    assert [r["url"] for r in results] == ["https://tuition.asu.edu/cost"]
    sent = json.loads(post.call_args.kwargs["data"])
    assert sent["params"]["name"] == "web-search-tool___WebSearch"
    assert "Authorization" in post.call_args.kwargs["headers"]  # SigV4 signed


def test_answer_loop_cites_only_pages_it_was_shown():
    qna = make_qna()
    qna.client = MagicMock()
    qna.client.converse.side_effect = [
        converse_reply([{"toolUse": {"toolUseId": "t1", "name": "search_asu", "input": {"query": "tuition"}}}], "tool_use"),
        converse_reply([{"text": "Tuition is $X.\nSOURCES: https://tuition.asu.edu/cost https://made-up.asu.edu/fake"}], "end_turn"),
    ]
    qna.search_asu = MagicMock(return_value=[{"url": "https://tuition.asu.edu/cost", "text": "..."}])

    result = qna.get_answer("Tuition?", "How much is tuition?")

    assert result["ok"]
    assert result["answer"].startswith("Tuition is $X.")
    assert "SOURCES:" not in result["answer"]
    assert "https://tuition.asu.edu/cost" in result["answer"]
    assert "made-up.asu.edu" not in result["answer"]
    # tool result went back to the model, then the loop stopped
    tool_msg = qna.client.converse.call_args.kwargs["messages"][2]
    assert tool_msg["content"][0]["toolResult"]["toolUseId"] == "t1"


def test_search_failure_is_reported_to_model_not_raised():
    qna = make_qna()
    qna.client = MagicMock()
    qna.client.converse.side_effect = [
        converse_reply([{"toolUse": {"toolUseId": "t1", "name": "search_asu", "input": {"query": "x"}}}], "tool_use"),
        converse_reply([{"text": "Please use https://admission.asu.edu/contact\nSOURCES:"}], "end_turn"),
    ]
    qna.search_asu = MagicMock(side_effect=RuntimeError("boom"))

    result = qna.get_answer("Q", "q")

    assert result["ok"]
    tool_result = qna.client.converse.call_args.kwargs["messages"][2]["content"][0]["toolResult"]
    assert tool_result["status"] == "error"
    assert "**Sources:**" not in result["answer"]


def test_converse_error_returns_not_ok():
    qna = make_qna()
    qna.client = MagicMock()
    qna.client.converse.side_effect = RuntimeError("throttled")

    result = qna.get_answer("Q", "q")

    assert not result["ok"]
    assert result["full_message"]

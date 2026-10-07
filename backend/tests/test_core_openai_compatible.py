import json
from types import SimpleNamespace
from typing import Any

import httpx2 as httpx
import openai
import pytest

from kredpare.core.cases.llm import InvalidModelOutput, LLMUnavailable
from kredpare.core.cases.openai_compatible import OpenAICompatibleClient
from kredpare.core.cases.workflow import WorkflowExplanation

VALID = {
    "cause": "accrued_interest_error",
    "wrong_side": "counterparty",
    "candidate_id": "c1",
    "citations": ["amendment-1 §4.2"],
    "proposal": "email",
    "confidence": 0.9,
    "reasoning": "r",
}


def _reply(content: str | None, finish_reason: str = "stop") -> Any:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(message=SimpleNamespace(content=content), finish_reason=finish_reason)
        ],
        usage=SimpleNamespace(prompt_tokens=1200, completion_tokens=80),
    )


def _status_error(status: int, retry_after: str | None = None) -> openai.APIStatusError:
    headers = {"retry-after": retry_after} if retry_after else {}
    response = httpx.Response(status, headers=headers, request=httpx.Request("POST", "http://x"))
    return openai.APIStatusError("boom", response=response, body=None)


class StubOpenAI:
    """Each queued item is returned or, when it is an exception, raised."""

    def __init__(self, *queue: Any) -> None:
        self.requests: list[dict[str, Any]] = []
        self._queue = list(queue)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
        item = self._queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _client(stub: StubOpenAI, sleeps: list[float] | None = None, **kwargs: Any):
    return OpenAICompatibleClient(
        api_key="k",
        base_url="http://x",
        client=stub,
        sleep=(sleeps if sleeps is not None else []).append,
        **kwargs,
    )


def _complete(client: OpenAICompatibleClient):
    return client.complete(model="m", system="sys", user="usr", schema=WorkflowExplanation)


def test_valid_reply_is_parsed_with_usage() -> None:
    result = _complete(_client(StubOpenAI(_reply(json.dumps(VALID)))))

    assert result.parsed.candidate_id == "c1"
    assert (result.input_tokens, result.output_tokens, result.retries) == (1200, 80, 0)
    assert result.latency_seconds >= 0


def test_request_asks_for_a_strict_json_schema() -> None:
    stub = StubOpenAI(_reply(json.dumps(VALID)))

    _complete(_client(stub))

    request = stub.requests[0]
    assert request["model"] == "m"
    fmt = request["response_format"]
    assert fmt["type"] == "json_schema"
    assert fmt["json_schema"]["strict"] is True
    assert fmt["json_schema"]["schema"]["properties"]["confidence"]
    assert request["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "usr"},
    ]


def test_json_object_mode_is_available_for_providers_without_json_schema() -> None:
    stub = StubOpenAI(_reply(json.dumps(VALID)))

    _complete(_client(stub, json_schema=False))

    assert stub.requests[0]["response_format"] == {"type": "json_object"}


@pytest.mark.parametrize(
    ("content", "finish_reason", "message"),
    [
        ("not json", "stop", "does not match the schema"),
        (json.dumps({**VALID, "confidence": 7}), "stop", "confidence"),
        (json.dumps({**VALID, "extra": 1}), "stop", "extra"),
        (json.dumps(VALID), "length", "truncated"),
        ("", "stop", "empty reply"),
        (None, "stop", "empty reply"),
    ],
)
def test_bad_replies_raise_invalid_output_and_keep_usage(
    content: str | None, finish_reason: str, message: str
) -> None:
    with pytest.raises(InvalidModelOutput, match=message) as raised:
        _complete(_client(StubOpenAI(_reply(content, finish_reason))))

    assert raised.value.input_tokens == 1200
    assert raised.value.output_tokens == 80


def test_429_and_5xx_are_retried_with_exponential_backoff_and_recorded() -> None:
    stub = StubOpenAI(_status_error(429), _status_error(503), _reply(json.dumps(VALID)))
    sleeps: list[float] = []

    result = _complete(_client(stub, sleeps, base_delay=1.0, max_delay=30.0))

    assert result.retries == 2
    assert sleeps == [1.0, 2.0]
    assert len(stub.requests) == 3


def test_backoff_is_capped_and_retry_after_is_honoured() -> None:
    stub = StubOpenAI(
        _status_error(429, retry_after="7"),
        _status_error(500),
        _status_error(500),
        _reply(json.dumps(VALID)),
    )
    sleeps: list[float] = []

    _complete(_client(stub, sleeps, base_delay=1.0, max_delay=2.5))

    # retry-after 7 and the doubling delays 2.0, 4.0 are all capped at 2.5
    assert sleeps == [2.5, 2.0, 2.5]


def test_gives_up_after_the_retry_cap_without_touching_the_break() -> None:
    stub = StubOpenAI(*[_status_error(429) for _ in range(3)])

    with pytest.raises(LLMUnavailable) as raised:
        _complete(_client(stub, max_retries=2))

    assert raised.value.retries == 2
    assert len(stub.requests) == 3


def test_client_errors_other_than_429_are_not_retried() -> None:
    stub = StubOpenAI(_status_error(401))

    with pytest.raises(LLMUnavailable):
        _complete(_client(stub))

    assert len(stub.requests) == 1


def test_invalid_output_after_a_retry_keeps_the_retry_count() -> None:
    stub = StubOpenAI(_status_error(503), _reply("not json"))

    with pytest.raises(InvalidModelOutput) as raised:
        _complete(_client(stub))

    assert raised.value.retries == 1

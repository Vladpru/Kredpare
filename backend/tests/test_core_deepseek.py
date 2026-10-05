import json
from types import SimpleNamespace
from typing import Any

import pytest

from kredpare.core.cases.deepseek import DeepSeekClient
from kredpare.core.cases.llm import InvalidModelOutput
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


class StubOpenAI:
    def __init__(self, content: str | None, finish_reason: str = "stop") -> None:
        self.requests: list[dict[str, Any]] = []
        self._reply = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=content), finish_reason=finish_reason
                )
            ],
            usage=SimpleNamespace(prompt_tokens=1200, completion_tokens=80),
        )
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
        return self._reply


def _complete(stub: StubOpenAI, thinking: bool = False):
    client = DeepSeekClient(api_key="k", base_url="http://x", thinking=thinking, client=stub)
    return client.complete(
        model="deepseek-flash", system="sys", user="usr", schema=WorkflowExplanation
    )


def test_valid_reply_is_parsed_with_usage() -> None:
    stub = StubOpenAI(json.dumps(VALID))

    result = _complete(stub)

    assert result.parsed.candidate_id == "c1"
    assert (result.input_tokens, result.output_tokens) == (1200, 80)
    assert result.latency_seconds >= 0


def test_request_uses_json_mode_schema_in_prompt_and_thinking_off() -> None:
    stub = StubOpenAI(json.dumps(VALID))

    _complete(stub)

    request = stub.requests[0]
    assert request["model"] == "deepseek-flash"
    assert request["response_format"] == {"type": "json_object"}
    assert request["extra_body"] == {"thinking": {"type": "disabled"}}
    assert "json schema" in request["messages"][0]["content"]
    assert request["messages"][1] == {"role": "user", "content": "usr"}


def test_thinking_can_be_enabled() -> None:
    stub = StubOpenAI(json.dumps(VALID))

    _complete(stub, thinking=True)

    assert stub.requests[0]["extra_body"] == {"thinking": {"type": "enabled"}}


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
        _complete(StubOpenAI(content, finish_reason))

    assert raised.value.input_tokens == 1200
    assert raised.value.output_tokens == 80

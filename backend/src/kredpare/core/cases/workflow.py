"""The workflow level of the cascade: one LLM call that explains a break from the agreements.

Generic: no domain words. A domain supplies a `WorkflowSpec` (documents, candidate values, prompt).
Code precomputes the candidates, the model chooses one and cites clauses, and CODE decides the
status. The model never outputs an amount that code trusts.
"""

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session

from kredpare.core.audit import record_event
from kredpare.core.cases.llm import (
    MODEL_PRICES,
    InvalidModelOutput,
    LLMClient,
    ModelPrice,
    cost_usd,
)

DEFAULT_CONFIDENCE_THRESHOLD = 0.7
UNKNOWN_CAUSE = "unknown"
NO_SUPPORTED_CANDIDATE = "no_supported_candidate"


class WorkflowStatus(StrEnum):
    EXPLAINED = "explained"
    NEEDS_INVESTIGATION = "needs_investigation"


class WorkflowExplanation(BaseModel):
    """What the model returns. Validated, never repaired."""

    model_config = ConfigDict(extra="forbid")

    cause: str
    wrong_side: Literal["seller", "counterparty", "unknown"]
    candidate_id: str = Field(
        description="Id of the candidate that reproduces the counterparty value, or empty."
    )
    citations: list[str]
    proposal: Literal["correction", "email", "none"]
    confidence: float = Field(ge=0, le=1)
    reasoning: str


@dataclass(frozen=True)
class WorkflowBreak:
    counterparty_id: str
    field: str
    seller_value: object
    counterparty_value: object
    seller_record: Mapping[str, object]
    counterparty_record: Mapping[str, object]


@dataclass(frozen=True)
class WorkflowDocument:
    id: str
    effective_date: date
    text: str


@dataclass(frozen=True)
class Prompt:
    system: str
    user: str


class WorkflowSpec(Protocol):
    """What a domain provides. Candidates are JSON-safe mappings.

    Every candidate has `id` (str), `reproduces_counterparty_value` (bool) and `supported_by`
    (list of citations of the clauses that state exactly that candidate's parameters).
    """

    @property
    def prompt_version(self) -> str: ...

    @property
    def causes(self) -> Sequence[str]: ...

    def load_documents(self, counterparty_id: str) -> Sequence[WorkflowDocument]: ...

    def build_candidates(
        self, brk: WorkflowBreak, documents: Sequence[WorkflowDocument]
    ) -> Sequence[Mapping[str, Any]]: ...

    def render_prompt(
        self,
        brk: WorkflowBreak,
        documents: Sequence[WorkflowDocument],
        candidates: Sequence[Mapping[str, Any]],
    ) -> Prompt: ...

    def citation_exists(self, citation: str, documents: Sequence[WorkflowDocument]) -> bool: ...


@dataclass(frozen=True)
class WorkflowUsage:
    model: str
    prompt_version: str
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal
    latency_seconds: float
    cached: bool
    """True when served from the local cache: tokens, cost, and latency are those of the
    original call, and nothing was spent now."""
    retries: int = 0
    """Requests repeated after a 429, 5xx, or connection error."""
    llm_called: bool = True
    """False when code decided without asking the model: tokens, cost, and latency are zero."""


@dataclass(frozen=True)
class WorkflowResult:
    status: WorkflowStatus
    reasons: list[str]
    explanation: WorkflowExplanation | None
    candidates: list[dict[str, Any]]
    usage: WorkflowUsage
    prompt_hash: str
    raw_output_error: str | None = field(default=None)


class ResponseCache:
    """Model replies on disk, keyed by the input hash, so eval reruns are free."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def get(self, key: str) -> dict[str, Any] | None:
        path = self._directory / f"{key}.json"
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def put(self, key: str, value: dict[str, Any]) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)
        (self._directory / f"{key}.json").write_text(json.dumps(value), encoding="utf-8")


def input_hash(model: str, prompt_version: str, prompt: Prompt) -> str:
    payload = json.dumps(
        [model, prompt_version, prompt.system, prompt.user], ensure_ascii=False
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def run_workflow(
    spec: WorkflowSpec,
    brk: WorkflowBreak,
    *,
    llm: LLMClient,
    model: str,
    threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    cache: ResponseCache | None = None,
    prices: dict[str, ModelPrice] | None = None,
) -> WorkflowResult:
    """Explain one break. Code, not the model, decides the status.

    When no clause-supported candidate reproduces the counterparty value, the model is not
    called and the cache is not touched: the result is needs_investigation at zero cost.
    """
    price_table = MODEL_PRICES if prices is None else prices
    documents = list(spec.load_documents(brk.counterparty_id))
    candidates = [dict(c) for c in spec.build_candidates(brk, documents)]
    if not _has_supported_candidate(candidates):
        return WorkflowResult(
            WorkflowStatus.NEEDS_INVESTIGATION,
            [NO_SUPPORTED_CANDIDATE],
            None,
            candidates,
            WorkflowUsage(model, spec.prompt_version, 0, 0, Decimal(0), 0.0, False, 0, False),
            "",
        )
    prompt = spec.render_prompt(brk, documents, candidates)
    key = input_hash(model, spec.prompt_version, prompt)

    def usage(
        input_tokens: int, output_tokens: int, latency: float, retries: int, cached: bool
    ) -> WorkflowUsage:
        return WorkflowUsage(
            model=model,
            prompt_version=spec.prompt_version,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd(model, input_tokens, output_tokens, price_table),
            latency_seconds=latency,
            cached=cached,
            retries=retries,
        )

    def result(
        explanation: WorkflowExplanation | None, call_usage: WorkflowUsage, error: str | None
    ) -> WorkflowResult:
        reasons = _reasons(spec, explanation, candidates, documents, threshold, error)
        status = WorkflowStatus.NEEDS_INVESTIGATION if reasons else WorkflowStatus.EXPLAINED
        return WorkflowResult(status, reasons, explanation, candidates, call_usage, key, error)

    hit = cache.get(key) if cache is not None else None
    if hit is not None:
        explanation, error = _from_cache(hit)
        return result(explanation, usage(*hit["usage"], cached=True), error)

    try:
        reply = llm.complete(
            model=model, system=prompt.system, user=prompt.user, schema=WorkflowExplanation
        )
    except InvalidModelOutput as exc:
        call_usage = usage(
            exc.input_tokens, exc.output_tokens, exc.latency_seconds, exc.retries, False
        )
        _store(cache, key, None, exc.detail, call_usage)
        return result(None, call_usage, exc.detail)

    call_usage = usage(
        reply.input_tokens, reply.output_tokens, reply.latency_seconds, reply.retries, False
    )
    _store(cache, key, reply.parsed, None, call_usage)
    return result(reply.parsed, call_usage, None)


def _store(
    cache: ResponseCache | None,
    key: str,
    explanation: WorkflowExplanation | None,
    error: str | None,
    call_usage: WorkflowUsage,
) -> None:
    if cache is None:
        return
    cache.put(
        key,
        {
            "explanation": explanation.model_dump() if explanation else None,
            "error": error,
            "usage": [
                call_usage.input_tokens,
                call_usage.output_tokens,
                call_usage.latency_seconds,
                call_usage.retries,
            ],
        },
    )


def _from_cache(hit: dict[str, Any]) -> tuple[WorkflowExplanation | None, str | None]:
    if hit["explanation"] is None:
        return None, hit["error"]
    try:
        return WorkflowExplanation.model_validate(hit["explanation"]), None
    except ValidationError as exc:
        return None, f"cached reply no longer validates: {exc.error_count()} errors"


def _has_supported_candidate(candidates: Sequence[Mapping[str, Any]]) -> bool:
    """A clause-supported candidate reproduces the counterparty value: the agreements explain it."""
    return any(c["reproduces_counterparty_value"] and c["supported_by"] for c in candidates)


def _reasons(
    spec: WorkflowSpec,
    explanation: WorkflowExplanation | None,
    candidates: list[dict[str, Any]],
    documents: Sequence[WorkflowDocument],
    threshold: float,
    error: str | None,
) -> list[str]:
    """Why the break is not explained. Empty means the explanation stands."""
    if explanation is None:
        return [f"invalid_model_output: {error}"]
    reasons: list[str] = []
    if explanation.confidence < threshold:
        reasons.append(f"confidence {explanation.confidence} is below threshold {threshold}")
    if explanation.cause == UNKNOWN_CAUSE or explanation.cause not in spec.causes:
        reasons.append(f"cause {explanation.cause!r} is unknown or outside the vocabulary")
    cited = next((c for c in candidates if c["id"] == explanation.candidate_id), None)
    if cited is None:
        reasons.append(f"candidate {explanation.candidate_id!r} does not exist")
    elif not (cited["reproduces_counterparty_value"] and cited["supported_by"]):
        reasons.append(
            f"candidate {explanation.candidate_id!r} does not reproduce the counterparty value"
            " with clause support"
        )
    if explanation.wrong_side == "unknown" or explanation.proposal == "none":
        reasons.append("no actionable proposal: wrong side or proposal is not decided")
    if not explanation.citations:
        reasons.append("no citations")
    reasons.extend(
        f"citation {citation!r} does not exist in the documents"
        for citation in explanation.citations
        if not spec.citation_exists(citation, documents)
    )
    return reasons


def audit_payload(result: WorkflowResult) -> dict[str, Any]:
    """What the audit event records about the call. No prompt text, no record values."""
    usage = asdict(result.usage)
    usage["cost_usd"] = str(result.usage.cost_usd)
    return {
        **usage,
        "prompt_hash": result.prompt_hash,
        "status": result.status.value,
        "reasons": result.reasons,
    }


def record_workflow_call(
    session: Session, result: WorkflowResult, *, break_id: str, actor: str = "workflow"
) -> None:
    """Write the call to the audit log in the caller's transaction."""
    record_event(
        session,
        actor,
        "workflow_llm_call",
        "break",
        break_id,
        audit_payload(result),
    )

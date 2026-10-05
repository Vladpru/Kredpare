from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from kredpare.core.cases.workflow import Prompt, WorkflowBreak, WorkflowDocument
from kredpare.domains.lending.agreement_documents import (
    AGREEMENTS_DIR,
    AgreementDocument,
    citation_exists,
    load_agreements,
)
from kredpare.domains.lending.candidates import LoanTerms, build_candidates
from kredpare.domains.lending.workflow.prompt import CAUSES, PROMPT_VERSION, render_prompt


def _date(value: object) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def _agreements(
    counterparty_id: str, documents: Sequence[WorkflowDocument]
) -> list[AgreementDocument]:
    return [
        AgreementDocument(counterparty_id, d.id, d.effective_date, None, "", d.text)
        for d in documents
    ]


class LendingWorkflowSpec:
    """Lending's WorkflowSpec: agreement loader, candidate builder, prompt, cause vocabulary."""

    prompt_version = PROMPT_VERSION
    causes: Sequence[str] = CAUSES

    def __init__(self, agreements_root: Path = AGREEMENTS_DIR) -> None:
        self._root = agreements_root

    def load_documents(self, counterparty_id: str) -> Sequence[WorkflowDocument]:
        return [
            WorkflowDocument(d.document, d.effective_date, d.body)
            for d in load_agreements(counterparty_id, self._root)
        ]

    def build_candidates(
        self, brk: WorkflowBreak, documents: Sequence[WorkflowDocument]
    ) -> Sequence[Mapping[str, Any]]:
        record = brk.company_record
        loan = LoanTerms(
            upb=Decimal(str(record["upb"])),
            note_rate=Decimal(str(record["note_rate"])),
            funding_date=_date(record["funding_date"]),
            cut_off_date=_date(record["cut_off_date"]),
            settlement_date=_date(record["settlement_date"]),
            credit_tier=str(record["credit_tier"]),
        )
        candidates = build_candidates(
            brk.field,
            loan,
            _agreements(brk.counterparty_id, documents),
            Decimal(str(brk.company_value)),
            Decimal(str(brk.counterparty_value)),
        )
        return [c.to_json() for c in candidates]

    def render_prompt(
        self,
        brk: WorkflowBreak,
        documents: Sequence[WorkflowDocument],
        candidates: Sequence[Mapping[str, Any]],
    ) -> Prompt:
        return render_prompt(brk, documents, candidates)

    def citation_exists(self, citation: str, documents: Sequence[WorkflowDocument]) -> bool:
        return citation_exists(citation, _agreements("", documents))

"""Cited clause text for the API: "<document> §<number>" to the section body."""

import re
from functools import lru_cache

from kredpare.domains.lending.agreement_documents import (
    AgreementDocument,
    load_agreements,
    parse_sections,
)

_CITATION = re.compile(r"^(\S+) §(\d+(?:\.\d+)*)$")


@lru_cache(maxsize=128)
def _documents(counterparty_id: str) -> tuple[AgreementDocument, ...]:
    return tuple(load_agreements(counterparty_id))


def resolve_clause(counterparty_id: str, citation: str) -> str | None:
    match = _CITATION.match(citation.strip())
    if match is None:
        return None
    name, number = match.groups()
    for document in _documents(counterparty_id):
        if document.document == name:
            section = parse_sections(document.body).get(number)
            if section is not None:
                return section.text
    return None

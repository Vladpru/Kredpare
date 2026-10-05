"""The agreement documents must back every citation the generator can emit."""

import re
from datetime import date, timedelta
from pathlib import Path

import pytest
from kredpare.domains import lending

from kredpare_datagen import agreements

AGREEMENTS_DIR = Path(lending.__file__).parent / "agreements"
DOCUMENTS = ("base", "amendment-1", "amendment-2")
_HEADING = re.compile(r"^#{2,6}\s+§(\d+(?:\.\d+)*)\s", re.MULTILINE)
_SCAN_START = date(2026, 1, 1)
_SCAN_END = date(2026, 12, 31)


def _read(counterparty_id: str, document: str) -> tuple[dict[str, str], set[str]]:
    path = AGREEMENTS_DIR / counterparty_id / f"{document}.md"
    text = path.read_text(encoding="utf-8")
    match = re.match(r"---\n(.*?)\n---\n(.*)", text, re.DOTALL)
    assert match, f"{path} has no front matter"
    front: dict[str, str] = {}
    for line in match.group(1).splitlines():
        key, _, value = line.partition(":")
        front[key.strip()] = value.strip().strip('"')
    sections = set(_HEADING.findall(match.group(2) + "\n"))
    return front, sections


def _emitted_citations(counterparty_id: str) -> set[str]:
    citations = {agreements.ROUNDING_CITATION}
    day = _SCAN_START
    while day <= _SCAN_END:
        terms = agreements.terms_in_force(counterparty_id, day)
        citations.update((terms.pricing_citation, terms.accrual_citation))
        day += timedelta(days=1)
    return citations


@pytest.mark.parametrize("counterparty_id", agreements.BUYERS)
@pytest.mark.parametrize("document", DOCUMENTS)
def test_front_matter(counterparty_id: str, document: str) -> None:
    front, sections = _read(counterparty_id, document)
    assert front["counterparty_id"] == counterparty_id
    assert front["document"] == document
    assert front["title"]
    date.fromisoformat(front["effective_date"])
    assert sections, "document has no numbered sections"


@pytest.mark.parametrize("counterparty_id", agreements.BUYERS)
def test_every_emitted_citation_resolves_to_a_heading(counterparty_id: str) -> None:
    citations = _emitted_citations(counterparty_id)
    assert len(citations) > 1
    for citation in sorted(citations):
        document, _, section = citation.partition(" §")
        assert document in DOCUMENTS, citation
        _, sections = _read(counterparty_id, document)
        assert section in sections, f"{counterparty_id}: {citation} has no heading"


@pytest.mark.parametrize("counterparty_id", agreements.BUYERS)
def test_effective_dates_match_the_generator(counterparty_id: str) -> None:
    _, versions = agreements._AGREEMENTS[counterparty_id]
    expected = {"base": agreements._BASE_EFFECTIVE}
    expected.update({version.label: version.effective for version in versions})
    for document in DOCUMENTS:
        front, _ = _read(counterparty_id, document)
        actual = date.fromisoformat(front["effective_date"])
        if document in expected:
            assert actual == expected[document], f"{counterparty_id} {document}"
        else:
            # The generator needs no entry for an amendment that changes nothing it models.
            assert actual > agreements._BASE_EFFECTIVE

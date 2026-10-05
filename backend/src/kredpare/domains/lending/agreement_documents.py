"""Load the synthetic agreement markdown: front matter, numbered sections, pricing grids.

Parsing only. Which document is in force for a batch is never decided here: the workflow
shows the model every version with its effective date and the model picks the citation.
"""

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

AGREEMENTS_DIR = Path(__file__).parent / "agreements"

_FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)
_SECTION_TITLE = re.compile(r"^§(\d+(?:\.\d+)*)\s+(.*)$")
_CITATION = re.compile(r"^(\S+) §(\d+(?:\.\d+)*)$")
_PERCENT = re.compile(r"^(\d+(?:\.\d+)?)%$")
_MAX_FRACTION_PLACES = 6  # kredpare.core.canonical.Ratio


@dataclass(frozen=True)
class Section:
    number: str
    title: str
    text: str


@dataclass(frozen=True)
class AgreementDocument:
    counterparty_id: str
    document: str
    effective_date: date
    signed_date: date | None
    title: str
    body: str


@dataclass(frozen=True)
class PricingGrid:
    source: str
    """Citation of the section holding the grid, for example "amendment-2 §4.1"."""
    effective_date: date
    prices: dict[str, Decimal]
    """Credit tier to price as an exact fraction of UPB."""


def load_agreements(counterparty_id: str, root: Path = AGREEMENTS_DIR) -> list[AgreementDocument]:
    """The counterparty's documents, oldest effective date first."""
    folder = root / counterparty_id
    if not folder.is_dir():
        return []
    documents = [_parse_document(path) for path in folder.glob("*.md")]
    return sorted(documents, key=lambda d: (d.effective_date, d.document))


def _parse_document(path: Path) -> AgreementDocument:
    raw = path.read_text(encoding="utf-8")
    match = _FRONT_MATTER.match(raw)
    if match is None:
        raise ValueError(f"{path}: missing front matter")
    meta = dict(line.split(": ", 1) for line in match.group(1).splitlines())
    signed = meta.get("signed_date")
    return AgreementDocument(
        counterparty_id=meta["counterparty_id"],
        document=meta["document"],
        effective_date=date.fromisoformat(meta["effective_date"]),
        signed_date=date.fromisoformat(signed) if signed else None,
        title=meta["title"],
        body=raw[match.end() :].lstrip("\n"),
    )


def parse_sections(body: str) -> dict[str, Section]:
    """Sections whose heading starts with a section number, e.g. "## §4.2 Accrued Interest"."""
    headings = list(_HEADING.finditer(body))
    sections: dict[str, Section] = {}
    for index, heading in enumerate(headings):
        numbered = _SECTION_TITLE.match(heading.group(2))
        if numbered is None:
            continue
        end = headings[index + 1].start() if index + 1 < len(headings) else len(body)
        number = numbered.group(1)
        sections[number] = Section(number, numbered.group(2), body[heading.end() : end].strip())
    return sections


def _parse_percent(cell: str) -> Decimal:
    match = _PERCENT.match(cell.strip())
    if match is None:
        raise ValueError(f"not a percentage: {cell!r}")
    fraction = Decimal(match.group(1)).scaleb(-2)
    exponent = fraction.as_tuple().exponent
    if isinstance(exponent, int) and -exponent > _MAX_FRACTION_PLACES:
        raise ValueError(f"{cell!r} as a fraction would need rounding")
    return fraction


def parse_pricing_grid(document: AgreementDocument) -> PricingGrid | None:
    """The pricing grid table in the document, or None when it holds no `Tier | Price` table."""
    for section in parse_sections(document.body).values():
        rows = [line for line in section.text.splitlines() if line.startswith("|")]
        if not rows or not re.match(r"^\|\s*Tier\s*\|\s*Price", rows[0]):
            continue
        prices: dict[str, Decimal] = {}
        for row in rows[2:]:
            tier, price = (cell.strip() for cell in row.strip("|").split("|"))
            prices[tier] = _parse_percent(price)
        return PricingGrid(
            source=f"{document.document} §{section.number}",
            effective_date=document.effective_date,
            prices=prices,
        )
    return None


def citation_exists(citation: str, documents: list[AgreementDocument]) -> bool:
    """True when "<document> §<number>" names a numbered section of one of the documents."""
    match = _CITATION.match(citation.strip())
    if match is None:
        return False
    name, number = match.groups()
    return any(d.document == name and number in parse_sections(d.body) for d in documents)

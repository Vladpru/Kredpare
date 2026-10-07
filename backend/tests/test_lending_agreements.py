from datetime import date
from decimal import Decimal

import pytest

from kredpare.domains.lending.agreement_documents import (
    PricingGrid,
    citation_exists,
    load_agreements,
    parse_pricing_grid,
    parse_sections,
)


def test_loads_documents_with_front_matter_sorted_by_effective_date() -> None:
    docs = load_agreements("cp-tessaline")

    assert [(d.document, d.effective_date) for d in docs] == [
        ("base", date(2026, 1, 1)),
        ("amendment-2", date(2026, 7, 1)),
        ("amendment-1", date(2026, 8, 24)),
    ]
    assert docs[0].counterparty_id == "cp-tessaline"
    assert docs[1].signed_date == date(2026, 6, 20)
    assert docs[0].signed_date is None
    assert docs[0].title.startswith("Forward Flow")
    assert not docs[0].body.startswith("---")


def test_unknown_counterparty_has_no_documents() -> None:
    assert load_agreements("cp-nobody") == []


def test_sections_are_keyed_by_number() -> None:
    brackwater = {d.document: d for d in load_agreements("cp-brackwater")}

    sections = parse_sections(brackwater["amendment-1"].body)

    assert set(sections) == {"4.2"}
    assert "Actual/365" in sections["4.2"].text
    assert sections["4.2"].title == "Accrued Interest"
    assert {"4.1", "4.2", "4.3"} <= set(parse_sections(brackwater["base"].body))


def test_pricing_grid_is_exact_decimal_fractions() -> None:
    docs = {d.document: d for d in load_agreements("cp-quillmont")}

    base = parse_pricing_grid(docs["base"])
    amended = parse_pricing_grid(docs["amendment-2"])

    assert isinstance(base, PricingGrid)
    assert amended is not None
    assert base.prices["B"] == Decimal("1.0150")
    assert amended.prices["B"] == Decimal("1.0100")
    assert amended.source == "amendment-2 §4.1"
    assert amended.effective_date == date(2026, 9, 1)
    assert parse_pricing_grid(docs["amendment-1"]) is None


def test_grid_needing_rounding_is_rejected() -> None:
    from kredpare.domains.lending.agreement_documents import _parse_percent

    with pytest.raises(ValueError, match="rounding"):
        _parse_percent("101.1234567%")
    assert _parse_percent("101.75%") == Decimal("1.0175")
    with pytest.raises(ValueError):
        _parse_percent("101.75")


def test_citation_exists_checks_document_and_section() -> None:
    docs = load_agreements("cp-tessaline")

    assert citation_exists("amendment-2 §4.4", docs)
    assert citation_exists("base §4.2", docs)
    assert not citation_exists("amendment-1 §4.2", docs)
    assert not citation_exists("amendment-3 §4.1", docs)
    assert not citation_exists("§4.1", docs)

import re
from datetime import date
from pathlib import Path

from kredpare.core.domain import MatchDeclaration
from kredpare.domains.lending.spec import LENDING


def test_lending_registers_its_three_schemas_keyed_by_loan_id() -> None:
    assert {s.name: s.record_id_field for s in LENDING.schemas} == {
        "FundedLoan": "loan_id",
        "PurchaseConfirmation": "loan_id",
        "ServicerOnboarding": "loan_id",
    }


def test_lending_registers_the_break_types_from_the_taxonomy() -> None:
    assert [b.name for b in LENDING.break_types] == [
        "missing_record",
        "duplicate",
        "amount_mismatch",
        "date_mismatch",
        "stale_pending",
    ]


def test_lending_match_declarations_follow_the_canonical_schema() -> None:
    assert LENDING.match_declarations == (
        MatchDeclaration(
            left="FundedLoan",
            right="PurchaseConfirmation",
            key_fields=("counterparty_id", "batch_id", "loan_id"),
            money_fields=("upb", "price_pct", "accrued_interest", "purchase_price"),
            date_fields=("settlement_date",),
            delivery_fields=("counterparty_id", "batch_id"),
            age_from="cut_off_date",
        ),
        MatchDeclaration(
            left="PurchaseConfirmation",
            right="ServicerOnboarding",
            key_fields=("loan_id",),
            money_fields=("upb",),
            date_fields=(),
            age_from="settlement_date",
        ),
    )


def test_lending_has_no_rules_or_tools_yet() -> None:
    assert LENDING.rules == ()
    assert LENDING.tools == ()


_CORE = Path(__file__).resolve().parents[1] / "src" / "kredpare" / "core"
_LENDING_WORDS = re.compile(
    r"\b(loans?|lender|lending|partner|contract|upb|dealer|servicer|credit_tier)\b", re.I
)


def test_core_source_uses_no_lending_words() -> None:
    hits = [
        f"{path.relative_to(_CORE)}:{number}: {line.strip()}"
        for path in sorted(_CORE.rglob("*.py"))
        for number, line in enumerate(path.read_text().splitlines(), start=1)
        if _LENDING_WORDS.search(line)
    ]

    assert hits == []


def test_lending_registers_one_mapping_per_known_format() -> None:
    assert sorted(m.name for m in LENDING.mappings) == [
        "cp-brackwater PurchaseConfirmation v1",
        "cp-orlo ServicerOnboarding v1",
        "cp-quillmont PurchaseConfirmation v1",
        "cp-tessaline PurchaseConfirmation v1",
        "seller FundedLoan v1",
    ]


def test_lending_ages_pending_records_in_us_business_days() -> None:
    assert LENDING.calendar is not None
    assert LENDING.stale_after_business_days == 5
    # Labor Day 2026-09-07 is not a business day.
    assert LENDING.calendar.add_business_days(date(2026, 9, 2), 5) == date(2026, 9, 10)

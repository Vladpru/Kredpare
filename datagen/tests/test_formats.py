from datetime import date
from decimal import Decimal

import pytest
from kredpare.domains.lending.schemas import PurchaseConfirmation, ServicerOnboarding

from kredpare_datagen.formats import (
    render_confirmation,
    render_dataset,
    render_funded,
    render_onboarding,
)
from kredpare_datagen.generate import Dataset


def _confirmation(batch_id: str, **overrides: object) -> PurchaseConfirmation:
    fields: dict[str, object] = {
        "loan_id": "L-004512",
        "batch_id": batch_id,
        "settlement_date": date(2026, 9, 2),
        "upb": Decimal("20300.00"),
        "price_pct": Decimal("1.015000"),
        "accrued_interest": Decimal("72.23"),
        "purchase_price": Decimal("20676.73"),
    }
    fields.update(overrides)
    return PurchaseConfirmation.model_validate(fields)


def test_quillmont_format() -> None:
    text = render_confirmation("cp-quillmont", [_confirmation("cp-quillmont-2026-09-02")])

    assert text == (
        "Loan Number,Settle Date,Principal Balance,Purchase Price %,Accrued Int,Total Price\n"
        'L-004512,09/02/2026,"$20,300.00",101.500,$72.23,"$20,676.73"\n'
    )


def test_brackwater_format() -> None:
    text = render_confirmation("cp-brackwater", [_confirmation("cp-brackwater-2026-09-02")])

    assert text == (
        "ACCT_ID;PURCH_DT;UPB_CENTS;PX;ACCR_INT_CENTS;PROCEEDS_CENTS\n"
        "L-004512;20260902;2030000;1.015000;7223;2067673\n"
    )


def test_tessaline_format() -> None:
    text = render_confirmation("cp-tessaline", [_confirmation("cp-tessaline-2026-09-02")])

    assert text == (
        "Settlement,Batch Ref,Loan ID,Current Balance,Price,Interest Accrued,Wire Amount\n"
        "02-Sep-2026,cp-tessaline-2026-09-02,L-004512,20300.00,101.50,72.23,20676.73\n"
    )


def test_percent_formats_refuse_to_round() -> None:
    row = _confirmation("cp-tessaline-2026-09-02", price_pct=Decimal("1.015250"))

    with pytest.raises(ValueError, match=r"101\.525"):
        render_confirmation("cp-tessaline", [row])


def test_orlo_format() -> None:
    row = ServicerOnboarding(
        loan_id="L-004512",
        boarded_date=date(2026, 9, 4),
        upb=Decimal("20300.00"),
        next_payment_due_date=date(2026, 10, 4),
    )

    assert render_onboarding([row]) == (
        "loan_id,board_dt,boarded_upb,first_due\nL-004512,2026-09-04,20300.00,2026-10-04\n"
    )


def test_seller_file_uses_canonical_names_and_iso_formats(clean: Dataset) -> None:
    loan = clean.batches[0].funded[0]
    lines = render_funded(clean.batches[0].funded).splitlines()

    assert lines[0] == (
        "loan_id,batch_id,dealer_id,credit_tier,funding_date,cut_off_date,settlement_date,"
        "funded_amount,upb,note_rate,term_months,price_pct,accrued_interest,purchase_price"
    )
    assert lines[1].split(",")[:2] == [loan.loan_id, loan.batch_id]
    assert lines[1].split(",")[4] == loan.funding_date.isoformat()
    assert lines[1].split(",")[9] == str(loan.note_rate)
    assert len(lines) == 41


def test_render_dataset_lists_every_file_with_its_metadata(clean: Dataset) -> None:
    files = render_dataset(clean)
    by_schema = {
        s: [f for f in files if f.schema_name == s] for s in {f.schema_name for f in files}
    }

    assert len(by_schema["FundedLoan"]) == len(clean.batches) == 10
    assert len(by_schema["PurchaseConfirmation"]) == 10
    assert {f.counterparty_id for f in by_schema["ServicerOnboarding"]} == {"cp-orlo"}
    assert len({f.path for f in files}) == len(files)
    tessaline = next(
        f for f in by_schema["PurchaseConfirmation"] if f.counterparty_id == "cp-tessaline"
    )
    assert tessaline.path == "cp-tessaline/confirmation_2026-08-14.csv"
    assert tessaline.batch_id == "cp-tessaline-2026-08-14"

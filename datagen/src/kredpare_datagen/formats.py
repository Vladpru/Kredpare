"""Each party's own CSV format, from docs/domain/counterparties.md. Formatting never rounds."""

import csv
import io
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from itertools import groupby

from kredpare.domains.lending.schemas import FundedLoan, PurchaseConfirmation, ServicerOnboarding

from kredpare_datagen.agreements import BRACKWATER, ORLO, QUILLMONT, TESSALINE
from kredpare_datagen.generate import Dataset

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


@dataclass(frozen=True)
class RenderedFile:
    path: str
    counterparty_id: str
    schema_name: str
    batch_id: str
    """Upload metadata: the batch the file belongs to, for files without a batch column."""
    content: str


def _exact(value: Decimal, places: int) -> str:
    text = f"{value:.{places}f}"
    if Decimal(text) != value:
        raise ValueError(f"{value} does not fit {places} decimal places")
    return text


def _dollars(value: Decimal) -> str:
    """$1,234.50; a negative amount as -$1,234.50."""
    whole, cents = _exact(abs(value), 2).split(".")
    return f"{'-' if value < 0 else ''}${int(whole):,}.{cents}"


def _cents(value: Decimal) -> str:
    return str(int(Decimal(_exact(value, 2)).scaleb(2)))


def _percent(places: int) -> Callable[[Decimal], str]:
    return lambda value: _exact(value.scaleb(2), places)


def _plain(value: Decimal) -> str:
    return _exact(value, 2)


@dataclass(frozen=True)
class _Format:
    delimiter: str
    columns: Sequence[tuple[str, Callable[[PurchaseConfirmation], str]]]


def _date_mdy(day: date) -> str:
    return day.strftime("%m/%d/%Y")


def _date_dmy(day: date) -> str:
    return f"{day.day:02d}-{_MONTHS[day.month - 1]}-{day.year}"


_CONFIRMATION_FORMATS: dict[str, _Format] = {
    QUILLMONT: _Format(
        ",",
        (
            ("Loan Number", lambda r: r.loan_id),
            ("Settle Date", lambda r: _date_mdy(r.settlement_date)),
            ("Principal Balance", lambda r: _dollars(r.upb)),
            ("Purchase Price %", lambda r: _percent(3)(r.price_pct)),
            ("Accrued Int", lambda r: _dollars(r.accrued_interest)),
            ("Total Price", lambda r: _dollars(r.purchase_price)),
        ),
    ),
    BRACKWATER: _Format(
        ";",
        (
            ("ACCT_ID", lambda r: r.loan_id),
            ("PURCH_DT", lambda r: r.settlement_date.strftime("%Y%m%d")),
            ("UPB_CENTS", lambda r: _cents(r.upb)),
            ("PX", lambda r: _exact(r.price_pct, 6)),
            ("ACCR_INT_CENTS", lambda r: _cents(r.accrued_interest)),
            ("PROCEEDS_CENTS", lambda r: _cents(r.purchase_price)),
        ),
    ),
    TESSALINE: _Format(
        ",",
        (
            ("Settlement", lambda r: _date_dmy(r.settlement_date)),
            ("Batch Ref", lambda r: r.batch_id),
            ("Loan ID", lambda r: r.loan_id),
            ("Current Balance", lambda r: _plain(r.upb)),
            ("Price", lambda r: _percent(2)(r.price_pct)),
            ("Interest Accrued", lambda r: _plain(r.accrued_interest)),
            ("Wire Amount", lambda r: _plain(r.purchase_price)),
        ),
    ),
}


def _csv(delimiter: str, header: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=delimiter, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue()


def render_confirmation(counterparty_id: str, rows: Sequence[PurchaseConfirmation]) -> str:
    fmt = _CONFIRMATION_FORMATS[counterparty_id]
    return _csv(
        fmt.delimiter,
        [name for name, _ in fmt.columns],
        [[render(row) for _, render in fmt.columns] for row in rows],
    )


def render_funded(rows: Sequence[FundedLoan]) -> str:
    """Seller file: canonical names in schema order, ISO dates, plain decimals."""
    names = list(FundedLoan.model_fields)
    return _csv(",", names, [[_canonical(getattr(row, n)) for n in names] for row in rows])


def render_onboarding(rows: Sequence[ServicerOnboarding]) -> str:
    return _csv(
        ",",
        ["loan_id", "board_dt", "boarded_upb", "first_due"],
        [
            [
                r.loan_id,
                r.boarded_date.isoformat(),
                _plain(r.upb),
                r.next_payment_due_date.isoformat(),
            ]
            for r in rows
        ],
    )


def _canonical(value: object) -> str:
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def render_dataset(dataset: Dataset) -> list[RenderedFile]:
    files: list[RenderedFile] = []
    for batch in dataset.batches:
        day = batch.settlement_date.isoformat()
        files.append(
            RenderedFile(
                f"seller/funded_{batch.counterparty_id}_{day}.csv",
                batch.counterparty_id,
                "FundedLoan",
                batch.batch_id,
                render_funded(batch.funded),
            )
        )
        if batch.confirmation is not None:
            files.append(
                RenderedFile(
                    f"{batch.counterparty_id}/confirmation_{day}.csv",
                    batch.counterparty_id,
                    "PurchaseConfirmation",
                    batch.batch_id,
                    render_confirmation(batch.counterparty_id, batch.confirmation),
                )
            )
    for boarded_date, rows in groupby(dataset.onboardings, key=lambda o: o.boarded_date):
        day = boarded_date.isoformat()
        files.append(
            RenderedFile(
                f"{ORLO}/onboarding_{day}.csv",
                ORLO,
                "ServicerOnboarding",
                f"{ORLO}-{day}",
                render_onboarding(list(rows)),
            )
        )
    return files

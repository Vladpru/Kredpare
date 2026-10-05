from kredpare.core.rules.types import BreakView
from kredpare.domains.lending.rules.records import (
    ConfirmationOverdue,
    DuplicateRow,
    LoanNotConfirmed,
    LoanNotOffered,
)
from tests.fake_context import (
    BATCH,
    CONFIRMATION,
    CP,
    FILE_A,
    FILE_B,
    LOAN,
    SELLER,
    FakeContext,
    make_break,
    make_record,
)

OTHER_BATCH = "cp-quillmont-2026-09-09"
OTHER_LOAN = "L-000002"


# -- loan_not_confirmed ------------------------------------------------------------------


def _not_confirmed(seller_present: bool = True) -> tuple[FakeContext, BreakView]:
    seller = make_record(SELLER)
    # The file arrived: it holds another loan of the batch.
    delivered = make_record(CONFIRMATION, loan=OTHER_LOAN)
    ctx = FakeContext([seller, delivered])
    brk = make_break(
        "missing_record",
        side_schema=CONFIRMATION,
        left=seller if seller_present else None,
    )
    return ctx, brk


def test_loan_not_confirmed_explains_a_loan_missing_from_a_received_confirmation() -> None:
    ctx, brk = _not_confirmed()

    found = LoanNotConfirmed().explain(brk, ctx)

    assert found is not None
    assert (found.rule, found.cause) == ("loan_not_confirmed", "loan_not_confirmed")
    assert (found.wrong_side, found.proposal) == ("counterparty", "email")
    assert found.evidence == {
        "loan_id": LOAN,
        "batch_id": BATCH,
        "confirmation_rows_in_batch": 1,
    }


def test_loan_not_confirmed_needs_the_confirmation_file_to_have_arrived() -> None:
    seller = make_record(SELLER)
    brk = make_break("missing_record", side_schema=CONFIRMATION, left=seller)

    assert LoanNotConfirmed().explain(brk, FakeContext([seller])) is None


def test_loan_not_confirmed_ignores_a_confirmation_of_another_batch() -> None:
    seller = make_record(SELLER)
    elsewhere = make_record(CONFIRMATION, loan=OTHER_LOAN, batch=OTHER_BATCH)
    brk = make_break("missing_record", side_schema=CONFIRMATION, left=seller)

    assert LoanNotConfirmed().explain(brk, FakeContext([seller, elsewhere])) is None


def test_loan_not_confirmed_needs_the_loan_in_the_seller_file() -> None:
    ctx, brk = _not_confirmed(seller_present=False)

    assert LoanNotConfirmed().explain(brk, ctx) is None


def test_loan_not_confirmed_ignores_a_loan_missing_on_the_seller_side() -> None:
    delivered = make_record(CONFIRMATION)
    brk = make_break("missing_record", side_schema=SELLER, right=delivered)

    assert LoanNotConfirmed().explain(brk, FakeContext([delivered])) is None


# -- loan_not_offered --------------------------------------------------------------------


def _not_offered(counterparty: str = CP) -> tuple[FakeContext, BreakView]:
    confirmed = make_record(CONFIRMATION)
    offered = make_record(SELLER, batch=OTHER_BATCH, counterparty=counterparty)
    brk = make_break("missing_record", side_schema=SELLER, right=confirmed)
    return FakeContext([confirmed, offered]), brk


def test_loan_not_offered_explains_a_loan_the_seller_offered_in_another_batch() -> None:
    ctx, brk = _not_offered()

    found = LoanNotOffered().explain(brk, ctx)

    assert found is not None
    assert (found.rule, found.cause) == ("loan_not_offered", "loan_not_offered")
    assert (found.wrong_side, found.proposal) == ("counterparty", "email")
    assert found.evidence == {
        "loan_id": LOAN,
        "batch_id": BATCH,
        "seller_batches": [OTHER_BATCH],
    }


def test_loan_not_offered_needs_the_loan_in_some_seller_batch() -> None:
    confirmed = make_record(CONFIRMATION)
    brk = make_break("missing_record", side_schema=SELLER, right=confirmed)

    assert LoanNotOffered().explain(brk, FakeContext([confirmed])) is None


def test_loan_not_offered_ignores_another_counterpartys_batch() -> None:
    ctx, brk = _not_offered(counterparty="cp-other")

    assert LoanNotOffered().explain(brk, ctx) is None


def test_loan_not_offered_ignores_the_same_batch() -> None:
    # A seller row in the break's own batch means matching would have paired it.
    confirmed = make_record(CONFIRMATION)
    offered = make_record(SELLER)
    brk = make_break("missing_record", side_schema=SELLER, right=confirmed)

    assert LoanNotOffered().explain(brk, FakeContext([confirmed, offered])) is None


def test_loan_not_offered_ignores_a_loan_missing_on_the_confirmation_side() -> None:
    seller = make_record(SELLER)
    other = make_record(SELLER, batch=OTHER_BATCH)
    brk = make_break("missing_record", side_schema=CONFIRMATION, left=seller)

    assert LoanNotOffered().explain(brk, FakeContext([seller, other])) is None


# -- duplicate_row -----------------------------------------------------------------------

ROW = {"loan_id": LOAN, "batch_id": BATCH, "upb": "100.00"}


def _duplicate(
    schema: str, second: dict[str, object] | None = None, *, second_file: bool = False
) -> tuple[FakeContext, BreakView]:
    first = make_record(schema, row_number=1, data=ROW)
    again = make_record(
        schema,
        row_number=2,
        file_id=FILE_B if second_file else FILE_A,
        data=second if second is not None else ROW,
    )
    brk = make_break("duplicate", side_schema=schema, left=first)
    return FakeContext([first, again]), brk


def test_duplicate_row_in_the_seller_file_is_the_sellers_to_correct() -> None:
    ctx, brk = _duplicate(SELLER)

    found = DuplicateRow().explain(brk, ctx)

    assert found is not None
    assert (found.rule, found.cause) == ("duplicate_row", "duplicate_row")
    assert (found.wrong_side, found.proposal) == ("seller", "correction")
    assert found.evidence == {"loan_id": LOAN, "batch_id": BATCH, "rows": 2, "row_numbers": [1, 2]}


def test_duplicate_row_in_the_confirmation_is_the_counterpartys() -> None:
    ctx, brk = _duplicate(CONFIRMATION)

    found = DuplicateRow().explain(brk, ctx)

    assert found is not None
    assert (found.wrong_side, found.proposal) == ("counterparty", "email")


def test_duplicate_row_with_different_values_is_not_explained() -> None:
    ctx, brk = _duplicate(SELLER, {**ROW, "upb": "100.01"})

    assert DuplicateRow().explain(brk, ctx) is None


def test_duplicate_row_ignores_rows_of_another_file() -> None:
    ctx, brk = _duplicate(SELLER, second_file=True)

    assert DuplicateRow().explain(brk, ctx) is None


def test_duplicate_row_of_a_file_without_a_known_owner_is_not_explained() -> None:
    ctx, brk = _duplicate("ServicerOnboarding")

    assert DuplicateRow().explain(brk, ctx) is None


# -- confirmation_overdue ----------------------------------------------------------------


def _overdue(extra_breaks: bool = False, delivered: bool = False) -> tuple[FakeContext, BreakView]:
    seller = make_record(SELLER)
    brk = make_break("stale_pending", side_schema=CONFIRMATION, left=seller)
    records = [seller]
    if delivered:
        records.append(make_record(CONFIRMATION, loan=OTHER_LOAN))
    breaks = [brk]
    if extra_breaks:
        breaks.append(make_break("amount_mismatch", field="upb", batch=OTHER_BATCH))
    return FakeContext(records, breaks), brk


def test_confirmation_overdue_explains_a_loan_with_no_other_break() -> None:
    ctx, brk = _overdue()

    found = ConfirmationOverdue().explain(brk, ctx)

    assert found is not None
    assert (found.rule, found.cause) == ("confirmation_overdue", "confirmation_overdue")
    assert (found.wrong_side, found.proposal) == (None, "email")
    assert found.evidence == {"loan_id": LOAN, "batch_id": BATCH, "counterparty_id": CP}


def test_confirmation_overdue_is_not_explained_when_the_loan_has_another_break() -> None:
    ctx, brk = _overdue(extra_breaks=True)

    assert ConfirmationOverdue().explain(brk, ctx) is None


def test_confirmation_overdue_is_not_explained_when_the_file_arrived() -> None:
    ctx, brk = _overdue(delivered=True)

    assert ConfirmationOverdue().explain(brk, ctx) is None


def test_confirmation_overdue_ignores_a_loan_not_yet_boarded() -> None:
    confirmed = make_record(CONFIRMATION)
    brk = make_break("stale_pending", side_schema="ServicerOnboarding", left=confirmed)

    assert ConfirmationOverdue().explain(brk, FakeContext([confirmed], [brk])) is None

from kredpare_datagen.generate import Batch

COMPARED = ("upb", "price_pct", "accrued_interest", "purchase_price", "settlement_date")


def differences(batch: Batch) -> dict[str, tuple[str, ...]]:
    """Per loan of the seller file: compared fields that differ from its confirmation row."""
    if batch.confirmation is None:
        return {}
    confirmed = {row.loan_id: row for row in batch.confirmation}
    result: dict[str, tuple[str, ...]] = {}
    for loan in batch.funded:
        row = confirmed.get(loan.loan_id)
        if row is None:
            continue
        fields = tuple(f for f in COMPARED if getattr(loan, f) != getattr(row, f))
        if fields:
            result[loan.loan_id] = fields
    return result

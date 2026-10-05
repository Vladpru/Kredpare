"""Hand-written mapping configs v1, one per known file format (docs/domain/counterparties.md)."""

from kredpare.core.mapping.config import ColumnMapping, MappingConfig
from kredpare.core.mapping.transforms import Transform as T


def _columns(*columns: tuple[str, str, T]) -> tuple[ColumnMapping, ...]:
    return tuple(ColumnMapping(source=s, target=t, transform=x) for s, t, x in columns)


SELLER = MappingConfig(
    name="seller FundedLoan v1",
    schema_name="FundedLoan",
    columns=_columns(
        ("loan_id", "loan_id", T.TEXT),
        ("batch_id", "batch_id", T.TEXT),
        ("dealer_id", "dealer_id", T.TEXT),
        ("credit_tier", "credit_tier", T.TEXT),
        ("funding_date", "funding_date", T.PARSE_DATE_ISO),
        ("cut_off_date", "cut_off_date", T.PARSE_DATE_ISO),
        ("settlement_date", "settlement_date", T.PARSE_DATE_ISO),
        ("funded_amount", "funded_amount", T.PARSE_DECIMAL),
        ("upb", "upb", T.PARSE_DECIMAL),
        ("note_rate", "note_rate", T.PARSE_DECIMAL),
        ("term_months", "term_months", T.PARSE_INT),
        ("price_pct", "price_pct", T.PARSE_DECIMAL),
        ("accrued_interest", "accrued_interest", T.PARSE_DECIMAL),
        ("purchase_price", "purchase_price", T.PARSE_DECIMAL),
    ),
)

QUILLMONT = MappingConfig(
    name="cp-quillmont PurchaseConfirmation v1",
    schema_name="PurchaseConfirmation",
    columns=_columns(
        ("Loan Number", "loan_id", T.TEXT),
        ("Settle Date", "settlement_date", T.PARSE_DATE_MDY),
        ("Principal Balance", "upb", T.PARSE_USD),
        ("Purchase Price %", "price_pct", T.PERCENT_TO_FRACTION),
        ("Accrued Int", "accrued_interest", T.PARSE_USD),
        ("Total Price", "purchase_price", T.PARSE_USD),
    ),
    batch_id_from_metadata=True,
)

BRACKWATER = MappingConfig(
    name="cp-brackwater PurchaseConfirmation v1",
    schema_name="PurchaseConfirmation",
    delimiter=";",
    columns=_columns(
        ("ACCT_ID", "loan_id", T.TEXT),
        ("PURCH_DT", "settlement_date", T.PARSE_DATE_YMD_COMPACT),
        ("UPB_CENTS", "upb", T.CENTS_TO_DECIMAL),
        ("PX", "price_pct", T.PARSE_DECIMAL),
        ("ACCR_INT_CENTS", "accrued_interest", T.CENTS_TO_DECIMAL),
        ("PROCEEDS_CENTS", "purchase_price", T.CENTS_TO_DECIMAL),
    ),
    batch_id_from_metadata=True,
)

TESSALINE = MappingConfig(
    name="cp-tessaline PurchaseConfirmation v1",
    schema_name="PurchaseConfirmation",
    columns=_columns(
        ("Settlement", "settlement_date", T.PARSE_DATE_DMON_Y),
        ("Batch Ref", "batch_id", T.TEXT),
        ("Loan ID", "loan_id", T.TEXT),
        ("Current Balance", "upb", T.PARSE_DECIMAL),
        ("Price", "price_pct", T.PERCENT_TO_FRACTION),
        ("Interest Accrued", "accrued_interest", T.PARSE_DECIMAL),
        ("Wire Amount", "purchase_price", T.PARSE_DECIMAL),
    ),
)

ORLO = MappingConfig(
    name="cp-orlo ServicerOnboarding v1",
    schema_name="ServicerOnboarding",
    columns=_columns(
        ("loan_id", "loan_id", T.TEXT),
        ("board_dt", "boarded_date", T.PARSE_DATE_ISO),
        ("boarded_upb", "upb", T.PARSE_DECIMAL),
        ("first_due", "next_payment_due_date", T.PARSE_DATE_ISO),
    ),
)

MAPPINGS = (SELLER, QUILLMONT, BRACKWATER, TESSALINE, ORLO)

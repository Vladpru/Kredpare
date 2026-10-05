from kredpare.core.domain import DomainSpec, MatchDeclaration, SchemaSpec
from kredpare.domains.lending.break_types import BREAK_TYPES
from kredpare.domains.lending.schemas import FundedLoan, PurchaseConfirmation, ServicerOnboarding

LENDING = DomainSpec(
    name="lending",
    schemas=(
        SchemaSpec(FundedLoan, record_id_field="loan_id"),
        SchemaSpec(PurchaseConfirmation, record_id_field="loan_id"),
        SchemaSpec(ServicerOnboarding, record_id_field="loan_id"),
    ),
    break_types=BREAK_TYPES,
    match_declarations=(
        MatchDeclaration(
            left="FundedLoan",
            right="PurchaseConfirmation",
            key_fields=("counterparty_id", "batch_id", "loan_id"),
            # price_pct is not money but is compared exactly like money.
            money_fields=("upb", "price_pct", "accrued_interest", "purchase_price"),
            date_fields=("settlement_date",),
        ),
        MatchDeclaration(
            left="PurchaseConfirmation",
            right="ServicerOnboarding",
            key_fields=("loan_id",),
            money_fields=("upb",),
            date_fields=(),
        ),
    ),
)

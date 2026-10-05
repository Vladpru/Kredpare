from kredpare.core.domain import DomainSpec, MatchDeclaration, SchemaSpec
from kredpare.domains.lending.break_types import BREAK_TYPES
from kredpare.domains.lending.calendar import US_BANK_CALENDAR
from kredpare.domains.lending.mappings import MAPPINGS
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
            # A loan missing from a received confirmation file is missing; with no file yet
            # it is pending until it goes stale after the cut-off date.
            delivery_fields=("counterparty_id", "batch_id"),
            age_from="cut_off_date",
        ),
        MatchDeclaration(
            left="PurchaseConfirmation",
            right="ServicerOnboarding",
            key_fields=("loan_id",),
            money_fields=("upb",),
            date_fields=(),
            # Boarding takes days: an unboarded loan is pending, stale only after N days.
            age_from="settlement_date",
        ),
    ),
    mappings=MAPPINGS,
    calendar=US_BANK_CALENDAR,
    stale_after_business_days=5,
)

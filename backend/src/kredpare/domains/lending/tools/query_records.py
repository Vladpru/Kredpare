"""query_records: read-only, parameterized lookup of stored canonical records. No free SQL."""

from kredpare.core.rules.types import JsonValue, RuleContext
from kredpare.domains.lending.schemas import FundedLoan, PurchaseConfirmation, ServicerOnboarding

SCHEMA_NAMES = (FundedLoan.__name__, PurchaseConfirmation.__name__, ServicerOnboarding.__name__)
MAX_LIMIT = 500


class QueryRecords:
    """Records matching every given filter. Values are canonical: decimal strings, ISO dates."""

    name = "query_records"

    def __call__(
        self,
        context: RuleContext,
        *,
        counterparty_id: str | None = None,
        batch_id: str | None = None,
        loan_id: str | None = None,
        schema: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, JsonValue]]:
        if counterparty_id is None and batch_id is None and loan_id is None and schema is None:
            raise ValueError("query_records needs at least one filter")
        if schema is not None and schema not in SCHEMA_NAMES:
            raise ValueError(f"unknown schema {schema!r}; known: {', '.join(SCHEMA_NAMES)}")
        if not 1 <= limit <= MAX_LIMIT:
            raise ValueError(f"limit must be between 1 and {MAX_LIMIT}, got {limit}")
        found = context.find_records(
            schema_name=schema,
            counterparty_id=counterparty_id,
            batch_id=batch_id,
            record_id=loan_id,
            limit=limit,
        )
        return [
            {
                "schema": r.schema_name,
                "counterparty_id": r.counterparty_id,
                "batch_id": r.batch_id,
                "loan_id": r.record_id,
                "row_number": r.row_number,
                "data": dict(r.data),  # type: ignore[dict-item]
            }
            for r in found
        ]

from kredpare.core.domain import BreakType

# Symptoms only; root causes live in docs/domain/break-taxonomy.md.
BREAK_TYPES = (
    BreakType("missing_record", "A record exists on one side only."),
    BreakType("duplicate", "The same match key appears more than once in one file."),
    BreakType("amount_mismatch", "A compared money field differs. Exact, no tolerance."),
    BreakType("date_mismatch", "A compared date field differs."),
    BreakType(
        "stale_pending",
        "No confirmation or boarding more than N business days after the cut-off date.",
    ),
)

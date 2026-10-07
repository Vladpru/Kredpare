"""Schema names and sides of the lending pairs. The seller is the left side of a pair."""

SELLER_SCHEMA = "FundedLoan"
CONFIRMATION_SCHEMA = "PurchaseConfirmation"

FILE_OWNER = {SELLER_SCHEMA: "seller", CONFIRMATION_SCHEMA: "counterparty"}

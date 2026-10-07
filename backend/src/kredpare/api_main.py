"""Composition root: wires the lending domain into the generic API."""

from kredpare.core.api.app import create_app
from kredpare.domains.lending.clauses import resolve_clause

app = create_app(clause_resolver=resolve_clause)

from fastapi import FastAPI

from kredpare.api_main import app
from kredpare.domains.lending.clauses import resolve_clause


def test_resolves_section_text() -> None:
    text = resolve_clause("cp-brackwater", "amendment-1 §4.2")
    assert text is not None
    assert "Actual/365" in text


def test_unknown_inputs_return_none() -> None:
    assert resolve_clause("cp-brackwater", "amendment-1 §99.9") is None
    assert resolve_clause("cp-nobody", "base §4.3") is None
    assert resolve_clause("cp-brackwater", "garbage") is None


def test_app_has_clause_resolver() -> None:
    assert isinstance(app, FastAPI)
    assert app.state.clause_resolver is not None

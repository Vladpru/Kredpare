"""How a domain plugs into core. Core reads these declarations; it never imports a domain.

See docs/adr/0004-core-domains-boundary.md.
"""

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Protocol

import pandera.polars as pa
import polars as pl
from pydantic import BaseModel, ValidationError

from kredpare.core.canonical import CanonicalRecord


class Rule(Protocol):
    """A deterministic break explanation. Its call signature lands with the rule runner."""

    @property
    def name(self) -> str: ...


class Tool(Protocol):
    """A deterministic tool the workflow or agent may call. Signature lands with the agent."""

    @property
    def name(self) -> str: ...


@dataclass(frozen=True)
class RowError:
    row_number: int
    """1-based position of the data row in the file, header excluded."""
    messages: tuple[str, ...]


@dataclass(frozen=True)
class FrameValidation:
    rows: tuple[BaseModel, ...]
    errors: tuple[RowError, ...]


@dataclass(frozen=True)
class SchemaSpec:
    """A canonical schema of the domain. Row rules live in the Pydantic row model."""

    row_model: type[BaseModel]
    record_id_field: str

    def __post_init__(self) -> None:
        if self.record_id_field not in self.row_model.model_fields:
            raise ValueError(f"{self.name} has no field {self.record_id_field!r} for record_id")

    @property
    def name(self) -> str:
        return self.row_model.__name__

    @property
    def field_names(self) -> frozenset[str]:
        return frozenset(self.row_model.model_fields)

    def frame_schema(self) -> pa.DataFrameSchema:
        """File-level shape: exactly the row model's columns, no nulls."""
        return pa.DataFrameSchema(
            columns={name: pa.Column(nullable=False) for name in self.row_model.model_fields},
            strict=True,
        )

    def validate_frame(self, frame: pl.DataFrame) -> FrameValidation:
        """Validate a whole file. Invalid rows are kept as errors, never dropped silently.

        A malformed file (wrong columns, nulls) raises pandera SchemaErrors listing all failures.
        Row rules come from the Pydantic row model only, so each rule is defined once.
        """
        self.frame_schema().validate(frame, lazy=True)
        rows: list[BaseModel] = []
        errors: list[RowError] = []
        for row_number, values in enumerate(frame.iter_rows(named=True), start=1):
            try:
                rows.append(self.row_model.model_validate(values))
            except ValidationError as exc:
                errors.append(RowError(row_number, _messages(exc)))
        return FrameValidation(tuple(rows), tuple(errors))


@dataclass(frozen=True)
class MatchDeclaration:
    """Which fields core matching uses for a pair of schemas. Matching never hard-codes names."""

    left: str
    right: str
    key_fields: tuple[str, ...]
    money_fields: tuple[str, ...]
    date_fields: tuple[str, ...]


@dataclass(frozen=True)
class BreakType:
    """A symptom matching can detect. Root causes are not break types."""

    name: str
    description: str


_ENVELOPE_FIELDS = frozenset(CanonicalRecord.model_fields)


@dataclass(frozen=True)
class DomainSpec:
    name: str
    schemas: tuple[SchemaSpec, ...]
    break_types: tuple[BreakType, ...]
    match_declarations: tuple[MatchDeclaration, ...]
    rules: tuple[Rule, ...] = field(default=())
    tools: tuple[Tool, ...] = field(default=())

    def __post_init__(self) -> None:
        _reject_duplicates("schema", (s.name for s in self.schemas))
        _reject_duplicates("break type", (b.name for b in self.break_types))
        _reject_duplicates("rule", (r.name for r in self.rules))
        _reject_duplicates("tool", (t.name for t in self.tools))
        for declaration in self.match_declarations:
            self._check_declaration(declaration)

    def schema(self, name: str) -> SchemaSpec:
        for spec in self.schemas:
            if spec.name == name:
                return spec
        raise KeyError(f"domain {self.name!r} has no schema {name!r}")

    def _check_declaration(self, declaration: MatchDeclaration) -> None:
        sides: list[SchemaSpec] = []
        for name in (declaration.left, declaration.right):
            try:
                sides.append(self.schema(name))
            except KeyError:
                raise ValueError(f"match declaration references unknown schema {name!r}") from None

        compared = (*declaration.money_fields, *declaration.date_fields)
        for side in sides:
            for name in declaration.key_fields:
                if name not in side.field_names and name not in _ENVELOPE_FIELDS:
                    raise ValueError(f"match key {name!r} is not a field of {side.name}")
            for name in compared:
                if name not in side.field_names:
                    raise ValueError(f"compared field {name!r} is not a field of {side.name}")


def _messages(exc: ValidationError) -> tuple[str, ...]:
    return tuple(
        f"{'.'.join(str(part) for part in error['loc']) or 'row'}: {error['msg']}"
        for error in exc.errors()
    )


def _reject_duplicates(kind: str, names: Iterable[str]) -> None:
    duplicates = sorted(name for name, count in Counter(names).items() if count > 1)
    if duplicates:
        raise ValueError(f"duplicate {kind} names: {', '.join(duplicates)}")

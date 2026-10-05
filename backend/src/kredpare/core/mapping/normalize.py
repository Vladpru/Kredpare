"""Apply a mapping config to a file: source cells → canonical values, row by row."""

import io
from dataclasses import dataclass

import polars as pl

from kredpare.core.domain import RowError
from kredpare.core.mapping.config import MappingConfig, header_hash
from kredpare.core.mapping.transforms import TransformError, apply


@dataclass(frozen=True)
class NormalizedFile:
    rows: tuple[tuple[int, dict[str, object]], ...]
    """(1-based data row number, canonical values) for rows whose every cell transformed."""
    errors: tuple[RowError, ...]


def normalize(config: MappingConfig, content: str, *, batch_id: str | None) -> NormalizedFile:
    if header_hash(content) != config.header_hash:
        raise ValueError(f"file header does not match mapping {config.name}")
    if config.batch_id_from_metadata and batch_id is None:
        raise ValueError(f"mapping {config.name} needs batch_id from upload metadata")

    frame = pl.read_csv(io.StringIO(content), separator=config.delimiter, infer_schema=False)
    rows: list[tuple[int, dict[str, object]]] = []
    errors: list[RowError] = []
    for row_number, cells in enumerate(frame.iter_rows(named=True), start=1):
        values: dict[str, object] = {}
        messages: list[str] = []
        for column in config.columns:
            try:
                values[column.target] = apply(column.transform, cells[column.source] or "")
            except TransformError as exc:
                messages.append(f"{column.source}: {exc}")
        if messages:
            errors.append(RowError(row_number, tuple(messages)))
            continue
        if config.batch_id_from_metadata:
            values["batch_id"] = batch_id
        rows.append((row_number, values))
    return NormalizedFile(tuple(rows), tuple(errors))

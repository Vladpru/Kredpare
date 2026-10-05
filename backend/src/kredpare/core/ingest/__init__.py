"""Load a directory of files described by manifest.jsonl into records, one transaction per file."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pandera.errors
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from kredpare.core.audit import record_event
from kredpare.core.domain import DomainSpec, RowError, canonical_frame
from kredpare.core.mapping.config import MappingConfig, header_hash
from kredpare.core.mapping.normalize import normalize
from kredpare.core.tables import Counterparty, File, MappingConfigRow, Record, RowErrorRow

Status = Literal["ingested", "unmapped", "rejected", "skipped"]


@dataclass(frozen=True)
class ManifestEntry:
    path: str
    counterparty_id: str
    schema_name: str
    batch_id: str
    """Upload metadata; used when the file has no batch column."""
    sha256: str


@dataclass(frozen=True)
class FileOutcome:
    path: str
    status: Status
    rows: int = 0
    errors: int = 0
    message: str | None = None


def read_manifest(directory: Path) -> list[ManifestEntry]:
    lines = (directory / "manifest.jsonl").read_text().splitlines()
    return [ManifestEntry(**json.loads(line)) for line in lines if line.strip()]


def ingest_directory(
    engine: Engine, spec: DomainSpec, directory: Path, *, actor: str = "ingest"
) -> list[FileOutcome]:
    with Session(engine) as session:
        _sync_mappings(session, spec, actor)
        session.commit()
    outcomes: list[FileOutcome] = []
    for entry in read_manifest(directory):
        with Session(engine) as session:
            outcomes.append(_ingest_file(session, spec, directory, entry, actor))
            session.commit()
    return outcomes


def _sync_mappings(session: Session, spec: DomainSpec, actor: str) -> None:
    """Store the domain's mapping configs as version 1 the first time they are seen."""
    known = set(session.scalars(select(MappingConfigRow.header_hash)))
    for mapping in spec.mappings:
        if mapping.header_hash in known:
            continue
        row = MappingConfigRow(
            header_hash=mapping.header_hash,
            name=mapping.name,
            schema_name=mapping.schema_name,
            version=1,
            status="active",
            config=mapping.model_dump(mode="json"),
        )
        session.add(row)
        session.flush()
        record_event(
            session,
            actor,
            "mapping_config_created",
            "mapping_config",
            str(row.id),
            {"name": mapping.name, "version": 1, "header_hash": mapping.header_hash},
        )


def _ensure_counterparty(session: Session, counterparty_id: str, actor: str) -> None:
    if session.get(Counterparty, counterparty_id) is None:
        session.add(Counterparty(id=counterparty_id))
        record_event(session, actor, "counterparty_created", "counterparty", counterparty_id, {})


def _ingest_file(
    session: Session, spec: DomainSpec, directory: Path, entry: ManifestEntry, actor: str
) -> FileOutcome:
    content_bytes = (directory / entry.path).read_bytes()
    sha256 = hashlib.sha256(content_bytes).hexdigest()
    if session.scalar(select(File.id).where(File.sha256 == sha256)) is not None:
        return FileOutcome(entry.path, "skipped")

    _ensure_counterparty(session, entry.counterparty_id, actor)
    content = content_bytes.decode()
    file = File(
        sha256=sha256,
        source_path=entry.path,
        counterparty_id=entry.counterparty_id,
        schema_name=entry.schema_name,
        batch_id=entry.batch_id,
        header_hash=header_hash(content),
        status="ingested",  # provisional; set from the outcome below
        row_count=0,
        error_count=0,
    )
    mapping = spec.mapping_for(file.header_hash)

    if sha256 != entry.sha256:
        outcome = FileOutcome(entry.path, "rejected", message="sha256 does not match the manifest")
    elif mapping is None:
        outcome = FileOutcome(entry.path, "unmapped", message="no mapping for this header")
    elif mapping.schema_name != entry.schema_name:
        outcome = FileOutcome(
            entry.path,
            "rejected",
            message=f"mapping is for {mapping.schema_name}, manifest says {entry.schema_name}",
        )
    else:
        file.mapping_config_id = session.scalar(
            select(MappingConfigRow.id).where(
                MappingConfigRow.header_hash == mapping.header_hash,
                MappingConfigRow.status == "active",
            )
        )
        session.add(file)
        session.flush()
        outcome = _store_rows(session, spec, mapping, file, content, entry)

    file.status = outcome.status
    file.row_count, file.error_count, file.error = outcome.rows, outcome.errors, outcome.message
    session.add(file)
    session.flush()
    record_event(
        session,
        actor,
        f"file_{file.status}",
        "file",
        str(file.id),
        {
            "path": entry.path,
            "sha256": sha256,
            "schema_name": entry.schema_name,
            "rows": outcome.rows,
            "errors": outcome.errors,
            "message": outcome.message,
        },
    )
    return outcome


def _store_rows(
    session: Session,
    spec: DomainSpec,
    mapping: MappingConfig,
    file: File,
    content: str,
    entry: ManifestEntry,
) -> FileOutcome:
    schema = spec.schema(mapping.schema_name)
    try:
        normalized = normalize(mapping, content, batch_id=entry.batch_id)
        validated = (
            schema.validate_frame(canonical_frame([values for _, values in normalized.rows]))
            if normalized.rows
            else None
        )
    except (ValueError, pandera.errors.SchemaErrors) as exc:
        return FileOutcome(entry.path, "rejected", message=str(exc)[:2000])

    errors: list[RowError] = list(normalized.errors)
    file_rows = [number for number, _ in normalized.rows]
    if validated is not None:
        # validate_frame numbers rows within the frame; map back to file row numbers.
        errors += [RowError(file_rows[e.row_number - 1], e.messages) for e in validated.errors]
        invalid = {e.row_number for e in validated.errors}
        valid_numbers = [n for i, n in enumerate(file_rows, start=1) if i not in invalid]
        for row_number, row in zip(valid_numbers, validated.rows, strict=True):
            data = row.model_dump(mode="json")
            session.add(
                Record(
                    file_id=file.id,
                    row_number=row_number,
                    record_id=data[schema.record_id_field],
                    counterparty_id=entry.counterparty_id,
                    batch_id=data.get("batch_id", entry.batch_id),
                    schema_name=schema.name,
                    match_status="unmatched",
                    data=data,
                )
            )
    for error in sorted(errors, key=lambda e: e.row_number):
        session.add(
            RowErrorRow(file_id=file.id, row_number=error.row_number, messages=list(error.messages))
        )
    stored = len(validated.rows) if validated is not None else 0
    return FileOutcome(entry.path, "ingested", rows=stored, errors=len(errors))

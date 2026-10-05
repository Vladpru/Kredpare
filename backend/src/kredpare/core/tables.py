"""Persistent storage for ingest, matching, and audit. Core terms only."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from kredpare.core.db import Base

FILE_STATUSES = ("ingested", "unmapped", "rejected")
MATCH_STATUSES = ("unmatched", "matched", "in_break")


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class Counterparty(Base):
    __tablename__ = "counterparties"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    created_at: Mapped[datetime] = _created_at()


class MappingConfigRow(Base):
    __tablename__ = "mapping_configs"
    __table_args__ = (UniqueConstraint("header_hash", "version"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    header_hash: Mapped[str] = mapped_column(Text, index=True)
    name: Mapped[str] = mapped_column(Text)
    schema_name: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(Text)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _created_at()


class File(Base):
    __tablename__ = "files"
    __table_args__ = (CheckConstraint(f"status IN {FILE_STATUSES}", name="status"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    sha256: Mapped[str] = mapped_column(Text, unique=True)
    source_path: Mapped[str] = mapped_column(Text)
    counterparty_id: Mapped[str] = mapped_column(ForeignKey("counterparties.id"))
    schema_name: Mapped[str] = mapped_column(Text)
    batch_id: Mapped[str] = mapped_column(Text)
    header_hash: Mapped[str] = mapped_column(Text)
    mapping_config_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("mapping_configs.id"))
    status: Mapped[str] = mapped_column(Text)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()


class Record(Base):
    __tablename__ = "records"
    __table_args__ = (
        UniqueConstraint("file_id", "row_number"),
        CheckConstraint(f"match_status IN {MATCH_STATUSES}", name="match_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("files.id"))
    row_number: Mapped[int] = mapped_column(Integer)
    record_id: Mapped[str] = mapped_column(Text)
    counterparty_id: Mapped[str] = mapped_column(ForeignKey("counterparties.id"))
    batch_id: Mapped[str] = mapped_column(Text)
    schema_name: Mapped[str] = mapped_column(Text, index=True)
    match_status: Mapped[str] = mapped_column(Text, default="unmatched")
    data: Mapped[dict[str, Any]] = mapped_column(JSONB)
    """Canonical values in JSON form: money and ratios as exact decimal strings, ISO dates."""


class RowErrorRow(Base):
    __tablename__ = "row_errors"
    __table_args__ = (UniqueConstraint("file_id", "row_number"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("files.id"))
    row_number: Mapped[int] = mapped_column(Integer)
    messages: Mapped[list[str]] = mapped_column(JSONB)


class Break(Base):
    __tablename__ = "breaks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(Text, unique=True)
    """Natural key, so rerunning matching for the same as-of date never duplicates a break."""
    as_of: Mapped[date] = mapped_column(Date)
    break_type: Mapped[str] = mapped_column(Text, index=True)
    left_schema: Mapped[str] = mapped_column(Text)
    right_schema: Mapped[str | None] = mapped_column(Text)
    side_schema: Mapped[str | None] = mapped_column(Text)
    """The schema that is missing (missing_record, stale_pending) or duplicated (duplicate)."""
    counterparty_id: Mapped[str] = mapped_column(Text)
    batch_id: Mapped[str] = mapped_column(Text)
    record_id: Mapped[str] = mapped_column(Text)
    field: Mapped[str | None] = mapped_column(Text)
    left_record_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("records.id"))
    right_record_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("records.id"))
    left_value: Mapped[str | None] = mapped_column(Text)
    right_value: Mapped[str | None] = mapped_column(Text)
    delta: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    """right_value - left_value, for amount_mismatch."""
    status: Mapped[str] = mapped_column(Text, default="open")
    created_at: Mapped[datetime] = _created_at()


class AuditEvent(Base):
    """Append-only: a database trigger rejects UPDATE, DELETE, and TRUNCATE."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = _created_at()
    actor: Mapped[str] = mapped_column(Text)
    action: Mapped[str] = mapped_column(Text)
    entity_type: Mapped[str] = mapped_column(Text)
    entity_id: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)

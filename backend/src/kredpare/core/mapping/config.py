"""A versioned description of one source file format: which column becomes which field."""

import hashlib
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from kredpare.core.mapping.transforms import Transform


class ColumnMapping(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str
    target: str
    transform: Transform


class MappingConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    schema_name: str
    delimiter: str = ","
    columns: tuple[ColumnMapping, ...]
    """In file order: the header row is exactly these source names."""
    batch_id_from_metadata: bool = False
    """The file has no batch column; batch_id comes from upload metadata."""

    @model_validator(mode="after")
    def _unique(self) -> Self:
        for kind in ("source", "target"):
            names = [getattr(c, kind) for c in self.columns]
            if len(names) != len(set(names)):
                raise ValueError(f"duplicate {kind} columns in {self.name}")
        return self

    @property
    def header_line(self) -> str:
        return self.delimiter.join(c.source for c in self.columns)

    @property
    def header_hash(self) -> str:
        return _sha256(self.header_line)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def header_hash(content: str) -> str:
    """Hash of a file's first line, without its line ending."""
    return _sha256(content.split("\n", 1)[0].rstrip("\r"))

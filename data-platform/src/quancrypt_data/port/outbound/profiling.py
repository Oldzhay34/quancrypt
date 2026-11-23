"""Outbound ports of the profiling use case (P6.3): reading raw, the canonical dictionary, the secret scan and the
report."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

from quancrypt_data.domain.profiling import RawSnapshot, TableChecksum
from quancrypt_data.domain.profiling_report import ProfileReport


class RawDataReader(Protocol):
    """Reads the landing layer and never writes it (the adapter runs every read in a READ ONLY transaction)."""

    def checksums(self) -> Sequence[TableChecksum]: ...

    def snapshot(self) -> RawSnapshot: ...


class CanonicalDictionary(Protocol):
    """contracts/canonical_dictionary.csv: the raw spellings it maps and the canonical values of each column."""

    def raw_names(self) -> set[str]: ...

    def canonical_values(self) -> Mapping[str, set[str]]:
        """Values per column (`mode`, `padding`, `hash`)."""
        ...


class SecretScanner(Protocol):
    def scan(self, texts: Sequence[str]) -> Mapping[str, int]:
        """How many matches each rule of contracts/redaction-rules.yaml finds in the texts (never the matched text)."""
        ...


class ProfileReportWriter(Protocol):
    def write(self, report: ProfileReport) -> Sequence[str]:
        """Writes the report, its figures and `unmapped_values.csv`; returns where."""
        ...

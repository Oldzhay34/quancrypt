"""Fakes of the profiling ports (P6.3) and the cases every adapter of a port must pass, the fake and the real one alike
(solid-checklist L). The PostgreSQL reader runs the reader cases in its integration test (it needs a database)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from quancrypt_data.domain.profiling import RawSnapshot, TableChecksum
from quancrypt_data.domain.profiling_report import ProfileReport
from quancrypt_data.port.outbound.profiling import (
    CanonicalDictionary,
    ProfileReportWriter,
    RawDataReader,
    SecretScanner,
)

RAW_TABLES = ("raw.event", "quarantine.event", "raw.benchmark_label", "raw.benchmark_load")
# The md5 of an empty string: what every table digest is while raw is empty.
EMPTY_DIGEST = "d41d8cd98f00b204e9800998ecf8427e"


class InMemoryRawDataReader:
    def __init__(self, snapshot: RawSnapshot | None = None, checksums: Sequence[TableChecksum] | None = None) -> None:
        self._snapshot = snapshot or RawSnapshot()
        self._checksums = tuple(checksums or (TableChecksum(t, 0, EMPTY_DIGEST) for t in RAW_TABLES))
        self.calls: list[str] = []

    def checksums(self) -> Sequence[TableChecksum]:
        self.calls.append("checksums")
        return self._checksums

    def snapshot(self) -> RawSnapshot:
        self.calls.append("snapshot")
        return self._snapshot


class StaticDictionary:
    def __init__(self, raw_names: set[str], values: Mapping[str, set[str]]) -> None:
        self._raw_names = set(raw_names)
        self._values = {column: set(values.get(column, set())) for column in ("mode", "padding", "hash")}

    def raw_names(self) -> set[str]:
        return set(self._raw_names)

    def canonical_values(self) -> Mapping[str, set[str]]:
        return {column: set(values) for column, values in self._values.items()}


class AtSignScanner:
    """Counts e-mail-like texts only: enough to stand in for the redaction rules in a use case test."""

    def scan(self, texts: Sequence[str]) -> Mapping[str, int]:
        found = sum(text.count("@") for text in texts)
        return {"email": found} if found else {}


class RecordingReportWriter:
    def __init__(self) -> None:
        self.reports: list[ProfileReport] = []

    def write(self, report: ProfileReport) -> Sequence[str]:
        self.reports.append(report)
        return ["reports/profiling_report.md"]


def check_reader_on_an_empty_raw(reader: RawDataReader) -> None:
    first, second = reader.checksums(), reader.checksums()
    assert first == second, "reading twice changes nothing"
    assert {c.table for c in first} == set(RAW_TABLES)
    assert all(c.rows == 0 and c.digest == EMPTY_DIGEST for c in first)
    snapshot = reader.snapshot()
    assert (snapshot.findings, snapshot.sources, snapshot.quarantine) == ((), (), ())


def check_dictionary(dictionary: CanonicalDictionary, known_raw: str, known_mode: str) -> None:
    names = dictionary.raw_names()
    assert known_raw in names and all(isinstance(n, str) for n in names)
    values = dictionary.canonical_values()
    assert set(values) >= {"mode", "padding", "hash"}
    assert known_mode in values["mode"]
    assert dictionary.raw_names() == names, "every call answers the same"


def check_scanner(scanner: SecretScanner) -> None:
    assert dict(scanner.scan([])) == {}
    assert dict(scanner.scan(["SHA256withRSA", "src/main/java/A.java"])) == {}
    text = "contact someone@example.com"
    hits = dict(scanner.scan([text]))
    assert hits and all(isinstance(rule, str) and count > 0 for rule, count in hits.items())
    assert all(text not in rule and "someone" not in rule for rule in hits), "only rule names, never the text"


def check_writer(writer: ProfileReportWriter, report: ProfileReport) -> None:
    written = writer.write(report)
    assert written and all(isinstance(path, str) for path in written)
    assert any(path.endswith("profiling_report.md") for path in written)

"""The outbound ports of the profiling use case (P6.3): the fake and the real adapter of each port pass the same cases
(solid-checklist L). The PostgreSQL reader runs the reader cases in tests/integration/test_profiling_postgres.py."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from quancrypt_data.domain.profiling import RawSnapshot
from quancrypt_data.domain.profiling_report import build_report
from quancrypt_data.infrastructure.profiling.dictionary_csv import CsvCanonicalDictionary
from quancrypt_data.infrastructure.profiling.report_files import FileProfileReportWriter
from quancrypt_data.infrastructure.redaction.redactor import Redactor
from quancrypt_data.port.outbound.profiling import CanonicalDictionary, ProfileReportWriter, SecretScanner
from tests.support.profiling_fakes import (
    AtSignScanner,
    InMemoryRawDataReader,
    RecordingReportWriter,
    StaticDictionary,
    check_dictionary,
    check_reader_on_an_empty_raw,
    check_scanner,
    check_writer,
)

CONTRACTS = Path(__file__).resolve().parents[3] / "contracts"


def test_the_fake_reader_passes_the_reader_cases() -> None:
    check_reader_on_an_empty_raw(InMemoryRawDataReader())


@pytest.mark.parametrize("kind", ["fake", "csv"])
def test_every_dictionary_passes_the_dictionary_cases(kind: str) -> None:
    dictionary: CanonicalDictionary = (
        StaticDictionary({"SHA256withRSA"}, {"mode": {"ECB"}})
        if kind == "fake"
        else CsvCanonicalDictionary(CONTRACTS / "canonical_dictionary.csv")
    )

    check_dictionary(dictionary, known_raw="SHA256withRSA", known_mode="ECB")


@pytest.mark.parametrize("kind", ["fake", "redactor"])
def test_every_scanner_passes_the_scanner_cases(kind: str) -> None:
    scanner: SecretScanner = (
        AtSignScanner() if kind == "fake" else Redactor.from_file(CONTRACTS / "redaction-rules.yaml")
    )

    check_scanner(scanner)


@pytest.mark.parametrize("kind", ["fake", "files"])
def test_every_report_writer_passes_the_writer_cases(kind: str, tmp_path: Path) -> None:
    writer: ProfileReportWriter = (
        RecordingReportWriter() if kind == "fake" else FileProfileReportWriter(tmp_path, lambda _: True)
    )
    report = build_report(
        RawSnapshot(),
        known_raw_names=set(),
        known_values={},
        secret_hits={},
        before=(),
        after=(),
        generated_at=datetime(2026, 11, 23, tzinfo=UTC),
    )

    check_writer(writer, report)

"""The profiling adapters (P6.3): the redaction scan against the shared vectors, the real canonical dictionary, the report
files (sections, figures, unmapped values, nothing secret shown)."""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from quancrypt_data.domain.profiling import FindingRecord, QuarantineRecord, RawSnapshot, TableChecksum, TextSample
from quancrypt_data.domain.profiling_report import build_report
from quancrypt_data.infrastructure.profiling.dictionary_csv import CsvCanonicalDictionary, DictionaryError
from quancrypt_data.infrastructure.profiling.report_files import FileProfileReportWriter
from quancrypt_data.infrastructure.redaction.redactor import Redactor

CONTRACTS = Path(__file__).resolve().parents[3] / "contracts"
VECTORS = yaml.safe_load((CONTRACTS / "testdata" / "redaction" / "vectors.yaml").read_text(encoding="utf-8"))["vectors"]
SECTIONS = (
    "## 1. Kaynaklar ve zaman aralığı",
    "## 2. Kolon profilleri",
    "## 3. Ham yazım çeşitliliği",
    "## 4. Tekrarlar",
    "## 5. Proje başına bulgu dağılımı ve aykırı adaylar",
    "## 6. Şema ihlalleri",
    "## 7. Kişisel veri ve sır taraması",
    "## 8. Öneriler",
    "## Ek: raw değişmedi mi?",
)


@pytest.fixture(scope="module")
def redactor() -> Redactor:
    return Redactor.from_file(CONTRACTS / "redaction-rules.yaml")


class TestRedactor:
    @pytest.mark.parametrize("vector", VECTORS, ids=lambda v: v["id"])
    def test_the_shared_vectors_hold_for_the_data_platform_copy(
        self, redactor: Redactor, vector: dict[str, object]
    ) -> None:
        text = str(vector["input"])
        output = redactor.redact(text)
        if vector["kind"] == "positive":
            assert f"[REDACTED:{vector['rule']}]" in output
            for secret in vector.get("secrets", []):  # type: ignore[attr-defined]
                assert secret not in output
        else:
            assert output == text

    def test_the_scan_counts_matches_per_rule_and_never_returns_text(self, redactor: Redactor) -> None:
        hits = redactor.scan(["contact: someone@example.com", "nothing here", "a@example.com and b@example.com"])

        assert hits == {"email": 3}

    def test_a_clean_text_has_no_hit(self, redactor: Redactor) -> None:
        assert redactor.scan(["RSA/ECB/PKCS1Padding", "SHA256withRSA"]) == {}


class TestDictionary:
    def test_the_real_dictionary_knows_its_raw_names_and_canonical_values(self) -> None:
        dictionary = CsvCanonicalDictionary(CONTRACTS / "canonical_dictionary.csv")

        assert "AES" in dictionary.raw_names()
        values = dictionary.canonical_values()
        assert set(values) == {"mode", "padding", "hash"}
        assert all(values[column] for column in values)

    def test_a_missing_dictionary_is_an_error_naming_the_file_only(self, tmp_path: Path) -> None:
        with pytest.raises(DictionaryError, match="canonical_dictionary.csv"):
            CsvCanonicalDictionary(tmp_path / "canonical_dictionary.csv")


def finding(**fields: object) -> FindingRecord:
    base: dict[str, object] = {
        "source": "corpus", "project_key": "a" * 64, "algorithm_family": "RSA", "usage_context": "SIGNATURE",
        "location_kind": "CODE", "priority": "P0", "key_size_bits": 2048, "confidence": 0.9,
        "file": "secret-module/src/main/java/A.java", "line_start": 3, "raw_name": "SHA1withRSA",
        "hash": "SHA-1", "library": "JCA",
    }  # fmt: skip
    base.update(fields)
    return FindingRecord(**base)  # type: ignore[arg-type]


class TestReportFiles:
    def test_the_report_has_every_section_and_the_figures_and_csv_are_written(
        self, tmp_path: Path, redactor: Redactor
    ) -> None:
        snapshot = RawSnapshot(
            findings=(
                finding(),
                finding(raw_name="Unknown/Spelling", algorithm_family="UNKNOWN"),
                finding(raw_name="leak someone@example.com"),
                # algorithm-name shaped, but the high-entropy rule matches it: listed in the CSV, never shown
                finding(raw_name="Zq8vX2mN4pL7rT1yW9bK3cF6hJ0dG5sA", algorithm_family="UNKNOWN"),
                *(finding(project_key=f"{i:064x}") for i in range(5)),
            ),
            quarantine=(QuarantineRecord("schema-violation", "payload.priority: enum"),),
            texts=(TextSample("findings.raw_name", "leak someone@example.com"),),
        )
        report = build_report(
            snapshot,
            known_raw_names={"SHA1withRSA"},
            known_values={"hash": {"SHA-1"}, "mode": set(), "padding": set()},
            secret_hits=redactor.scan([t.text for t in snapshot.texts]),
            before=(TableChecksum("raw.event", 8, "x"),),
            after=(TableChecksum("raw.event", 8, "x"),),
            generated_at=datetime(2026, 10, 29, tzinfo=UTC),
        )
        writer = FileProfileReportWriter(tmp_path, lambda text: not redactor.scan([text]))

        written = writer.write(report)

        text = (tmp_path / "profiling_report.md").read_text(encoding="utf-8")
        for section in SECTIONS:
            assert section in text
        for figure in ("findings_per_project", "records_per_source", "quarantine_reasons", "raw_name_variety"):
            assert (tmp_path / "figures" / f"{figure}.png").stat().st_size > 0
        assert len(written) == 6
        assert "someone@example.com" not in text, "a spelling a redaction rule matches is never shown"
        assert "secret-module" not in text, "file paths are not written to the report"
        assert "a" * 64 not in text, "a project key appears shortened only"
        assert "raw değişmedi" in text
        with (tmp_path / "unmapped_values.csv").open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        assert [r["raw"] for r in rows] == ["Unknown/Spelling", "[gizlendi: redaksiyon kuralı eşleşti]"]
        assert list(rows[0]) == ["kind", "raw", "frequency", "projects"]

    def test_crafted_spellings_neither_break_the_report_nor_become_markup_or_formulas(self, tmp_path: Path) -> None:
        snapshot = RawSnapshot(
            findings=(
                finding(raw_name="$\\frac$", key_size_bits=1024),  # mathtext would fail in the chart
                finding(raw_name="a`b<img src=x>", key_size_bits=4096),
                finding(mode="-cmd", key_size_bits=None),
            ),
            project_keys=frozenset({"a" * 64, "b" * 64, "c" * 64}),
        )
        report = build_report(
            snapshot,
            known_raw_names=set(),
            known_values={"mode": set(), "padding": set(), "hash": {"SHA-1"}},
            secret_hits={},
            before=(),
            after=(),
            generated_at=datetime(2026, 11, 23, tzinfo=UTC),
        )

        FileProfileReportWriter(tmp_path, lambda _: True).write(report)

        text = (tmp_path / "profiling_report.md").read_text(encoding="utf-8")
        assert "| findings | key_size_bits | number | 3 | 33.3% | 2 | 1024 | 4096 |" in text, "whole numbers in full"
        assert "`a'b<img src=x>`" in text, "a backtick cannot close the code span"
        assert "Raw'daki 3 projenin 1 tanesinde bulgu var" in text
        with (tmp_path / "unmapped_values.csv").open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        assert {r["raw"] for r in rows if r["kind"] == "mode"} == {"'-cmd"}, "a formula-like cell stays text"

    def test_an_empty_raw_still_gives_every_section_and_empty_figures(self, tmp_path: Path) -> None:
        report = build_report(
            RawSnapshot(), known_raw_names=set(), known_values={}, secret_hits={}, before=(), after=(),
            generated_at=datetime(2026, 10, 29, tzinfo=UTC),
        )  # fmt: skip

        FileProfileReportWriter(tmp_path, lambda text: True).write(report)

        text = (tmp_path / "profiling_report.md").read_text(encoding="utf-8")
        assert all(section in text for section in SECTIONS)
        assert "Kanıtı olan öneri yok." in text
        assert (tmp_path / "figures" / "findings_per_project.png").exists()

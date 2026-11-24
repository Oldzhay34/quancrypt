"""The preprocessing adapters (P6.4): the filters that read contract files (event schemas, canonical dictionary,
redaction rules), the report files, and the in-memory port fakes through the shared port cases."""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path

import pytest

from quancrypt_data.domain.prep import FindingRow, LabelRow, PrepBatch, ProjectRow, RawEvent, UnitRow, run_filters
from quancrypt_data.domain.prep_extract import extract
from quancrypt_data.domain.prep_report import build_report
from quancrypt_data.infrastructure.filters.anonymizer import Anonymizer, IdentifierLeak
from quancrypt_data.infrastructure.filters.canonicalizer import Canonicalizer
from quancrypt_data.infrastructure.filters.schema_validator import SchemaValidator
from quancrypt_data.infrastructure.prep.report_files import FilePrepReportWriter
from quancrypt_data.infrastructure.profiling.dictionary_csv import CsvCanonicalDictionary
from quancrypt_data.infrastructure.redaction.redactor import Redactor
from quancrypt_data.infrastructure.schema.json_schema_catalog import JsonSchemaCatalog
from quancrypt_data.port.outbound.prep import TableStat
from tests.support.envelopes import KEY_A, envelope
from tests.support.prep_fakes import (
    InMemoryPrepStore,
    InMemoryRawEventSource,
    check_repository_replaces_a_project,
    check_source_on_an_empty_raw,
)

CONTRACTS = Path(__file__).resolve().parents[3] / "contracts"
SALT = "s" * 40
NOW = datetime(2026, 11, 23, tzinfo=UTC)


@pytest.fixture(scope="module")
def redactor() -> Redactor:
    return Redactor.from_file(CONTRACTS / "redaction-rules.yaml")


def raw(item: dict[str, object]) -> RawEvent:
    return RawEvent(
        str(item["event_id"]), str(item["event_type"]), "core-service", 1,
        datetime.fromisoformat(str(item["occurred_at"]).replace("Z", "+00:00")), str(item["project_key"]),
        dict(item["payload"]),  # type: ignore[call-overload]
    )  # fmt: skip


def finding(**fields: object) -> FindingRow:
    base: dict[str, object] = {
        "id": "f1", "source_event_id": "e1", "project_key": KEY_A, "unit_path": ".", "file_path": "src/main/java/A.java",
        "line_start": 3, "line_end": 3, "algorithm_family": "RSA", "usage_context": "SIGNATURE", "location_kind": "CODE",
        "priority": "P2", "key_size_bits": 2048, "confidence": 0.9,
    }  # fmt: skip
    base.update(fields)
    return FindingRow(**base)  # type: ignore[arg-type]


class TestSchemaValidator:
    def test_a_valid_event_passes_and_an_invalid_one_goes_with_all_its_rows(self) -> None:
        good = raw(envelope("finding_detected"))
        bad = raw(envelope("finding_detected", payload={**envelope("finding_detected")["payload"], "priority": "P9"}))
        validator = SchemaValidator(JsonSchemaCatalog(CONTRACTS / "schemas" / "events"))

        result = validator.apply(extract([good, bad], []))

        assert [f.source_event_id for f in result.batch.findings] == [good.event_id]
        (rejection,) = result.rejected
        assert (rejection.error_code, rejection.raw_event_id, rejection.rows) == ("schema-violation", bad.event_id, 1)
        assert "P9" not in rejection.message, "the reason names the rule, never the value"


@pytest.fixture(scope="module")
def dictionary() -> CsvCanonicalDictionary:
    return CsvCanonicalDictionary(CONTRACTS / "canonical_dictionary.csv")


class TestCanonicalizer:
    def test_the_dictionary_cases_of_the_skill_are_canonical_values_the_filter_keeps(
        self, dictionary: CsvCanonicalDictionary
    ) -> None:
        # data-preprocessing section 3: RSA/ECB/PKCS1Padding, SHA256withRSA, RS256, the RSA OID, 2K.
        rows = {
            (r["kind"], r["raw"]): r
            for r in csv.DictReader((CONTRACTS / "canonical_dictionary.csv").open(encoding="utf-8", newline=""))
        }
        cases = [rows[("transformation", "RSA")], rows[("signature", "SHA256withRSA")], rows[("jwt_alg", "RS256")],
                 rows[("oid", "1.2.840.113549.1.1.1")]]  # fmt: skip
        assert rows[("key_size", "2K")]["key_size_bits"] == "2048"
        findings = tuple(
            finding(
                id=str(n), algorithm_family=c["algorithm_family"], usage_context=c["usage_context"] or "UNKNOWN",
                mode=c["mode"] or None, padding=c["padding"] or None, hash=c["hash"] or None, library="JCA",
            )
            for n, c in enumerate(cases)
        )  # fmt: skip

        result = Canonicalizer(dictionary).apply(PrepBatch(findings=findings))

        assert result.batch.findings == findings and result.notes == {}

    def test_a_value_outside_the_dictionary_becomes_unknown_and_the_finding_stays(
        self, dictionary: CsvCanonicalDictionary
    ) -> None:
        row = finding(padding="PKCS1Padding", library="some-lib", algorithm_family="ROT13")

        result = Canonicalizer(dictionary).apply(PrepBatch(findings=(row,)))

        (kept,) = result.batch.findings
        assert (kept.padding, kept.library, kept.algorithm_family) == ("UNKNOWN", "UNKNOWN", "UNKNOWN")
        assert result.notes == {
            "algorithm_family_set_to_unknown": 1, "library_set_to_unknown": 1, "padding_set_to_unknown": 1
        }  # fmt: skip


class TestAnonymizer:
    def test_paths_keep_the_source_layout_and_extension_and_hash_the_rest(self, redactor: Redactor) -> None:
        anonymizer = Anonymizer(SALT, redactor)
        acme = anonymizer.segment("acme")

        assert anonymizer.path("src/main/java/com/acme/Shop.java") == (
            f"src/main/java/{anonymizer.segment('com')}/{acme}/{anonymizer.segment('Shop')}.java"
        )
        assert anonymizer.path("pom.xml") == "pom.xml"
        assert (
            anonymizer.path("acme/src/main/resources/application.yml") == f"{acme}/src/main/resources/application.yml"
        )
        assert anonymizer.path(".") == "."
        assert len(acme) == 12 and acme == Anonymizer(SALT, redactor).segment("acme"), "the same name, the same digest"

    @pytest.mark.parametrize("path", ["/home/a/A.java", "C:/x/A.java", "a/../b.java", "https://x/A.java", "a@b/A.java"])
    def test_a_raw_identifier_is_refused(self, redactor: Redactor, path: str) -> None:
        with pytest.raises(IdentifierLeak):
            Anonymizer(SALT, redactor).path(path)

    def test_rows_with_a_raw_identifier_or_a_secret_are_set_aside_and_units_follow(self, redactor: Redactor) -> None:
        anonymizer = Anonymizer(SALT, redactor)
        batch = PrepBatch(
            projects=(ProjectRow(KEY_A, "CORPUS"),),
            units=(UnitRow(KEY_A, "svc-a", "21", None),),
            findings=(
                finding(id="1", unit_path="svc-a"),
                finding(id="2", unit_path="svc-a", file_path="/etc/ssl/key.pem", source_event_id="e2"),
                finding(id="3", unit_path="svc-a", library="mail someone@example.com", source_event_id="e3"),
            ),
            labels=(LabelRow("owasp-benchmark", "c1", "src/main/java/BenchmarkTest00001.java", "crypto", 327, True),),
        )

        result = anonymizer.apply(batch)

        assert [f.id for f in result.batch.findings] == ["1"]
        assert result.batch.findings[0].unit_path == result.batch.units[0].unit_path == anonymizer.segment("svc-a")
        assert [(r.error_code, r.raw_event_id) for r in result.rejected] == [
            ("identifier-leak", "e2"),
            ("secret-match", "e3"),
        ]
        assert result.batch.labels[0].file_path == anonymizer.path("src/main/java/BenchmarkTest00001.java")

    def test_a_unit_name_is_all_directory_and_a_file_extension_that_can_carry_a_name_is_hashed(
        self, redactor: Redactor
    ) -> None:
        anonymizer = Anonymizer(SALT, redactor)

        assert anonymizer.path("acme-billing.gateway", directory=True) == anonymizer.segment("acme-billing.gateway")
        assert "gateway" not in anonymizer.path("svc/payment.internalname", directory=True)
        for path in ("config/app.olcay-yilmaz", "Dockerfile.acmebank", "x/.env.acmebank", "a/application.qbank-prod"):
            anonymized = anonymizer.path(path)
            assert not any(word in anonymized for word in ("olcay", "acmebank", "qbank")), (path, anonymized)
        assert anonymizer.path("settings.gradle.kts") == "settings.gradle.kts"
        assert anonymizer.path("a/b/Foo.java").endswith(".java")

    def test_a_unit_whose_name_is_a_raw_identifier_sets_its_events_aside_instead_of_stopping_the_run(
        self, redactor: Redactor
    ) -> None:
        anonymizer = Anonymizer(SALT, redactor)
        events = (
            RawEvent("e1", "corpus_analysis", "corpus", 1, NOW, KEY_A, {"analysis_unit": ".."}),
            RawEvent("e2", "corpus_analysis", "corpus", 1, NOW, KEY_A, {"analysis_unit": "svc"}),
        )
        batch = PrepBatch(
            events=events,
            projects=(ProjectRow(KEY_A, "CORPUS"),),
            units=(UnitRow(KEY_A, ".."), UnitRow(KEY_A, "svc")),
            findings=(
                finding(id="1", unit_path="..", source_event_id="e1"),
                finding(id="2", unit_path="svc", source_event_id="e2"),
            ),
        )

        result = anonymizer.apply(batch)

        assert [(r.error_code, r.raw_event_id, r.rows) for r in result.rejected] == [("identifier-leak", "e1", 1)]
        assert [f.id for f in result.batch.findings] == ["2"]
        assert [u.unit_path for u in result.batch.units] == [anonymizer.segment("svc")]

    def test_a_short_or_placeholder_salt_is_refused(self, redactor: Redactor) -> None:
        with pytest.raises(ValueError, match="salt"):
            Anonymizer("CHANGE_ME" * 5, redactor)


class TestReportFiles:
    def test_the_report_has_every_section_and_the_funnel_and_shows_no_path_or_key(self, tmp_path: Path) -> None:
        event = raw(envelope("corpus_analysis"))
        extracted = extract([event], [])
        final, rejected, counts = run_filters(extracted, [])
        report = build_report(
            extracted=extracted, final=final, counts=counts, rejected=rejected, leaks={"email": 1}, generated_at=NOW
        )

        written = FilePrepReportWriter(tmp_path).write(report, [TableStat("prep.finding", 3, {"key_size_bits": 0.5})])

        text = (tmp_path / "preprocessing_report.md").read_text(encoding="utf-8")
        for section in ("## 1. Filtre hunisi", "## 2. Kanonikleştirme", "## 3. Karantina", "## 4. Sızıntı kontrolü",
                        "## 5. prep tabloları", "## 6. Hedef kontrolü"):  # fmt: skip
            assert section in text
        assert "Sızıntı sıfır değil" in text and "key_size_bits %50.0" in text
        assert KEY_A not in text and "src/main" not in text
        assert (tmp_path / "figures" / "prep_funnel.png").stat().st_size > 0 and len(written) == 2


class TestPortFakes:
    def test_the_fake_source_passes_the_source_cases(self) -> None:
        check_source_on_an_empty_raw(InMemoryRawEventSource())

    def test_the_fake_store_passes_the_repository_cases(self) -> None:
        store = InMemoryPrepStore()
        check_repository_replaces_a_project(store, store)

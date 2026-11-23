"""The profiling metrics and recommendation rules (P6.3) on a small fixed data set."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from quancrypt_data.domain.profiling import (
    Duplicates,
    FindingRecord,
    ProfileFacts,
    QuarantineRecord,
    RawSnapshot,
    TableChecksum,
    column_profile,
    duplicates,
    findings_per_project,
    outliers,
    path_class,
    recommendations,
    spelling_variety,
    unmapped_values,
)
from quancrypt_data.domain.profiling_report import build_report
from quancrypt_data.facade.profiling_facade import ProfilingFacade, RawDataChangedError
from quancrypt_data.port.inbound.profiling import ProfileRawDataResult
from quancrypt_data.usecase.profile_raw_data_service import ProfileRawDataService
from tests.support.profiling_fakes import AtSignScanner, InMemoryRawDataReader, RecordingReportWriter, StaticDictionary

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)


def finding(key: str = "a" * 64, **fields: object) -> FindingRecord:
    base: dict[str, object] = {
        "source": "corpus",
        "project_key": key,
        "algorithm_family": "RSA",
        "usage_context": "SIGNATURE",
        "location_kind": "CODE",
        "priority": "P0",
        "key_size_bits": 2048,
        "confidence": 0.9,
        "file": "src/main/java/A.java",
        "line_start": 10,
        "raw_name": "SHA1withRSA",
        "mode": None,
        "padding": None,
        "hash": "SHA-1",
        "library": "JCA",
    }
    base.update(fields)
    return FindingRecord(**base)  # type: ignore[arg-type]


class TestColumnProfile:
    def test_numbers_get_the_summary_statistics(self) -> None:
        profile = column_profile("t", "c", [1, 2, 3, 4, None])

        assert (profile.kind, profile.count, profile.nulls, profile.distinct) == ("number", 5, 1, 4)
        assert (profile.minimum, profile.maximum, profile.mean, profile.median) == (1, 4, 2.5, 2.5)
        assert profile.null_ratio == pytest.approx(0.2)
        assert profile.skewness == pytest.approx(0.0)

    def test_a_long_right_tail_has_positive_skewness(self) -> None:
        assert (column_profile("t", "c", [1, 1, 1, 1, 100]).skewness or 0) > 1

    def test_constant_numbers_have_no_skewness_and_no_division_by_zero(self) -> None:
        assert column_profile("t", "c", [5, 5, 5]).skewness == 0.0

    @pytest.mark.parametrize(
        ("values", "kind"),
        [([], "empty"), ([None, None], "empty"), (["a", "b", None], "text"), ([True, False], "bool")],
    )
    def test_other_values_get_their_kind_and_counts_only(self, values: list[object], kind: str) -> None:
        profile = column_profile("t", "c", values)

        assert profile.kind == kind
        assert profile.mean is None

    def test_mixed_numbers_and_text_are_text(self) -> None:
        assert column_profile("t", "c", [1, "x"]).kind == "text"


class TestSpellingsAndDuplicates:
    def test_spellings_are_counted_most_frequent_first(self) -> None:
        findings = [finding(raw_name="RSA"), finding(raw_name="rsa"), finding(raw_name="RSA"), finding(raw_name=None)]

        assert spelling_variety(findings, "raw_name") == [("RSA", 2), ("rsa", 1)]

    def test_duplicates_are_the_same_project_file_line_algorithm_and_context(self) -> None:
        findings = [
            finding(),
            finding(),
            finding(),  # three of the same: one group, two extra rows
            finding(line_start=11),
            finding(key="b" * 64),
            finding(usage_context="ENCRYPTION"),
            finding(file=None),  # a coded finding has no location and is never a duplicate
            finding(file=None),
        ]

        assert duplicates(findings) == Duplicates(groups=1, extra_rows=2)


class TestPaths:
    @pytest.mark.parametrize(
        ("path", "cls"),
        [
            ("src/main/java/A.java", "main"),
            ("svc/src/test/java/ATest.java", "test"),
            ("src/main/java/CryptoTests.java", "test"),
            ("src/main/java/CryptoIT.java", "test"),
            ("svc/target/generated-sources/A.java", "generated"),
            ("build/classes/A.java", "generated"),
            ("web/node_modules/x/a.js", "generated"),
            ("svc/generated/A.java", "generated"),
            ("target.java", "main"),
        ],
    )
    def test_a_path_is_main_test_or_generated(self, path: str, cls: str) -> None:
        assert path_class(path) == cls


class TestOutliers:
    def test_fewer_than_four_projects_give_no_threshold(self) -> None:
        assert outliers({"a": 1, "b": 2, "c": 300}).threshold is None

    def test_a_project_far_above_q3_plus_three_iqr_is_a_candidate(self) -> None:
        per_project = {"p1": 10, "p2": 12, "p3": 11, "p4": 13, "p5": 9, "big": 500}

        report = outliers(per_project)

        assert report.threshold is not None and report.threshold < 500
        assert report.outliers == (("big", 500),)

    def test_an_even_distribution_has_no_candidate(self) -> None:
        assert outliers({f"p{i}": 10 for i in range(8)}).outliers == ()

    def test_findings_are_counted_per_project(self) -> None:
        assert findings_per_project([finding(), finding(), finding(key="b" * 64)]) == {"a" * 64: 2, "b" * 64: 1}


class TestUnmapped:
    def test_spellings_the_dictionary_does_not_know_are_listed_with_frequency_and_projects(self) -> None:
        findings = [
            finding(raw_name="SHA1withRSA", algorithm_family="UNKNOWN"),  # known
            finding(raw_name="sha1withrsa", algorithm_family="UNKNOWN"),  # known, other case
            finding(raw_name="NONEwithECDSA", algorithm_family="UNKNOWN", hash="SHA-1"),
            finding(key="b" * 64, raw_name="NONEwithECDSA", algorithm_family="UNKNOWN"),
            finding(raw_name="AES/ECB/PKCS5Padding", algorithm_family="AES"),  # canonicalised by its parts
            finding(raw_name="SSLContext:TLS", algorithm_family="UNKNOWN"),  # an analyzer label, not a spelling
            finding(raw_name="JKS keystore", algorithm_family="UNKNOWN"),  # an analyzer label, not a spelling
            finding(raw_name="unrecognized", algorithm_family="UNKNOWN"),  # the analyzer's own marker
            finding(mode="GCM-SIV"),
        ]

        result = unmapped_values(findings, {"SHA1withRSA"}, {"mode": {"GCM"}, "padding": set(), "hash": {"SHA-1"}})

        assert [(v.kind, v.raw, v.frequency, v.projects) for v in result] == [
            ("raw_name", "NONEwithECDSA", 2, 2),
            ("mode", "GCM-SIV", 1, 1),
        ]


class TestRecommendations:
    def test_no_evidence_means_no_recommendation(self) -> None:
        assert recommendations(ProfileFacts()) == []

    def test_each_filter_with_evidence_gets_one_numbered_recommendation_in_filter_order(self) -> None:
        facts = ProfileFacts(
            quarantined={"schema-violation": 3},
            duplicates=Duplicates(1, 2),
            path_classes={"generated": 4, "test": 5},
            test_code_findings=5,
            unmapped=7,
            secret_hits={"email": 1},
            findings_with_path=20,
            unknown_key_size=6,
            unknown_algorithm=2,
            outliers=1,
            findings=20,
        )

        result = recommendations(facts)

        assert [r.filter for r in result] == [
            "SchemaValidator",
            "Deduplicator",
            "GeneratedCodeExcluder",
            "TestCodeFlagger",
            "Canonicalizer",
            "Anonymizer",
            "MissingValueHandler",
            "OutlierFlagger",
        ]
        assert [r.number for r in result] == list(range(1, 9))
        assert "schema-violation: 3" in result[0].evidence
        assert "email: 1" in result[5].evidence


class TestReport:
    def test_an_empty_raw_gives_a_report_with_no_recommendation(self) -> None:
        checks = (TableChecksum("raw.event", 0, "d41d8cd98f00b204e9800998ecf8427e"),)

        report = build_report(
            RawSnapshot(),
            known_raw_names=set(),
            known_values={},
            secret_hits={},
            before=checks,
            after=checks,
            generated_at=NOW,
        )

        assert report.recommendations == []
        assert report.unchanged
        assert report.per_project == {}

    def test_a_change_between_the_two_checksums_is_reported(self) -> None:
        report = build_report(
            RawSnapshot(),
            known_raw_names=set(),
            known_values={},
            secret_hits={},
            before=(TableChecksum("raw.event", 1, "x"),),
            after=(TableChecksum("raw.event", 2, "y"),),
            generated_at=NOW,
        )

        assert not report.unchanged

    def test_the_report_brings_the_metrics_together(self) -> None:
        snapshot = RawSnapshot(
            findings=(
                finding(),
                finding(),
                finding(file="t/target/A.java", raw_name="Odd/Name", algorithm_family="UNKNOWN"),
                finding(key_size_bits=None),
            ),
            quarantine=(QuarantineRecord("schema-violation", "payload.priority: enum"),),
        )

        report = build_report(
            snapshot,
            known_raw_names={"SHA1withRSA"},
            known_values={"hash": {"SHA-1"}},
            secret_hits={},
            before=(),
            after=(),
            generated_at=NOW,
        )

        assert report.duplicates.extra_rows == 2
        assert report.path_classes == {"main": 3, "generated": 1}
        assert [u.raw for u in report.unmapped] == ["Odd/Name"]
        assert report.quarantine_reasons == {"schema-violation": 1}
        assert {r.filter for r in report.recommendations} >= {
            "SchemaValidator", "Deduplicator", "GeneratedCodeExcluder", "Canonicalizer", "Anonymizer", "MissingValueHandler"
        }  # fmt: skip


class TestService:
    def test_the_service_reads_twice_around_the_snapshot_and_writes_the_report(self) -> None:
        reader = InMemoryRawDataReader(
            RawSnapshot(findings=(finding(), finding(key="b" * 64))), (TableChecksum("raw.event", 2, "x"),)
        )
        writer = RecordingReportWriter()

        result = ProfileRawDataService(
            reader, StaticDictionary({"SHA1withRSA"}, {"hash": {"SHA-1"}}), AtSignScanner(), writer, FixedClock()
        ).execute()

        assert reader.calls == ["checksums", "snapshot", "checksums"]
        assert (result.findings, result.projects, result.unmapped, result.unchanged) == (2, 2, 0, True)
        assert result.written == ("reports/profiling_report.md",)
        assert writer.reports[0].generated_at == NOW


class FixedClock:
    def now(self) -> datetime:
        return NOW


class StubUseCase:
    def __init__(self, unchanged: bool) -> None:
        self._unchanged = unchanged

    def execute(self) -> ProfileRawDataResult:
        return ProfileRawDataResult(("reports/profiling_report.md",), 1, 330, 25, 1, 5, self._unchanged)


class TestFacade:
    def test_the_counts_and_the_written_files_are_shown(self) -> None:
        view = ProfilingFacade(StubUseCase(unchanged=True)).profile()

        assert view.counts == {
            "sources": 1, "findings": 330, "projects": 25, "unmapped_values": 1, "recommendations": 5
        }  # fmt: skip
        assert view.notes == ("written: reports/profiling_report.md",)

    def test_a_raw_that_changed_while_it_was_profiled_is_an_error(self) -> None:
        with pytest.raises(RawDataChangedError, match="raw changed while it was being profiled"):
            ProfilingFacade(StubUseCase(unchanged=False)).profile()

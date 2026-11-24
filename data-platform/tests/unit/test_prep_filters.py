"""The pure preprocessing filters, the extraction of raw events and the funnel counters (P6.4)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone

import pytest

from quancrypt_data.domain.filters.deduplicator import Deduplicator
from quancrypt_data.domain.filters.generated_code_excluder import GeneratedCodeExcluder
from quancrypt_data.domain.filters.missing_value_handler import MissingValueHandler
from quancrypt_data.domain.filters.outlier_flagger import OutlierFlagger
from quancrypt_data.domain.filters.test_code_flagger import TestCodeFlagger
from quancrypt_data.domain.filters.type_caster import TypeCaster
from quancrypt_data.domain.prep import (
    FILTER_ORDER,
    FilterResult,
    FindingRow,
    LabelRow,
    LinkRow,
    PrepBatch,
    ProjectRow,
    RawEvent,
    RawLabel,
    Rejection,
    ScopeRow,
    UnitRow,
    row_id,
    run_filters,
)
from quancrypt_data.domain.prep_extract import extract
from quancrypt_data.domain.prep_report import build_report, identifier_leaks

NOW = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)
KEY = "a" * 64


def event(
    event_type: str, payload: dict[str, object], *, key: str = KEY, event_id: str = "", at: datetime = NOW
) -> RawEvent:
    return RawEvent(
        event_id or f"00000000-0000-0000-0000-{len(payload):012d}", event_type, "corpus", 1, at, key, payload
    )


def finding(**fields: object) -> FindingRow:
    base: dict[str, object] = {
        "id": "f1", "source_event_id": "e1", "project_key": KEY, "unit_path": ".", "file_path": "src/main/java/A.java",
        "line_start": 3, "line_end": 3, "algorithm_family": "RSA", "usage_context": "SIGNATURE", "location_kind": "CODE",
        "priority": "P2", "key_size_bits": 2048, "confidence": 0.9,
    }  # fmt: skip
    base.update(fields)
    return FindingRow(**base)  # type: ignore[arg-type]


def batch(*findings: FindingRow, projects: tuple[ProjectRow, ...] = (ProjectRow(KEY, "CORPUS"),)) -> PrepBatch:
    return PrepBatch(projects=projects, units=(UnitRow(KEY, "."),), findings=findings)


class TestExtract:
    def test_an_analysis_event_gives_its_unit_runtime_findings_and_topology(self) -> None:
        raw = event(
            "corpus_analysis",
            {
                "analysis_unit": "svc-a", "chunk_index": 0, "chunk_count": 1,
                "runtime": {"java_version": "21", "spring_boot_version": "3.3.1"},
                "findings": [{"file": "src/main/java/A.java", "algorithm_family": "RSA"}, {"file": "B.java"}],
                "topology": {"node_count": 4, "edge_count": 2, "tls_edge_count": 1, "mtls_edge_count": 0},
            },
            event_id="11111111-1111-1111-1111-111111111111",
        )  # fmt: skip

        result = extract([raw], [])

        assert result.projects == (ProjectRow(KEY, "CORPUS"),)
        assert result.units == (UnitRow(KEY, "svc-a", "21", "3.3.1", NOW),)
        assert [f.full_path for f in result.findings] == ["svc-a/src/main/java/A.java", "svc-a/B.java"]
        assert result.findings[1].id == row_id(raw.event_id, "finding", 1)
        assert (result.topologies[0].node_count, result.topologies[0].tls_edge_count) == (4, 1)

    def test_core_events_give_coded_findings_and_the_latest_topology_and_runtime(self) -> None:
        old = event("topology_recorded", {"node_count": 1, "link_count": 0, "links": []}, event_id="1" * 8 + "-0" * 4,
                    at=NOW - timedelta(days=1))  # fmt: skip
        new = event(
            "topology_recorded",
            {"node_count": 2, "link_count": 2, "links": [
                {"protocol": "HTTP", "tls": True, "mtls": True}, {"protocol": "MQTT", "tls": False, "mtls": False}]},
            event_id="2" * 8 + "-0" * 4,
        )  # fmt: skip
        runtime = event(
            "project_runtime_changed",
            {"previous": None, "current": {"java_version": "17", "spring_boot_version": None}},
        )
        coded = event("finding_detected", {"algorithm_family": "RSA", "usage_context": "ENCRYPTION", "location_kind": "CODE",
                                           "priority": "P1", "key_size_bits": None, "confidence": 0.8, "classified_by": "STATIC"},
                      event_id="3" * 8 + "-0" * 4)  # fmt: skip
        scan = event("scan_completed", {}, event_id="4" * 8 + "-0" * 4)

        result = extract([old, new, runtime, coded, scan], [])

        assert result.projects == (ProjectRow(KEY, "USER"),)
        assert [(t.node_count, t.edge_count, t.tls_edge_count, t.mtls_edge_count) for t in result.topologies] == [
            (2, 2, 1, 1)
        ]
        assert [(link.ordinal, link.protocol) for link in result.links] == [(0, "HTTP"), (1, "MQTT")]
        assert result.units == (UnitRow(KEY, ".", "17", None, NOW),)
        assert result.findings[0].file_path is None and result.findings[0].priority == "P1"
        assert scan not in result.events, "an event type without a prep table is not read"

    def test_scope_decisions_and_benchmark_labels(self) -> None:
        scope = event("scope_decision", {"decision": "DENY", "confidence": None, "deciding_ring": "RULE_FILTER",
                                          "latency_ms": 4, "language": "tr"})  # fmt: skip

        result = extract([scope], [RawLabel("owasp-benchmark", "c1", "A.java", "crypto", 327, True)])

        assert result.scopes == (ScopeRow(scope.event_id, KEY, NOW, "DENY", None, "RULE_FILTER", 4, "tr"),)
        assert result.labels == (LabelRow("owasp-benchmark", "c1", "A.java", "crypto", 327, True),)


class TestWithoutEvents:
    def test_the_units_and_projects_only_the_removed_events_supported_go_with_them(self) -> None:
        other = "b" * 64
        events = (
            event("corpus_analysis", {"analysis_unit": "svc", "chunk_index": 0}, event_id="e1"),
            event("corpus_analysis", {"analysis_unit": "svc", "chunk_index": 1}, event_id="e2"),
            event("corpus_analysis", {"analysis_unit": "api", "chunk_index": 0}, event_id="e3"),
            event("corpus_analysis", {"analysis_unit": "svc", "chunk_index": 0}, key=other, event_id="e4"),
        )
        full = PrepBatch(
            events=events,
            projects=(ProjectRow(KEY, "CORPUS"), ProjectRow(other, "CORPUS")),
            units=(UnitRow(KEY, "svc", "21", "3.3"), UnitRow(KEY, "api", "17"), UnitRow(other, "svc")),
        )

        # e1 carried the runtime of the unit `svc`; e2 still supports the unit, so it stays without versions.
        result = full.without_events(["e1", "e3"])
        assert [(u.project_key, u.unit_path, u.java_version) for u in result.units] == [
            (KEY, "svc", None), (other, "svc", None)
        ]  # fmt: skip
        assert [p.project_key for p in full.without_events(["e4"]).projects] == [KEY]
        assert full.without_events(["e1", "e2", "e3"]).projects[0].project_key == other


class TestDeduplicator:
    def test_repeats_of_a_path_line_family_and_context_become_one(self) -> None:
        rows = (
            finding(id="1"),
            finding(id="2"),  # the same
            finding(id="3", unit_path="svc-b"),  # the same relative path in another unit is another file (D-307b)
            finding(id="4", line_start=4),
            finding(id="5", file_path=None),
            finding(id="6", file_path=None),  # coded findings are never repeats
        )

        result = Deduplicator().apply(batch(*rows))

        assert [f.id for f in result.batch.findings] == ["1", "3", "4", "5", "6"]
        assert result.notes == {"duplicates_removed": 1}


class TestGeneratedCodeExcluder:
    def test_findings_below_build_output_are_dropped(self) -> None:
        rows = (
            finding(id="1"),
            finding(id="2", file_path="target/generated-sources/A.java"),
            finding(id="3", file_path=None),
        )

        result = GeneratedCodeExcluder().apply(batch(*rows))

        assert [f.id for f in result.batch.findings] == ["1", "3"]
        assert result.rejected == () and result.notes == {"generated_removed": 1}


class TestTestCodeFlagger:
    @pytest.mark.parametrize(
        ("fields", "flag"),
        [
            ({}, False),
            ({"file_path": "src/test/java/A.java"}, True),
            ({"file_path": "src/main/java/CryptoIT.java"}, True),
            ({"location_kind": "TEST_CODE"}, True),
            ({"file_path": None}, False),
        ],
    )
    def test_test_code_is_flagged_and_kept(self, fields: dict[str, object], flag: bool) -> None:
        result = TestCodeFlagger().apply(batch(finding(**fields)))

        assert [f.in_test_code for f in result.batch.findings] == [flag]


class TestMissingValueHandler:
    def test_nothing_is_guessed_and_missing_categories_become_unknown(self) -> None:
        result = MissingValueHandler().apply(
            batch(finding(key_size_bits=None, algorithm_family=None, usage_context=None, mode=None))
        )

        (row,) = result.batch.findings
        assert (row.key_size_bits, row.algorithm_family, row.usage_context, row.mode) == (
            None,
            "UNKNOWN",
            "UNKNOWN",
            None,
        )
        assert result.notes == {"category_set_to_unknown": 1, "key_size_unknown": 1}


class TestOutlierFlagger:
    def test_a_project_above_q3_plus_three_iqr_of_its_origin_is_flagged_not_removed(self) -> None:
        keys = [f"{i:064x}" for i in range(6)]
        counts = [10, 12, 11, 13, 9, 500]
        rows = tuple(finding(id=f"{k}{n}", project_key=k) for k, c in zip(keys, counts, strict=True) for n in range(c))
        projects = tuple(ProjectRow(k, "CORPUS") for k in keys) + (ProjectRow("b" * 64, "BENCHMARK"),)

        result = OutlierFlagger().apply(PrepBatch(projects=projects, findings=rows))

        assert [p.project_key for p in result.batch.projects if p.is_outlier_project] == [keys[5]]
        assert len(result.batch.findings) == len(rows)


class TestTypeCaster:
    def test_values_that_fit_pass_and_times_become_utc(self) -> None:
        local = datetime(2026, 11, 23, 15, 0, tzinfo=timezone(timedelta(hours=3)))
        scope = ScopeRow("e1", KEY, local, "ALLOW", 0.9, "SCOPE_CLASSIFIER", 12, "en")

        result = TypeCaster().apply(replace(batch(finding()), scopes=(scope,)))

        assert result.rejected == ()
        assert result.batch.scopes[0].occurred_at == datetime(2026, 11, 23, 12, 0, tzinfo=UTC)

    @pytest.mark.parametrize(
        ("fields", "column"),
        [
            ({"priority": "P9"}, "finding.priority"),
            ({"confidence": 1.5}, "finding.confidence"),
            ({"line_start": 0}, "finding.line_start"),
            ({"line_start": 9, "line_end": 3}, "finding.line_end"),
            ({"key_size_bits": True}, "finding.key_size_bits"),
            ({"algorithm_family": "ROT13"}, "finding.algorithm_family"),
        ],
    )
    def test_a_row_that_does_not_fit_is_set_aside_with_its_column(self, fields: dict[str, object], column: str) -> None:
        result = TypeCaster().apply(batch(finding(**fields)))

        assert result.batch.findings == ()
        assert result.rejected == (Rejection("TypeCaster", "type-mismatch", column, KEY, "e1"),)

    def test_a_unit_whose_runtime_does_not_fit_keeps_its_rows_and_loses_the_runtime(self) -> None:
        result = TypeCaster().apply(replace(batch(finding()), units=(UnitRow(KEY, ".", "21 LTS", None),)))

        assert result.batch.units == (UnitRow(KEY, "."),)
        assert len(result.batch.findings) == 1 and result.notes == {"runtime_set_to_unknown": 1}

    def test_a_link_and_a_label_are_checked_too(self) -> None:
        bad = replace(
            batch(),
            links=(LinkRow(KEY, ".", "e2", 0, "SMTP", True, False),),
            labels=(LabelRow("owasp-benchmark", "c1", None, None, 0, True),),
        )

        result = TypeCaster().apply(bad)

        assert (result.batch.links, result.batch.labels) == ((), ())
        assert [r.message for r in result.rejected] == ["service_link.protocol", "benchmark_label.cwe"]


class _RejectFirst:
    code = "Rejector"

    def apply(self, b: PrepBatch) -> FilterResult:
        first = b.findings[0]
        kept = replace(b, findings=b.findings[1:])
        return FilterResult(
            kept, (Rejection(self.code, "type-mismatch", "x", first.project_key, first.source_event_id),)
        )


class TestPipeline:
    def test_the_funnel_counts_each_filter_and_chains(self) -> None:
        rows = (
            finding(id="1"),
            finding(id="2"),
            finding(id="3", file_path="out/A.java"),
            finding(id="4", line_start=9),
        )

        final, rejected, counts = run_filters(batch(*rows), [Deduplicator(), GeneratedCodeExcluder(), _RejectFirst()])

        assert [(c.filter_code, c.rows_in, c.rows_out, c.rows_rejected, c.rows_dropped) for c in counts] == [
            ("Deduplicator", 4, 3, 0, 1),
            ("GeneratedCodeExcluder", 3, 2, 0, 1),
            ("Rejector", 2, 1, 1, 0),
        ]
        assert [f.id for f in final.findings] == ["4"] and len(rejected) == 1

    def test_the_default_order_is_the_order_of_the_skill(self) -> None:
        assert FILTER_ORDER[0] == "SchemaValidator" and FILTER_ORDER[-1] == "TypeCaster" and len(FILTER_ORDER) == 9


class TestReport:
    def test_the_report_counts_the_funnel_targets_and_leaks(self) -> None:
        raw = event("corpus_analysis", {"analysis_unit": ".", "chunk_index": 0, "findings": [
            {"file": "A.java", "raw_name": "RSA", "algorithm_family": "RSA"},
            {"file": "B.java", "raw_name": "rsa", "algorithm_family": "RSA"}]})  # fmt: skip
        extracted = extract([raw], [])
        final, rejected, counts = run_filters(extracted, [Deduplicator()])

        report = build_report(
            extracted=extracted, final=final, counts=counts, rejected=rejected, leaks={}, generated_at=NOW
        )

        assert report.distinct["raw_name"] == (2, None) and report.distinct["algorithm_family"] == (1, 1)
        assert (report.rows_in, report.findings, report.corpus_projects) == (2, 2, 1)
        assert report.funnel_consistent and report.leak_free and not report.findings_target_met
        assert not report.quarantine_warning

    def test_a_raw_identifier_in_prep_text_is_a_leak(self) -> None:
        assert identifier_leaks(["ab12cd34ef56/src/main/java/9f8e7d6c5b4a.java", "SHA-256"]) == {}
        assert identifier_leaks(["https://github.com/acme/x", "/home/olcay/x/A.java"]) == {"url": 1, "absolute_path": 1}

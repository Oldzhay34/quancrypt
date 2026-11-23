"""The profiling report as data (P6.3): everything the Markdown, the figures and `unmapped_values.csv` are drawn
from."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from quancrypt_data.domain.profiling import (
    ColumnProfile,
    Duplicates,
    OutlierReport,
    ProfileFacts,
    RawSnapshot,
    Recommendation,
    SourceSummary,
    TableChecksum,
    UnmappedValue,
    column_profile,
    duplicates,
    finding_columns,
    findings_per_project,
    outliers,
    path_class,
    recommendations,
    spelling_variety,
    unmapped_values,
)

SPELLING_FIELDS = ("raw_name", "mode", "padding", "hash", "library")


@dataclass(frozen=True)
class ProfileReport:
    generated_at: datetime
    sources: tuple[SourceSummary, ...]
    columns: tuple[ColumnProfile, ...]
    spellings: Mapping[str, list[tuple[str, int]]]
    duplicates: Duplicates
    per_project: Mapping[str, int]
    outliers: OutlierReport
    path_classes: Mapping[str, int]
    quarantine_reasons: Mapping[str, int]
    quarantine_messages: list[tuple[str, int]]
    secret_hits: Mapping[str, int]
    scanned_texts: int
    projects_in_raw: int
    unmapped: list[UnmappedValue]
    recommendations: list[Recommendation]
    before: tuple[TableChecksum, ...]
    after: tuple[TableChecksum, ...]

    @property
    def unchanged(self) -> bool:
        return self.before == self.after


def build_report(
    snapshot: RawSnapshot,
    *,
    known_raw_names: set[str],
    known_values: Mapping[str, set[str]],
    secret_hits: Mapping[str, int],
    before: Sequence[TableChecksum],
    after: Sequence[TableChecksum],
    generated_at: datetime,
) -> ProfileReport:
    findings = snapshot.findings
    per_project = findings_per_project(findings)
    classes = Counter(path_class(f.file) for f in findings if f.file is not None)
    unmapped = unmapped_values(findings, known_raw_names, known_values)
    dupes = duplicates(findings)
    outlier_report = outliers(per_project)
    quarantine_reasons = Counter(q.error_code for q in snapshot.quarantine)
    columns = [
        *finding_columns(findings),
        *_columns("topologies", snapshot.topologies, ("node_count", "edge_count", "tls_edge_count", "mtls_edge_count")),
        *_columns("runtimes", snapshot.runtimes, ("java_version", "spring_boot_version")),
        *_columns(
            "scope_decisions", snapshot.scopes, ("decision", "deciding_ring", "confidence", "latency_ms", "language")
        ),
        *_columns(
            "benchmark_labels",
            snapshot.labels,
            ("benchmark", "case_id", "file_path", "category", "cwe", "expected_vulnerable"),
        ),
    ]
    facts = ProfileFacts(
        quarantined=dict(quarantine_reasons),
        duplicates=dupes,
        path_classes=dict(classes),
        test_code_findings=sum(1 for f in findings if f.location_kind == "TEST_CODE"),
        unmapped=len(unmapped),
        secret_hits=dict(secret_hits),
        findings_with_path=sum(1 for f in findings if f.file is not None),
        unknown_key_size=sum(1 for f in findings if f.key_size_bits is None),
        unknown_algorithm=sum(1 for f in findings if f.algorithm_family == "UNKNOWN"),
        outliers=len(outlier_report.outliers),
        findings=len(findings),
    )
    return ProfileReport(
        generated_at=generated_at,
        sources=snapshot.sources,
        columns=tuple(columns),
        spellings={name: spelling_variety(findings, name) for name in SPELLING_FIELDS},
        duplicates=dupes,
        per_project=per_project,
        outliers=outlier_report,
        path_classes=dict(classes),
        quarantine_reasons=dict(quarantine_reasons),
        quarantine_messages=sorted(
            Counter(q.error_message for q in snapshot.quarantine).items(), key=lambda item: (-item[1], item[0])
        ),
        secret_hits=dict(secret_hits),
        scanned_texts=len(snapshot.texts),
        projects_in_raw=len(snapshot.project_keys),
        unmapped=unmapped,
        recommendations=recommendations(facts),
        before=tuple(before),
        after=tuple(after),
    )


def _columns(table: str, records: Sequence[object], names: Sequence[str]) -> list[ColumnProfile]:
    return [column_profile(table, name, [getattr(r, name) for r in records]) for name in names]

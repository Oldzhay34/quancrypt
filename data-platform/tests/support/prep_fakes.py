"""Fakes of the preprocessing ports (P6.4) and the cases every adapter of a port passes, the fake and the PostgreSQL
one alike (solid-checklist L); the PostgreSQL adapters run them in tests/integration/test_prep_postgres.py."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from quancrypt_data.domain.prep import (
    FindingRow,
    LabelRow,
    ProjectRow,
    RawEvent,
    RawLabel,
    Rejection,
    UnitRow,
)
from quancrypt_data.domain.prep_report import PreprocessReport
from quancrypt_data.port.outbound.prep import (
    PrepReader,
    PrepRepository,
    ProjectContent,
    RawEventSource,
    TableStat,
)

KEY = "c" * 64


@dataclass
class InMemoryRawEventSource:
    stored_events: list[RawEvent] = field(default_factory=list)
    stored_labels: list[RawLabel] = field(default_factory=list)

    def events(self) -> Sequence[RawEvent]:
        return sorted(self.stored_events, key=lambda e: e.event_id)

    def labels(self) -> Sequence[RawLabel]:
        return sorted(self.stored_labels, key=lambda label: (label.benchmark, label.case_id))


@dataclass
class InMemoryPrepStore:
    """`PrepRepository` and `PrepReader` over dictionaries."""

    projects: dict[str, ProjectContent] = field(default_factory=dict)
    rejections: dict[str | None, list[Rejection]] = field(default_factory=dict)
    labels: list[LabelRow] = field(default_factory=list)

    def stored_project_keys(self) -> set[str]:
        return set(self.projects) | {k for k in self.rejections if k is not None}

    def replace_project(self, project_key: str, content: ProjectContent | None, rejected: Sequence[Rejection]) -> None:
        self.projects.pop(project_key, None)
        self.rejections.pop(project_key, None)
        if content is not None:
            self.projects[project_key] = content
        if rejected:
            self.rejections[project_key] = list(rejected)

    def replace_labels(self, labels: Sequence[LabelRow], rejected: Sequence[Rejection]) -> None:
        self.labels = list(labels)
        self.rejections[None] = list(rejected)

    def path_values(self) -> Sequence[str]:
        values: list[str] = []
        for content in self.projects.values():
            values += [u.unit_path for u in content.units]
            values += [f.file_path for f in content.findings if isinstance(f.file_path, str)]
        return values

    def text_values(self) -> Sequence[str]:
        values: list[str] = []
        for content in self.projects.values():
            for unit in content.units:
                values += [
                    v for v in (unit.unit_path, unit.java_version, unit.spring_boot_version) if isinstance(v, str)
                ]
            for f in content.findings:
                values += [
                    v for v in (f.unit_path, f.file_path, f.mode, f.padding, f.hash, f.library) if isinstance(v, str)
                ]
        for label in self.labels:
            values += [v for v in (label.case_id, label.file_path, label.category) if isinstance(v, str)]
        return values

    def table_stats(self) -> Sequence[TableStat]:
        findings = [f for c in self.projects.values() for f in c.findings]
        return [
            TableStat("prep.project_snapshot", len(self.projects), {}),
            TableStat("prep.finding", len(findings), {}),
        ]


@dataclass
class RecordingPrepReportWriter:
    reports: list[PreprocessReport] = field(default_factory=list)

    def write(self, report: PreprocessReport, stats: Sequence[TableStat]) -> Sequence[str]:
        self.reports.append(report)
        return ["reports/preprocessing_report.md"]


def content(
    key: str = KEY, *, findings: int = 2, source_event_id: str = "11111111-1111-1111-1111-111111111111"
) -> ProjectContent:
    unit = "ab12cd34ef56"
    rows = tuple(
        FindingRow(
            id=f"00000000-0000-0000-0000-{n:012d}", source_event_id=source_event_id,
            project_key=key, unit_path=unit, file_path=f"src/main/java/{n:012x}.java", line_start=n + 1,
            line_end=n + 1, algorithm_family="RSA", usage_context="SIGNATURE", location_kind="CODE", priority="P2",
            key_size_bits=2048, confidence=0.9, mode=None, padding="PKCS1_V1_5", hash="SHA-256", library="JCA",
        )
        for n in range(findings)
    )  # fmt: skip
    return ProjectContent(ProjectRow(key, "CORPUS"), (UnitRow(key, unit, "21", None),), rows, (), (), ())


def check_source_on_an_empty_raw(source: RawEventSource) -> None:
    assert list(source.events()) == [] and list(source.labels()) == []


def check_repository_replaces_a_project(
    repository: PrepRepository, reader: PrepReader, event_id: str = "11111111-1111-1111-1111-111111111111"
) -> None:
    repository.replace_project(
        KEY,
        content(findings=3, source_event_id=event_id),
        [Rejection("TypeCaster", "type-mismatch", "f", KEY, event_id)],
    )
    repository.replace_project(KEY, content(findings=2, source_event_id=event_id), [])
    assert repository.stored_project_keys() == {KEY}
    finding_rows = next(s for s in reader.table_stats() if s.table == "prep.finding").rows
    assert finding_rows == 2, "a second write replaces the first, nothing is added to it"
    assert "src/main/java/000000000001.java" in reader.text_values()
    repository.replace_project(KEY, None, [])
    assert repository.stored_project_keys() == set()
    assert next(s for s in reader.table_stats() if s.table == "prep.finding").rows == 0

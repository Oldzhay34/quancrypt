"""Outbound ports of the preprocessing use case (P6.4): reading raw, writing prep, reading prep back for the leak check
and the report."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from quancrypt_data.domain.prep import (
    FindingRow,
    LabelRow,
    LinkRow,
    ProjectRow,
    RawEvent,
    RawLabel,
    Rejection,
    ScopeRow,
    TopologyRow,
    UnitRow,
)
from quancrypt_data.domain.prep_report import PreprocessReport


@dataclass(frozen=True)
class ProjectContent:
    """Every prep row of one project: what one transaction writes."""

    project: ProjectRow
    units: tuple[UnitRow, ...]
    findings: tuple[FindingRow, ...]
    topologies: tuple[TopologyRow, ...]
    links: tuple[LinkRow, ...]
    scopes: tuple[ScopeRow, ...]


@dataclass(frozen=True)
class TableStat:
    table: str
    rows: int
    null_ratios: Mapping[str, float]


class RawEventSource(Protocol):
    """Reads raw and never writes it (the adapter reads in READ ONLY transactions)."""

    def events(self) -> Sequence[RawEvent]: ...

    def labels(self) -> Sequence[RawLabel]: ...


class PrepRepository(Protocol):
    def stored_project_keys(self) -> set[str]: ...

    def replace_project(self, project_key: str, content: ProjectContent | None, rejected: Sequence[Rejection]) -> None:
        """In one transaction: delete every prep and prep-quarantine row of the key, then write `content` (None writes
        no prep row: every record of the project was set aside) and the rejections."""
        ...

    def replace_labels(self, labels: Sequence[LabelRow], rejected: Sequence[Rejection]) -> None:
        """In one transaction: the benchmark labels and their rejections, replaced."""
        ...


class PrepReader(Protocol):
    def text_values(self) -> Sequence[str]:
        """Every text value of the prep tables (the leak check reads what was really written)."""
        ...

    def path_values(self) -> Sequence[str]:
        """The text values that are paths (a subset of `text_values`): slash separated, scanned per segment."""
        ...

    def table_stats(self) -> Sequence[TableStat]: ...


class PrepReportWriter(Protocol):
    def write(self, report: PreprocessReport, stats: Sequence[TableStat]) -> Sequence[str]: ...

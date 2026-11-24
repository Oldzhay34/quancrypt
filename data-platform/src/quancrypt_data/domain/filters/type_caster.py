from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from typing import TypeVar

from quancrypt_data.domain.prep import (
    ALGORITHM_FAMILIES,
    LANGUAGES,
    LOCATION_KINDS,
    PRIORITIES,
    PROTOCOLS,
    SCOPE_DECISIONS,
    SCOPE_RINGS,
    USAGE_CONTEXTS,
    FilterResult,
    FindingRow,
    LabelRow,
    LinkRow,
    PrepBatch,
    Rejection,
    ScopeRow,
    TopologyRow,
    UnitRow,
)

_VERSION = re.compile(r"[0-9A-Za-z._+-]{1,32}")
_SHORT_TEXT = 64
_PATH_TEXT = 1024
_R = TypeVar("_R")


class CastError(ValueError):
    """A value that does not fit its prep column; the message names the column only, never the value."""


def _int(value: object, column: str, *, minimum: int, nullable: bool = False) -> int | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise CastError(column)
    return value


def _instant(value: object, column: str) -> datetime | None:
    """A time zone aware time in UTC; None stays None (a row built without a time, tests): the database refuses it."""
    if value is None:
        return None
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise CastError(column)
    return value.astimezone(UTC)


def _bool(value: object, column: str) -> bool:
    if not isinstance(value, bool):
        raise CastError(column)
    return value


def _code(value: object, column: str, codes: frozenset[str]) -> str:
    if not isinstance(value, str) or value not in codes:
        raise CastError(column)
    return value


def _text(value: object, column: str, limit: int, *, nullable: bool = True) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not value or len(value) > limit:
        raise CastError(column)
    return value


def _fraction(value: object, column: str, *, nullable: bool = False) -> float | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
        raise CastError(column)
    return float(value)


def _version(value: object, column: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or _VERSION.fullmatch(value) is None:
        raise CastError(column)
    return value


class TypeCaster:
    """The last filter (filter 9): every value is checked against the type, code list and range of its prep column and
    every time is turned to UTC. A row that does not fit is set aside (`type-mismatch`) with the column's name."""

    code = "TypeCaster"

    def apply(self, batch: PrepBatch) -> FilterResult:
        rejected: list[Rejection] = []
        findings = self._each(batch.findings, self._finding, rejected, lambda r: (r.project_key, r.source_event_id))
        topologies = self._each(
            batch.topologies, self._topology, rejected, lambda r: (r.project_key, r.source_event_id)
        )
        links = self._each(batch.links, self._link, rejected, lambda r: (r.project_key, r.source_event_id))
        scopes = self._each(batch.scopes, self._scope, rejected, lambda r: (r.project_key, r.event_id))
        labels: list[LabelRow] = []
        for label in batch.labels:
            try:
                labels.append(self._label(label))
            except CastError as exc:
                rejected.append(
                    Rejection(
                        self.code, "type-mismatch", f"benchmark_label.{exc}", label=(label.benchmark, label.case_id)
                    )
                )
        # A unit whose runtime does not fit keeps its rows: only the runtime becomes unknown.
        units: list[UnitRow] = []
        runtime_dropped = 0
        for unit in batch.units:
            try:
                units.append(self._unit(unit))
            except CastError:
                units.append(replace(unit, java_version=None, spring_boot_version=None))
                runtime_dropped += 1
        return FilterResult(
            replace(
                batch,
                findings=tuple(findings),
                topologies=tuple(topologies),
                links=tuple(links),
                scopes=tuple(scopes),
                units=tuple(units),
                labels=tuple(labels),
            ),
            tuple(rejected),
            notes={"runtime_set_to_unknown": runtime_dropped},
        )

    def _each(
        self,
        rows: tuple[_R, ...],
        cast: Callable[[_R], _R],
        rejected: list[Rejection],
        origin: Callable[[_R], tuple[str, str | None]],
    ) -> list[_R]:
        kept: list[_R] = []
        for row in rows:
            try:
                kept.append(cast(row))
            except CastError as exc:
                project_key, event_id = origin(row)
                rejected.append(Rejection(self.code, "type-mismatch", str(exc), project_key, event_id))
        return kept

    @staticmethod
    def _finding(f: FindingRow) -> FindingRow:
        start = _int(f.line_start, "finding.line_start", minimum=1, nullable=True)
        end = _int(f.line_end, "finding.line_end", minimum=1, nullable=True)
        if start is not None and end is not None and end < start:
            raise CastError("finding.line_end")
        return replace(
            f,
            file_path=_text(f.file_path, "finding.file_path", _PATH_TEXT),
            line_start=start,
            line_end=end,
            algorithm_family=_code(f.algorithm_family, "finding.algorithm_family", ALGORITHM_FAMILIES),
            usage_context=_code(f.usage_context, "finding.usage_context", USAGE_CONTEXTS),
            location_kind=_code(f.location_kind, "finding.location_kind", LOCATION_KINDS),
            priority=_code(f.priority, "finding.priority", PRIORITIES),
            key_size_bits=_int(f.key_size_bits, "finding.key_size_bits", minimum=1, nullable=True),
            confidence=_fraction(f.confidence, "finding.confidence"),
            mode=_text(f.mode, "finding.mode", _SHORT_TEXT),
            padding=_text(f.padding, "finding.padding", _SHORT_TEXT),
            hash=_text(f.hash, "finding.hash", _SHORT_TEXT),
            library=_text(f.library, "finding.library", _SHORT_TEXT),
        )

    @staticmethod
    def _topology(t: TopologyRow) -> TopologyRow:
        return replace(
            t,
            node_count=_int(t.node_count, "topology_summary.node_count", minimum=0),
            edge_count=_int(t.edge_count, "topology_summary.edge_count", minimum=0),
            tls_edge_count=_int(t.tls_edge_count, "topology_summary.tls_edge_count", minimum=0, nullable=True),
            mtls_edge_count=_int(t.mtls_edge_count, "topology_summary.mtls_edge_count", minimum=0, nullable=True),
            recorded_at=_instant(t.recorded_at, "topology_summary.recorded_at"),
        )

    @staticmethod
    def _link(link: LinkRow) -> LinkRow:
        return replace(
            link,
            protocol=_code(link.protocol, "service_link.protocol", PROTOCOLS),
            tls=_bool(link.tls, "service_link.tls"),
            mtls=_bool(link.mtls, "service_link.mtls"),
        )

    @staticmethod
    def _scope(s: ScopeRow) -> ScopeRow:
        if s.occurred_at.tzinfo is None:
            raise CastError("scope_decision.occurred_at")
        return replace(
            s,
            occurred_at=s.occurred_at.astimezone(UTC),
            decision=_code(s.decision, "scope_decision.decision", SCOPE_DECISIONS),
            confidence=_fraction(s.confidence, "scope_decision.confidence", nullable=True),
            deciding_ring=_code(s.deciding_ring, "scope_decision.deciding_ring", SCOPE_RINGS),
            latency_ms=_int(s.latency_ms, "scope_decision.latency_ms", minimum=0),
            language=_code(s.language, "scope_decision.language", LANGUAGES),
        )

    @staticmethod
    def _unit(u: UnitRow) -> UnitRow:
        return replace(
            u,
            java_version=_version(u.java_version, "analysis_unit.java_version"),
            spring_boot_version=_version(u.spring_boot_version, "analysis_unit.spring_boot_version"),
            analysed_at=_instant(u.analysed_at, "analysis_unit.analysed_at"),
        )

    @staticmethod
    def _label(label: LabelRow) -> LabelRow:
        return replace(
            label,
            file_path=_text(label.file_path, "file_path", _PATH_TEXT),
            category=_text(label.category, "category", 128),
            cwe=_int(label.cwe, "cwe", minimum=1, nullable=True),
            expected_vulnerable=_bool(label.expected_vulnerable, "expected_vulnerable"),
        )

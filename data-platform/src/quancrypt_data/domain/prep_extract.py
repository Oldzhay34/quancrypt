"""From raw events to the candidate rows of the prep tables (P6.4): the payloads read as they are, nothing checked yet
(SchemaValidator and TypeCaster do that). Pure: no I/O.

Which event feeds which table:
- `corpus_analysis` and `benchmark_analysis`: a unit (runtime on the first chunk), its findings, and the topology counts
  (first chunk, root only);
- `finding_detected` (core-service): one coded finding of the root unit, no path;
- `topology_recorded`: the latest event of a project gives the root unit's counts and links;
- `project_runtime_changed`: the latest event gives the root unit's runtime;
- `scope_decision`: one row each.
Other event types (scans, plans) have no prep table and are not read."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import replace
from datetime import datetime

from quancrypt_data.domain.prep import (
    ROOT_UNIT,
    FindingRow,
    LabelRow,
    LinkRow,
    PrepBatch,
    ProjectRow,
    RawEvent,
    RawLabel,
    ScopeRow,
    TopologyRow,
    UnitRow,
    event_unit,
    row_id,
)

ORIGIN_BY_EVENT = {
    "corpus_analysis": "CORPUS",
    "benchmark_analysis": "BENCHMARK",
    "finding_detected": "USER",
    "topology_recorded": "USER",
    "project_runtime_changed": "USER",
    "scope_decision": "USER",
}
_ANALYSIS = ("corpus_analysis", "benchmark_analysis")


def _map(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _list(value: object) -> Sequence[object]:
    return value if isinstance(value, list) else []


def _latest(events: Iterable[RawEvent], event_type: str) -> dict[str, RawEvent]:
    latest: dict[str, RawEvent] = {}
    for event in sorted((e for e in events if e.event_type == event_type), key=lambda e: (e.occurred_at, e.event_id)):
        latest[event.project_key] = event
    return latest


# The event types that create or feed an analysis unit (the others are about the project or a scope decision).
_UNIT_EVENTS = (*_ANALYSIS, "finding_detected", "topology_recorded", "project_runtime_changed")


def _analysis_times(events: Sequence[RawEvent]) -> dict[tuple[str, str], datetime]:
    """When each unit was analysed: the largest occurred_at over every event that feeds it (D-318b)."""
    times: dict[tuple[str, str], datetime] = {}
    for event in events:
        if event.event_type in _UNIT_EVENTS:
            key = (event.project_key, event_unit(event))
            times[key] = max(times[key], event.occurred_at) if key in times else event.occurred_at
    return times


def extract(events: Sequence[RawEvent], labels: Sequence[RawLabel]) -> PrepBatch:
    relevant = tuple(sorted((e for e in events if e.event_type in ORIGIN_BY_EVENT), key=lambda e: e.event_id))
    projects: dict[str, ProjectRow] = {}
    units: dict[tuple[str, str], UnitRow] = {}
    findings: list[FindingRow] = []
    topologies: list[TopologyRow] = []
    links: list[LinkRow] = []
    scopes: list[ScopeRow] = []

    def unit(project_key: str, path: str) -> None:
        units.setdefault((project_key, path), UnitRow(project_key, path))

    for event in relevant:
        projects.setdefault(event.project_key, ProjectRow(event.project_key, ORIGIN_BY_EVENT[event.event_type]))
        payload = event.payload
        if event.event_type in _ANALYSIS:
            path = payload.get("analysis_unit")
            unit_path = path if isinstance(path, str) else ROOT_UNIT
            unit(event.project_key, unit_path)
            if payload.get("chunk_index") == 0:
                runtime = _map(payload.get("runtime"))
                units[(event.project_key, unit_path)] = UnitRow(
                    event.project_key, unit_path, runtime.get("java_version"), runtime.get("spring_boot_version")
                )
                topology = payload.get("topology")
                if isinstance(topology, Mapping):
                    topologies.append(
                        TopologyRow(
                            event.project_key, unit_path, event.event_id, topology.get("node_count"),
                            topology.get("edge_count"), topology.get("tls_edge_count"), topology.get("mtls_edge_count"),
                            event.occurred_at,
                        )
                    )  # fmt: skip
            for ordinal, item in enumerate(_list(payload.get("findings"))):
                findings.append(_analysis_finding(event, unit_path, ordinal, _map(item)))
        elif event.event_type == "finding_detected":
            unit(event.project_key, ROOT_UNIT)
            findings.append(_coded_finding(event))
        elif event.event_type == "scope_decision":
            scopes.append(
                ScopeRow(
                    event.event_id, event.project_key, event.occurred_at, payload.get("decision"),
                    payload.get("confidence"), payload.get("deciding_ring"), payload.get("latency_ms"),
                    payload.get("language"),
                )
            )  # fmt: skip

    for event in _latest(relevant, "topology_recorded").values():
        unit(event.project_key, ROOT_UNIT)
        edges = [_map(item) for item in _list(event.payload.get("links"))]
        topologies.append(
            TopologyRow(
                event.project_key, ROOT_UNIT, event.event_id, event.payload.get("node_count"),
                event.payload.get("link_count"), sum(1 for e in edges if e.get("tls") is True),
                sum(1 for e in edges if e.get("mtls") is True), event.occurred_at,
            )
        )  # fmt: skip
        links.extend(
            LinkRow(
                event.project_key, ROOT_UNIT, event.event_id, ordinal, e.get("protocol"), e.get("tls"), e.get("mtls")
            )
            for ordinal, e in enumerate(edges)
        )
    for event in _latest(relevant, "project_runtime_changed").values():
        current = _map(event.payload.get("current"))
        units[(event.project_key, ROOT_UNIT)] = UnitRow(
            event.project_key, ROOT_UNIT, current.get("java_version"), current.get("spring_boot_version")
        )

    analysed = _analysis_times(relevant)
    return PrepBatch(
        events=relevant,
        projects=tuple(sorted(projects.values(), key=lambda p: p.project_key)),
        units=tuple(
            replace(u, analysed_at=analysed.get((u.project_key, u.unit_path)))
            for u in sorted(units.values(), key=lambda u: (u.project_key, u.unit_path))
        ),
        findings=tuple(findings),
        topologies=tuple(topologies),
        links=tuple(links),
        scopes=tuple(scopes),
        labels=tuple(
            LabelRow(
                label.benchmark, label.case_id, label.file_path, label.category, label.cwe, label.expected_vulnerable
            )
            for label in sorted(labels, key=lambda label: (label.benchmark, label.case_id))
        ),
    )


def _analysis_finding(event: RawEvent, unit_path: str, ordinal: int, item: Mapping[str, object]) -> FindingRow:
    return FindingRow(
        id=row_id(event.event_id, "finding", ordinal),
        source_event_id=event.event_id,
        project_key=event.project_key,
        unit_path=unit_path,
        file_path=item.get("file"),
        line_start=item.get("line_start"),
        line_end=item.get("line_end"),
        algorithm_family=item.get("algorithm_family"),
        usage_context=item.get("usage_context"),
        location_kind=item.get("location_kind"),
        priority=item.get("priority"),
        key_size_bits=item.get("key_size_bits"),
        confidence=item.get("confidence"),
        mode=item.get("mode"),
        padding=item.get("padding"),
        hash=item.get("hash"),
        library=item.get("library"),
    )


def _coded_finding(event: RawEvent) -> FindingRow:
    payload = event.payload
    return FindingRow(
        id=row_id(event.event_id, "finding", 0),
        source_event_id=event.event_id,
        project_key=event.project_key,
        unit_path=ROOT_UNIT,
        file_path=None,
        line_start=None,
        line_end=None,
        algorithm_family=payload.get("algorithm_family"),
        usage_context=payload.get("usage_context"),
        location_kind=payload.get("location_kind"),
        priority=payload.get("priority"),
        key_size_bits=payload.get("key_size_bits"),
        confidence=payload.get("confidence"),
    )

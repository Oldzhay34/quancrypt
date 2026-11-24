"""Test doubles of the outbound ports (hexagonal-service section 7): in-memory, no network, no database."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

from quancrypt_ml.domain.labels import BatchRow, Candidate, LabelRecord, Resolution, SourceLocation
from quancrypt_ml.port.outbound.labeling import (
    AnalyzerUnavailableError,
    BatchExistsError,
    NewBatch,
    ResolutionConflictError,
    SnippetUnavailableError,
    StoredBatch,
)


def candidate(n: int, family: str = "RSA", context: str = "ENCRYPTION", origin: str = "CORPUS", test: bool = False,
              priority: str = "P1") -> Candidate:  # fmt: skip
    return Candidate(
        finding_id=f"00000000-0000-4000-8000-{n:012d}", project_key=f"{n % 7:064x}", origin=origin,
        algorithm_family=family, usage_context=context, location_kind="TEST_CODE" if test else "CODE",
        priority=priority, in_test_code=test, key_size_bits=2048, mode=None, padding="OAEP", hash="SHA-256", library="JCA", confidence=0.9,
        quantum_status="VULNERABLE", hndl_exposure=True,
    )  # fmt: skip


class FakeCandidates:
    def __init__(self, rows: Sequence[Candidate]) -> None:
        self.rows = list(rows)
        self.gone: set[str] = set()

    def candidates(self) -> list[Candidate]:
        return sorted(self.rows, key=lambda c: c.finding_id)

    def known(self, finding_ids: Sequence[str]) -> set[str]:
        return {c.finding_id for c in self.rows if c.finding_id in finding_ids} - self.gone


class FakeLocator:
    def __init__(self, locations: Mapping[str, SourceLocation]) -> None:
        self.locations = dict(locations)

    def locate(self, finding_ids: Sequence[str]) -> dict[str, SourceLocation]:
        return {f: self.locations[f] for f in finding_ids if f in self.locations}


class FakeSnippets:
    def __init__(self, missing: set[str] | None = None, down: bool = False) -> None:
        self.missing = missing or set()
        self.down = down
        self.calls: list[SourceLocation] = []

    def context(self, location: SourceLocation, radius: int) -> tuple[tuple[int, str], ...]:
        self.calls.append(location)
        if self.down:
            raise AnalyzerUnavailableError("down")
        if location.path in self.missing:
            raise SnippetUnavailableError("gone")
        line = location.line or 1
        return tuple((n, f"line {n} of {location.path}") for n in range(max(1, line - radius), line + radius + 1))


class FakeLabelStore:
    def __init__(self) -> None:
        self.batches: dict[str, NewBatch] = {}
        self.gold: dict[tuple[str, str], dict[str, LabelRecord]] = {}
        self.resolved: dict[str, dict[str, Resolution]] = {}

    def create_batch(self, batch: NewBatch) -> None:
        if batch.name in self.batches:
            raise BatchExistsError(batch.name)
        self.batches[batch.name] = batch

    def batch(self, name: str) -> StoredBatch | None:
        b = self.batches.get(name)
        if b is None:
            return None
        items = {f: d for f, _, d in b.items}
        return StoredBatch(b.id, b.name, len(items), sum(items.values()), items)

    def _items(self, batch_id: str) -> set[str]:
        return next({f for f, _, _ in b.items} for b in self.batches.values() if b.id == batch_id)

    def replace_labels(self, batch_id: str, labeler_role: str, records: Sequence[LabelRecord], at: datetime) -> None:
        if not {r.finding_id for r in records} <= self._items(batch_id):
            raise ValueError("a label of a finding that is not in the batch")
        before = self.labels(batch_id, labeler_role)
        self.gold[(batch_id, labeler_role)] = {r.finding_id: r for r in records}
        after = self.labels(batch_id, labeler_role)
        changed = {f for f in set(before) | set(after) if before.get(f) != after.get(f)}
        open_ = self._disagreements(batch_id)
        self.resolved[batch_id] = {
            f: r for f, r in self.resolved.get(batch_id, {}).items() if f not in changed and f in open_
        }

    def _disagreements(self, batch_id: str) -> set[str]:
        first, second = self.labels(batch_id, "FIRST"), self.labels(batch_id, "SECOND")
        return {f for f in set(first) & set(second) if first[f] != second[f]}

    def labels(self, batch_id: str, labeler_role: str) -> dict[str, str]:
        return {f: r.label for f, r in self.gold.get((batch_id, labeler_role), {}).items()}

    def replace_resolutions(self, batch_id: str, resolutions: Sequence[Resolution], at: datetime) -> None:
        if not {r.finding_id for r in resolutions} <= self._disagreements(batch_id):
            raise ResolutionConflictError("a record to resolve is no longer a disagreement")
        self.resolved.setdefault(batch_id, {}).update({r.finding_id: r for r in resolutions})

    def resolutions(self, batch_id: str) -> dict[str, str]:
        return {f: r.label for f, r in self.resolved.get(batch_id, {}).items()}


class FakeFiles:
    def __init__(self) -> None:
        self.batches: dict[Path, list[BatchRow]] = {}
        self.inputs: dict[Path, list[dict[str, str]]] = {}
        self.written: dict[Path, list[dict[str, str]]] = {}

    def write_batch(self, path: Path, rows: Sequence[BatchRow]) -> None:
        self.batches[path] = list(rows)
        self.inputs[path] = [
            {"finding_id": r.sampled.candidate.finding_id, "double_label": "true" if r.sampled.double_label else "false",
             "label": "", "labeler": "", "notes": ""}
            for r in rows
        ]  # fmt: skip

    def read_rows(self, path: Path) -> list[dict[str, str]]:
        return [dict(r) for r in self.inputs[path]]

    def write_rows(self, path: Path, rows: Sequence[Mapping[str, str]]) -> None:
        self.written[path] = [dict(r) for r in rows]
        self.inputs[path] = [dict(r) for r in rows]


class FakeReports:
    def __init__(self) -> None:
        self.texts: dict[Path, str] = {}

    def write(self, path: Path, text: str) -> None:
        self.texts[path] = text

    def read(self, path: Path) -> str:
        return self.texts[path]


class FixedClock:
    def __init__(self) -> None:
        self.at = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)

    def now(self) -> datetime:
        self.at += timedelta(seconds=1)
        return self.at


class SequentialIds:
    def __init__(self) -> None:
        self.n = 0

    def new_id(self) -> str:
        self.n += 1
        return f"10000000-0000-4000-8000-{self.n:012d}"

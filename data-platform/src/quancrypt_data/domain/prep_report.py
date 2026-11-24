"""The preprocessing report as data (P6.4, data-preprocessing section 4): the funnel, the values before and after
canonicalisation, the quarantine, the leak check (H6) and the targets. Pure: no I/O."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from quancrypt_data.domain.corpus import CORPUS_MINIMUM, CORPUS_TARGET
from quancrypt_data.domain.prep import FilterCount, PrepBatch, RawEvent, Rejection

# H5: the corpus should give at least this many findings.
FINDINGS_TARGET = 2000
# D-310d: above this share of set-aside rows the user is asked before the gate.
QUARANTINE_WARNING = 0.05
DISTINCT_COLUMNS = ("algorithm_family", "usage_context", "mode", "padding", "hash", "library")
_ABSOLUTE_PATH = re.compile(r"(^|\s)(/[A-Za-z0-9._-]+/|[A-Za-z]:\\)")


def identifier_leaks(texts: Sequence[str]) -> dict[str, int]:
    """Raw identifiers left in prep text: an address with a scheme and an absolute local path (H6; the e-mail and secret
    patterns are the redaction rules', counted by the secret scanner)."""
    found: Counter[str] = Counter()
    for text in texts:
        if "://" in text:
            found["url"] += 1
        if _ABSOLUTE_PATH.search(text):
            found["absolute_path"] += 1
    return dict(found)


def _distinct_in_raw(events: Sequence[RawEvent]) -> dict[str, int]:
    values: dict[str, set[object]] = {column: set() for column in (*DISTINCT_COLUMNS, "raw_name")}
    for event in events:
        items = event.payload.get("findings")
        rows = items if isinstance(items, list) else [event.payload] if event.event_type == "finding_detected" else []
        for item in rows:
            if isinstance(item, Mapping):
                for column, seen in values.items():
                    if item.get(column) is not None:
                        seen.add(item.get(column))
    return {column: len(seen) for column, seen in values.items()}


@dataclass(frozen=True)
class PreprocessReport:
    generated_at: datetime
    counts: tuple[FilterCount, ...]
    rejections: Mapping[str, int]  # "<filter>: <error code>" -> records
    distinct: Mapping[str, tuple[int, int | None]]  # column -> (in raw, in prep); raw_name is not in prep (D-310c)
    leaks: Mapping[str, int]
    projects_by_origin: Mapping[str, int]
    findings: int
    rows_in: int
    rows_rejected: int

    @property
    def quarantine_rate(self) -> float:
        return self.rows_rejected / self.rows_in if self.rows_in else 0.0

    @property
    def quarantine_warning(self) -> bool:
        return self.quarantine_rate > QUARANTINE_WARNING

    @property
    def leak_free(self) -> bool:
        return not any(self.leaks.values())

    @property
    def corpus_projects(self) -> int:
        return self.projects_by_origin.get("CORPUS", 0)

    @property
    def projects_target_met(self) -> bool:
        return self.corpus_projects >= CORPUS_MINIMUM

    @property
    def findings_target_met(self) -> bool:
        return self.findings >= FINDINGS_TARGET

    @property
    def funnel_consistent(self) -> bool:
        """Every filter took what the previous one let through, and nothing appeared from nowhere."""
        chained = all(a.rows_out == b.rows_in for a, b in zip(self.counts, self.counts[1:], strict=False))
        return chained and all(c.rows_dropped >= 0 for c in self.counts)


def build_report(
    *,
    extracted: PrepBatch,
    final: PrepBatch,
    counts: Sequence[FilterCount],
    rejected: Sequence[Rejection],
    leaks: Mapping[str, int],
    generated_at: datetime,
) -> PreprocessReport:
    before = _distinct_in_raw(extracted.events)
    after = {column: len({getattr(f, column) for f in final.findings} - {None}) for column in DISTINCT_COLUMNS}
    distinct: dict[str, tuple[int, int | None]] = {
        column: (before[column], after[column]) for column in DISTINCT_COLUMNS
    }
    distinct["raw_name"] = (before["raw_name"], None)
    return PreprocessReport(
        generated_at=generated_at,
        counts=tuple(counts),
        rejections=dict(Counter(f"{r.filter_code}: {r.error_code}" for r in rejected)),
        distinct=distinct,
        leaks=dict(leaks),
        projects_by_origin=dict(Counter(p.origin for p in final.projects)),
        findings=len(final.findings),
        rows_in=extracted.size,
        rows_rejected=sum(c.rows_rejected for c in counts),
    )


__all__ = ["CORPUS_TARGET", "FINDINGS_TARGET", "PreprocessReport", "build_report", "identifier_leaks"]

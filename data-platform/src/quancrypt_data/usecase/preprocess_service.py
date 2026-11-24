from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from quancrypt_data.domain.prep import PrepBatch, RecordFilter, Rejection, run_filters
from quancrypt_data.domain.prep_extract import extract
from quancrypt_data.domain.prep_report import build_report, identifier_leaks
from quancrypt_data.port.inbound.preprocess import PreprocessResult, PreprocessUseCase
from quancrypt_data.port.outbound.prep import (
    PrepReader,
    PrepReportWriter,
    PrepRepository,
    ProjectContent,
    RawEventSource,
)
from quancrypt_data.port.outbound.profiling import SecretScanner
from quancrypt_data.port.outbound.system import Clock


class PreprocessService(PreprocessUseCase):
    """Pipes and Filters (data-preprocessing section 3): raw is read, every filter of the configured order runs, and
    each project is written in a transaction of its own that deletes its prep rows first (idempotent: the same raw
    gives the same prep). A project no longer in raw (erased) loses its prep rows too. After writing, prep is read back
    and scanned for leaks (H6); the report says what each filter did."""

    def __init__(
        self,
        source: RawEventSource,
        filters: Sequence[RecordFilter],
        repository: PrepRepository,
        reader: PrepReader,
        scanner: SecretScanner,
        writer: PrepReportWriter,
        clock: Clock,
    ) -> None:
        self._source = source
        self._filters = tuple(filters)
        self._repository = repository
        self._reader = reader
        self._scanner = scanner
        self._writer = writer
        self._clock = clock

    def execute(self) -> PreprocessResult:
        extracted = extract(self._source.events(), self._source.labels())
        final, rejected, counts = run_filters(extracted, self._filters)
        # Fail closed (D-314): what is about to be written is checked first and nothing is written if it leaks;
        # what was written is read back and checked again below.
        leaks = self._leaks(*_candidate_texts(final))
        if not leaks:
            self._write(final, rejected)
            leaks = self._leaks(self._reader.text_values(), self._reader.path_values())
        report = build_report(
            extracted=extracted, final=final, counts=counts, rejected=rejected, leaks=leaks,
            generated_at=self._clock.now(),
        )  # fmt: skip
        written = self._writer.write(report, self._reader.table_stats())
        return PreprocessResult(
            written=tuple(written),
            projects=len(final.projects),
            findings=report.findings,
            rows_in=report.rows_in,
            rows_rejected=report.rows_rejected,
            leaks=report.leaks,
            quarantine_rate=report.quarantine_rate,
            quarantine_warning=report.quarantine_warning,
            projects_target_met=report.projects_target_met,
            findings_target_met=report.findings_target_met,
        )

    def _leaks(self, texts: Sequence[str], path_values: Sequence[str]) -> dict[str, int]:
        # A path is scanned per segment: the redaction rules read "/" as part of a token, so a long anonymised path
        # (several 12-character segments) looked like one random string (high_entropy, D-312). Identifier checks
        # (`://`, absolute path) still read the whole path.
        paths = set(path_values)
        pieces = [t for t in texts if t not in paths] + [s for p in paths for s in p.split("/") if s]
        return {**identifier_leaks(texts), **dict(self._scanner.scan(pieces))}

    def _write(self, batch: PrepBatch, rejected: Sequence[Rejection]) -> None:
        by_project: dict[str | None, list[Rejection]] = defaultdict(list)
        for rejection in rejected:
            by_project[None if rejection.label is not None else rejection.project_key].append(rejection)
        written: set[str] = set()
        for project in batch.projects:
            key = project.project_key
            content = ProjectContent(
                project=project,
                units=tuple(u for u in batch.units if u.project_key == key),
                findings=tuple(f for f in batch.findings if f.project_key == key),
                topologies=tuple(t for t in batch.topologies if t.project_key == key),
                links=tuple(link for link in batch.links if link.project_key == key),
                scopes=tuple(s for s in batch.scopes if s.project_key == key),
            )
            self._repository.replace_project(key, content, by_project.get(key, []))
            written.add(key)
        for key in sorted(self._repository.stored_project_keys() - written):
            self._repository.replace_project(key, None, [])
        self._repository.replace_labels(batch.labels, by_project.get(None, []))


def _candidate_texts(batch: PrepBatch) -> tuple[list[str], list[str]]:
    """The text values the batch would write: all of them, and the ones that are paths."""
    paths: list[object] = [*(u.unit_path for u in batch.units), *(f.unit_path for f in batch.findings)]
    paths += [f.file_path for f in batch.findings] + [label.file_path for label in batch.labels]
    others: list[object] = [v for u in batch.units for v in (u.java_version, u.spring_boot_version)]
    others += [v for f in batch.findings for v in (f.mode, f.padding, f.hash, f.library)]
    others += [v for label in batch.labels for v in (label.case_id, label.category)]
    path_texts = [p for p in paths if isinstance(p, str)]
    return path_texts + [v for v in others if isinstance(v, str)], path_texts

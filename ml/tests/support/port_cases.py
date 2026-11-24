"""Shared contracts of the outbound ports that have a fake (LSP, hexagonal-service section 7): the fake and the real adapter
run the same cases. LabelStore has its own module (label_store_cases.py)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from quancrypt_ml.domain.labels import CONTEXT_OK, BatchRow, Candidate, SampledFinding, SourceLocation
from quancrypt_ml.port.outbound.labeling import (
    AnalyzerUnavailableError,
    BatchFiles,
    LabelCandidateSource,
    ReportWriter,
    SnippetSource,
    SnippetUnavailableError,
    SourceLocator,
)
from tests.support.fakes import candidate

# ---------------------------------------------------------------- LabelCandidateSource
# A factory builds a source holding exactly the given candidates.
CandidateFactory = Callable[[Sequence[Candidate]], LabelCandidateSource]


def candidates_case_every_stored_candidate_comes_back_in_id_order(factory: CandidateFactory) -> None:
    rows = [candidate(3, "RSA"), candidate(1, "ECDSA", "SIGNATURE", test=True), candidate(2, "SHA1", priority="P0")]
    source = factory(rows)
    assert source.candidates() == sorted(rows, key=lambda c: c.finding_id)


def candidates_case_known_names_only_stored_findings(factory: CandidateFactory) -> None:
    source = factory([candidate(1), candidate(2)])
    absent = "00000000-0000-4000-8000-999999999999"
    assert source.known([candidate(1).finding_id, absent]) == {candidate(1).finding_id}
    assert source.known([]) == set()


CANDIDATE_CASES = [
    candidates_case_every_stored_candidate_comes_back_in_id_order,
    candidates_case_known_names_only_stored_findings,
]

# ---------------------------------------------------------------- SourceLocator
# A factory builds a locator that knows one corpus finding per given location and returns the finding ids it gave them
# (the PostgreSQL adapter cannot take arbitrary ids: prep's id is uuid5 of the source event and the ordinal).
LocatorFactory = Callable[[Sequence[SourceLocation]], tuple[SourceLocator, list[str]]]


def locator_case_known_findings_are_located_and_others_left_out(factory: LocatorFactory) -> None:
    locations = [
        SourceLocation("/corpus/acme__shop/payment", "src/B.java", 7),
        SourceLocation("/corpus/acme__shop", "certs/a.pem", None),
    ]
    locator, ids = factory(locations)
    unknown = "00000000-0000-4000-8000-999999999999"
    assert locator.locate([*ids, unknown]) == dict(zip(ids, locations, strict=True))
    assert locator.locate([]) == {}


LOCATOR_CASES = [locator_case_known_findings_are_located_and_others_left_out]

# ---------------------------------------------------------------- SnippetSource
# A factory builds a source for an analyzer that serves `path` (lines 1..20), refuses `refused` and is down when `down`.
SnippetFactory = Callable[[str, str, bool], SnippetSource]


def snippets_case_lines_around_the_location(factory: SnippetFactory) -> None:
    source = factory("src/A.java", "src/Gone.java", False)
    lines = source.context(SourceLocation("/corpus/a", "src/A.java", 10), 2)
    assert [n for n, _ in lines] == [8, 9, 10, 11, 12]
    assert all(isinstance(text, str) for _, text in lines)


def snippets_case_a_refused_location_and_an_outage_are_told_apart(factory: SnippetFactory) -> None:
    with pytest.raises(SnippetUnavailableError):
        factory("src/A.java", "src/Gone.java", False).context(SourceLocation("/corpus/a", "src/Gone.java", 3), 2)
    with pytest.raises(AnalyzerUnavailableError):
        factory("src/A.java", "src/Gone.java", True).context(SourceLocation("/corpus/a", "src/A.java", 3), 2)


SNIPPET_CASES = [snippets_case_lines_around_the_location, snippets_case_a_refused_location_and_an_outage_are_told_apart]

# ---------------------------------------------------------------- BatchFiles


def _row(n: int, double: bool) -> BatchRow:
    location = SourceLocation("/corpus/a", f"src/F{n}.java", n)
    return BatchRow(SampledFinding(candidate(n), double), location, ((n, "code"),), CONTEXT_OK)


def files_case_a_written_batch_reads_back_one_row_per_finding(files: BatchFiles, folder: Path) -> None:
    path = folder / "batch.csv"
    files.write_batch(path, [_row(1, True), _row(2, False)])
    rows = files.read_rows(path)
    assert [(r["finding_id"], r["double_label"], r["label"]) for r in rows] == [
        (candidate(1).finding_id, "true", ""),
        (candidate(2).finding_id, "false", ""),
    ]


def files_case_written_rows_read_back_as_written(files: BatchFiles, folder: Path) -> None:
    path = folder / "rows.csv"
    rows = [{"finding_id": "a", "label": "HIGH", "notes": "not, virgül"}, {"finding_id": "b", "label": "", "notes": ""}]
    files.write_rows(path, rows)
    assert files.read_rows(path) == rows


FILES_CASES = [files_case_a_written_batch_reads_back_one_row_per_finding, files_case_written_rows_read_back_as_written]

# ---------------------------------------------------------------- ReportWriter
# The report is read back through the second callable (the file for the real adapter, the memory for the fake).


def reports_case_the_last_write_wins(writer: ReportWriter, read: Callable[[Path], str], folder: Path) -> None:
    path = folder / "reports" / "labeling.md"
    writer.write(path, "# eski\n")
    writer.write(path, "# Etiketleme raporu\n")
    assert read(path) == "# Etiketleme raporu\n"


REPORT_CASES = [reports_case_the_last_write_wins]

"""Every outbound port with a fake: the fake and the real adapter pass the same cases (tests/support/port_cases.py). The
PostgreSQL adapters of LabelCandidateSource and SourceLocator run the same cases in tests/integration."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

import httpx
import pytest

from quancrypt_ml.domain.labels import SourceLocation
from quancrypt_ml.infrastructure.analyzer.snippet_client import AnalyzerSnippetClient
from quancrypt_ml.infrastructure.files.batch_csv import CsvBatchFiles
from quancrypt_ml.infrastructure.files.text_files import FileReportWriter
from quancrypt_ml.port.outbound.labeling import BatchFiles, ReportWriter, SnippetSource, SourceLocator
from tests.support.fakes import FakeCandidates, FakeFiles, FakeLocator, FakeReports, FakeSnippets, candidate
from tests.support.port_cases import (
    CANDIDATE_CASES,
    FILES_CASES,
    LOCATOR_CASES,
    REPORT_CASES,
    SNIPPET_CASES,
    CandidateFactory,
    LocatorFactory,
    SnippetFactory,
)


def _fake_snippets(served: str, refused: str, down: bool) -> SnippetSource:
    return FakeSnippets(missing={refused}, down=down)


def _analyzer_snippets(served: str, refused: str, down: bool) -> SnippetSource:
    """The real client against a stand-in analyzer that answers like contracts/openapi/analyzer-service.yaml."""

    def answer(request: httpx.Request) -> httpx.Response:
        if down:
            raise httpx.ConnectError("refused", request=request)
        params = request.url.params
        if params["path"] != served:
            return httpx.Response(404, json={"type": "https://quancrypt.local/problems/not-found"})
        line, context = int(params["line"]), int(params["context"])
        lines = [{"number": n, "text": f"line {n}"} for n in range(max(1, line - context), min(20, line + context) + 1)]
        return httpx.Response(200, json={"path": served, "lines": lines})

    return AnalyzerSnippetClient("http://127.0.0.1:8082", "t" * 40, transport=httpx.MockTransport(answer))


@pytest.mark.parametrize("make", [_fake_snippets, _analyzer_snippets], ids=["fake", "analyzer"])
@pytest.mark.parametrize("case", SNIPPET_CASES, ids=lambda c: c.__name__)
def test_snippet_sources_keep_the_contract(case: Callable[[SnippetFactory], None], make: SnippetFactory) -> None:
    case(make)


@pytest.mark.parametrize("make", [FakeFiles, CsvBatchFiles], ids=["fake", "csv"])
@pytest.mark.parametrize("case", FILES_CASES, ids=lambda c: c.__name__)
def test_batch_files_keep_the_contract(
    case: Callable[[BatchFiles, Path], None], make: Callable[[], BatchFiles], tmp_path: Path
) -> None:
    case(make(), tmp_path)


@pytest.mark.parametrize("case", REPORT_CASES, ids=lambda c: c.__name__)
def test_report_writers_keep_the_contract(
    case: Callable[[ReportWriter, Callable[[Path], str], Path], None], tmp_path: Path
) -> None:
    fake = FakeReports()
    case(fake, fake.read, tmp_path / "fake")
    case(FileReportWriter(), lambda p: p.read_text(encoding="utf-8"), tmp_path / "file")


@pytest.mark.parametrize("case", CANDIDATE_CASES, ids=lambda c: c.__name__)
def test_the_fake_candidate_source_keeps_the_contract(case: Callable[[CandidateFactory], None]) -> None:
    case(lambda rows: FakeCandidates(rows))


@pytest.mark.parametrize("case", LOCATOR_CASES, ids=lambda c: c.__name__)
def test_the_fake_locator_keeps_the_contract(case: Callable[[LocatorFactory], None]) -> None:
    def factory(locations: Sequence[SourceLocation]) -> tuple[SourceLocator, list[str]]:
        ids = [candidate(n).finding_id for n in range(len(locations))]
        return FakeLocator(dict(zip(ids, locations, strict=True))), ids

    case(factory)

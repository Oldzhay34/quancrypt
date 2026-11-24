"""The Preprocess use case, its facade and the `preprocess` command with fake ports (P6.4)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from typer.testing import CliRunner

from quancrypt_data.api import cli
from quancrypt_data.api.cli import app
from quancrypt_data.domain.filters.deduplicator import Deduplicator
from quancrypt_data.domain.filters.missing_value_handler import MissingValueHandler
from quancrypt_data.domain.filters.type_caster import TypeCaster
from quancrypt_data.domain.prep import RawEvent, RawLabel, RecordFilter
from quancrypt_data.facade.preprocess_facade import PrepLeakError, PreprocessFacade
from quancrypt_data.port.inbound.preprocess import PreprocessResult
from quancrypt_data.usecase.preprocess_service import PreprocessService
from tests.support.prep_fakes import InMemoryPrepStore, InMemoryRawEventSource, RecordingPrepReportWriter, content
from tests.support.profiling_fakes import AtSignScanner

NOW = datetime(2026, 11, 23, tzinfo=UTC)
KEY = "a" * 64


class Clock:
    def now(self) -> datetime:
        return NOW


def analysis(event_id: str, findings: list[dict[str, object]], key: str = KEY) -> RawEvent:
    payload = {"analysis_unit": ".", "chunk_index": 0, "chunk_count": 1, "findings": findings,
               "runtime": {"java_version": "21", "spring_boot_version": None}}  # fmt: skip
    return RawEvent(event_id, "corpus_analysis", "corpus", 1, NOW, key, payload)


FINDING = {"file": "src/main/java/A.java", "line_start": 3, "line_end": 3, "algorithm_family": "RSA",
           "usage_context": "SIGNATURE", "location_kind": "CODE", "priority": "P2", "key_size_bits": 2048,
           "confidence": 0.9}  # fmt: skip


def service(
    source: InMemoryRawEventSource, store: InMemoryPrepStore, writer: RecordingPrepReportWriter
) -> PreprocessService:
    filters: list[RecordFilter] = [Deduplicator(), MissingValueHandler(), TypeCaster()]
    return PreprocessService(source, filters, store, store, AtSignScanner(), writer, Clock())


class TestService:
    def test_raw_goes_through_the_filters_into_prep_and_the_report(self) -> None:
        source = InMemoryRawEventSource(
            [analysis("e1", [FINDING, FINDING, {**FINDING, "line_start": 4, "line_end": 4, "priority": "P9"}])],
            [RawLabel("owasp-benchmark", "c1", None, None, None, True)],
        )
        store = InMemoryPrepStore()
        store.replace_project("d" * 64, content("d" * 64), [])  # a project erased from raw since the last run
        writer = RecordingPrepReportWriter()

        result = service(source, store, writer).execute()

        assert set(store.projects) == {KEY}, "a project no longer in raw loses its prep rows"
        assert len(store.projects[KEY].findings) == 1 and len(store.labels) == 1
        assert [r.message for r in store.rejections[KEY]] == ["finding.priority"]
        assert (result.findings, result.rows_in, result.rows_rejected, result.leaks) == (1, 4, 1, {})
        report = writer.reports[0]
        assert [(c.filter_code, c.rows_in, c.rows_out) for c in report.counts] == [
            ("Deduplicator", 4, 3), ("MissingValueHandler", 3, 3), ("TypeCaster", 3, 2)
        ]  # fmt: skip
        assert report.funnel_consistent and result.quarantine_warning  # 1 of 4 rows set aside: 25% > 5%

    def test_running_twice_gives_the_same_prep(self) -> None:
        source = InMemoryRawEventSource([analysis("e1", [FINDING]), analysis("e2", [FINDING], key="b" * 64)])
        store = InMemoryPrepStore()
        run = service(source, store, RecordingPrepReportWriter())

        run.execute()
        first = (dict(store.projects), dict(store.rejections), list(store.labels))
        run.execute()

        assert (dict(store.projects), dict(store.rejections), list(store.labels)) == first

    def test_a_leak_in_what_was_written_is_counted(self) -> None:
        source = InMemoryRawEventSource([analysis("e1", [{**FINDING, "library": "x@y"}])])
        store = InMemoryPrepStore()

        result = service(source, store, RecordingPrepReportWriter()).execute()

        assert result.leaks == {"email": 1}
        assert store.projects == {}, "a leak found before the write stops the write (D-314)"


class StubUseCase:
    def __init__(self, leaks: dict[str, int], warning: bool = False) -> None:
        self._leaks = leaks
        self._warning = warning

    def execute(self) -> PreprocessResult:
        return PreprocessResult(("reports/preprocessing_report.md",), 40, 330, 330, 0, self._leaks, 0.0, self._warning,
                                True, False)  # fmt: skip


class TestFacade:
    def test_counts_notes_and_the_target_warning(self) -> None:
        view = PreprocessFacade(StubUseCase({}, warning=True)).preprocess()

        assert view.counts["findings"] == 330 and view.counts["leaks"] == 0
        assert any("above 5%" in note for note in view.notes)
        assert any("H5" in note for note in view.notes)

    def test_a_leak_is_an_error(self) -> None:
        with pytest.raises(PrepLeakError, match="email=1"):
            PreprocessFacade(StubUseCase({"email": 1})).preprocess()


@pytest.mark.parametrize(("leaks", "exit_code"), [({}, 0), ({"email": 2}, 1)])
def test_the_preprocess_command_fails_on_a_leak(
    monkeypatch: pytest.MonkeyPatch, leaks: dict[str, int], exit_code: int
) -> None:
    class Container:
        preprocessing = PreprocessFacade(StubUseCase(leaks))

        def close(self) -> None:
            pass

    monkeypatch.setattr(cli, "bootstrap", lambda **_: Container())

    result = CliRunner().invoke(app, ["preprocess"])

    assert result.exit_code == exit_code, result.output
    assert ("PrepLeakError" in result.output) is bool(leaks)

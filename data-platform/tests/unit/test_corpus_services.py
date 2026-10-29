"""The corpus use cases against fakes of every outbound port (P6.2): what is cloned, excluded, analysed, delivered and reported."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from quancrypt_data.domain.corpus import (
    AnalysisStatus,
    Candidate,
    CloneStatus,
    ExclusionReason,
    ManifestEntry,
    RepoRef,
    SelectionPolicy,
)
from quancrypt_data.domain.corpus_events import (
    AnalysisStats,
    CorpusFinding,
    Runtime,
    TopologySummary,
    UnitAnalysis,
    project_key,
    repo_identifier,
)
from quancrypt_data.port.inbound.corpus import (
    AnalyzeCorpusCommand,
    BuildCorpusListCommand,
    CloneCorpusCommand,
    CloneCorpusResult,
    LoadBenchmarkCommand,
    UnknownBenchmarkError,
)
from quancrypt_data.port.outbound.corpus import (
    AnalysisFailedError,
    AnalysisUnsupportedError,
    BenchmarkLabel,
    CloneError,
    CloneResult,
    DeliveryResult,
    EventDeliveryError,
)
from quancrypt_data.usecase.analyze_corpus_service import AnalyzeCorpusService
from quancrypt_data.usecase.build_corpus_list_service import BuildCorpusListService
from quancrypt_data.usecase.clone_corpus_service import CloneCorpusService
from quancrypt_data.usecase.event_delivery import MAX_REQUEST_BYTES, deliver
from quancrypt_data.usecase.load_benchmarks_service import LoadBenchmarksService
from quancrypt_data.usecase.project_analysis import ProjectAnalyzer
from quancrypt_data.usecase.report_corpus_service import ReportCorpusService
from tests.support.corpus_fakes import FakeHasher, FakeLabels, FakeListing, FakeManifest, FakeWriter

NOW = datetime(2026, 10, 28, 9, 30, tzinfo=UTC)
MIT = (
    "Permission is hereby granted, free of charge, to any person obtaining a copy. The above copyright notice and this "
    "permission notice shall be included in all copies or substantial portions of the Software. THE SOFTWARE IS PROVIDED "
    '"AS IS", WITHOUT WARRANTY OF ANY KIND.'
)
GIB = 1024**3


def repo(name: str) -> RepoRef:
    return RepoRef.parse(f"https://github.com/acme/{name}")


class Clock:
    def now(self) -> datetime:
        return NOW


@dataclass
class FakeFiles:
    """The corpus root: `present` maps a directory to its facts."""

    licenses: dict[str, str | None] = field(default_factory=dict)
    spring_boot: set[str] = field(default_factory=set)
    services: dict[str, list[str]] = field(default_factory=dict)
    present: set[str] = field(default_factory=set)
    removed: list[str] = field(default_factory=list)
    size: int = 0
    copied: list[str] = field(default_factory=list)

    def exists(self, dir_name: str) -> bool:
        return dir_name in self.present

    def read_license(self, dir_name: str) -> str | None:
        return self.licenses.get(dir_name)

    def has_spring_boot(self, dir_name: str) -> bool:
        return dir_name in self.spring_boot

    def service_directories(self, dir_name: str, max_depth: int, limit: int) -> Sequence[str]:
        return self.services.get(dir_name, [])[:limit]

    def size_bytes(self) -> int:
        return self.size

    def remove(self, dir_name: str) -> None:
        self.present.discard(dir_name)
        self.removed.append(dir_name)

    def copy_benchmark(self, source: Path, name: str) -> str:
        self.copied.append(name)
        return f"_benchmarks/{name}"

    def good(self, name: str, services: int = 3) -> None:
        directory = repo(name).dir_name
        self.licenses[directory] = MIT
        self.spring_boot.add(directory)
        self.services[directory] = [f"svc{i}" for i in range(services)]


class FakeGit:
    def __init__(self, files: FakeFiles, grow_by: int = 0) -> None:
        self.files = files
        self.cloned: list[str] = []
        self.failing: set[str] = set()
        self.grow_by = grow_by

    def clone(self, repository: RepoRef) -> CloneResult:
        if repository.name in self.failing:
            raise CloneError("git clone failed (CalledProcessError)")
        self.cloned.append(repository.name)
        self.files.present.add(repository.dir_name)
        self.files.size += self.grow_by
        return CloneResult(commit_sha="f" * 40, default_branch="main")


def finding(index: int = 0) -> CorpusFinding:
    return CorpusFinding(
        file=f"src/A{index}.java",
        line_start=1,
        line_end=1,
        raw_name="SHA1withRSA",
        algorithm_family="RSA",
        usage_context="SIGNATURE",
        location_kind="CODE",
        priority="P0",
        key_size_bits=2048,
        mode=None,
        padding=None,
        hash="SHA-1",
        library="JCA",
        confidence=0.9,
    )


def analysis(count: int = 2) -> UnitAnalysis:
    return UnitAnalysis(
        ".", Runtime("21", "3.3.1"), tuple(finding(i) for i in range(count)), AnalysisStats(9, count, 5), None
    )


class FakeAnalyzer:
    """Answers per root: an analysis, 'unsupported' or 'failed'."""

    def __init__(self) -> None:
        self.answers: dict[str, UnitAnalysis | str] = {}
        self.topologies: dict[str, TopologySummary | None] = {}
        self.calls: list[str] = []

    def analyze(self, root: str) -> UnitAnalysis:
        self.calls.append(root)
        answer = self.answers.get(root, "unsupported")
        if answer == "unsupported":
            raise AnalysisUnsupportedError("no")
        if answer == "failed":
            raise AnalysisFailedError("analyzer-service answered 500")
        assert isinstance(answer, UnitAnalysis)
        return answer

    def topology(self, root: str) -> TopologySummary | None:
        return self.topologies.get(root)


class FakeSink:
    def __init__(self) -> None:
        self.requests: list[list[Mapping[str, object]]] = []
        self.fail = False

    def send(self, events: Sequence[Mapping[str, object]]) -> DeliveryResult:
        if self.fail:
            raise EventDeliveryError("ingest-api answered 500")
        self.requests.append(list(events))
        return DeliveryResult(accepted=len(events))

    @property
    def events(self) -> list[Mapping[str, object]]:
        return [e for request in self.requests for e in request]


class Dataset:
    def __init__(self, candidates: Sequence[Candidate]) -> None:
        self.candidates = candidates

    def read(self, path: Path) -> Sequence[Candidate]:
        return self.candidates


def clone_service(repos: Sequence[str], **options: int) -> tuple[CloneCorpusService, FakeManifest, FakeFiles, FakeGit]:
    files = FakeFiles()
    for name in repos:
        files.good(name)
    manifest = FakeManifest()
    git = FakeGit(files, grow_by=options.get("grow_by", 0))
    listing = FakeListing([repo(n) for n in repos])
    return CloneCorpusService(listing, manifest, git, files), manifest, files, git


def clone(service: CloneCorpusService, offset: int = 0, limit: int = 100, gib: int = 10) -> CloneCorpusResult:
    return service.execute(CloneCorpusCommand(offset, limit, gib * GIB))


class TestBuildList:
    def test_the_list_is_what_the_policy_selects_and_the_result_counts_what_was_turned_away(self) -> None:
        candidates = [
            Candidate(repo("a"), None, None, "Java", 4),
            Candidate(repo("b"), None, None, "Python", None),
        ]
        listing = FakeListing()

        result = BuildCorpusListService(Dataset(candidates), listing, SelectionPolicy()).execute(
            BuildCorpusListCommand(Path("x.csv"), 10)
        )

        assert (result.candidates, result.selected) == (2, 1)
        assert result.turned_away == {"not-java": 1}
        assert [p.candidate.repo.name for p in listing.written] == ["a"]


class TestClone:
    def test_a_project_that_passes_every_check_is_cloned_and_kept(self) -> None:
        service, manifest, files, git = clone_service(["a"])

        result = clone(service)

        entry = manifest.entries[repo("a").canonical]
        assert (result.attempted, result.cloned, result.failed) == (1, 1, 0)
        assert entry.status is CloneStatus.CLONED
        assert entry.commit_sha == "f" * 40
        assert entry.license_verified == "MIT"
        assert git.cloned == ["a"]
        assert files.removed == []

    @pytest.mark.parametrize(
        ("break_it", "reason"),
        [
            (lambda f, d: f.licenses.__setitem__(d, None), ExclusionReason.LICENSE_UNVERIFIED),
            (lambda f, d: f.licenses.__setitem__(d, "All rights reserved"), ExclusionReason.LICENSE_UNVERIFIED),
            (lambda f, d: f.spring_boot.discard(d), ExclusionReason.NO_SPRING_BOOT),
            (lambda f, d: f.services.__setitem__(d, ["one", "two"]), ExclusionReason.TOO_FEW_SERVICES),
        ],
    )
    def test_a_project_that_fails_a_check_is_removed_from_disk_and_the_reason_is_kept(
        self, break_it: Callable[[FakeFiles, str], object], reason: ExclusionReason
    ) -> None:
        service, manifest, files, _ = clone_service(["a"])
        break_it(files, repo("a").dir_name)

        result = clone(service)

        entry = manifest.entries[repo("a").canonical]
        assert (result.cloned, result.excluded) == (0, {reason.value: 1})
        assert (entry.status, entry.exclusion_reason) == (CloneStatus.EXCLUDED, reason)
        assert files.removed == [repo("a").dir_name]
        assert not files.exists(repo("a").dir_name)

    def test_a_failed_clone_is_recorded_and_the_run_goes_on(self) -> None:
        service, manifest, _, git = clone_service(["a", "b"])
        git.failing.add("a")

        result = clone(service)

        assert (result.cloned, result.failed) == (1, 1)
        assert manifest.entries[repo("a").canonical].status is CloneStatus.FAILED
        assert manifest.entries[repo("a").canonical].exclusion_reason is ExclusionReason.CLONE_FAILED

    def test_a_project_already_cloned_or_excluded_is_not_cloned_again_but_a_failed_one_is_tried_again(self) -> None:
        service, manifest, files, git = clone_service(["a", "b", "c"])
        clone(service)
        manifest.entries[repo("b").canonical] = replace(
            manifest.entries[repo("b").canonical],
            status=CloneStatus.EXCLUDED,
            exclusion_reason=ExclusionReason.NO_SPRING_BOOT,
        )
        manifest.entries[repo("c").canonical] = replace(
            manifest.entries[repo("c").canonical], status=CloneStatus.FAILED
        )
        files.present.discard(repo("c").dir_name)
        git.cloned.clear()

        result = clone(service)

        assert (result.already_there, result.cloned) == (2, 1)
        assert git.cloned == ["c"]

    def test_the_window_limits_which_projects_are_touched(self) -> None:
        service, manifest, _, git = clone_service(["a", "b", "c", "d"])

        clone(service, offset=1, limit=2)

        assert git.cloned == ["b", "c"]
        assert set(manifest.entries) == {repo("b").canonical, repo("c").canonical}

    def test_the_run_stops_when_the_corpus_root_reaches_the_disk_limit(self) -> None:
        service, manifest, _, git = clone_service(["a", "b", "c"], grow_by=6 * GIB)

        result = clone(service, gib=10)

        assert git.cloned == ["a", "b"]  # 6 GiB after the first, 12 GiB after the second: the third is not started
        assert result.stopped_by_disk_limit
        assert result.disk_bytes == 12 * GIB
        assert repo("c").canonical not in manifest.entries

    def test_the_manifest_is_saved_after_every_project_so_that_a_crash_loses_one_at_most(self) -> None:
        service, manifest, _, _ = clone_service(["a", "b", "c"])

        clone(service)

        assert manifest.saves >= 3


class TestAnalyze:
    def _service(
        self, names: Sequence[str]
    ) -> tuple[AnalyzeCorpusService, FakeManifest, FakeAnalyzer, FakeSink, FakeFiles]:
        files = FakeFiles()
        manifest = FakeManifest()
        for name in names:
            files.good(name)
            manifest.entries[repo(name).canonical] = ManifestEntry(repo(name).url, status=CloneStatus.CLONED)
        analyzer = FakeAnalyzer()
        sink = FakeSink()
        service = AnalyzeCorpusService(
            FakeListing([repo(n) for n in names]),
            manifest,
            ProjectAnalyzer(analyzer, files, "/corpus"),
            sink,
            FakeHasher(),
            Clock(),
        )
        return service, manifest, analyzer, sink, files

    def test_a_project_the_root_of_which_can_be_analysed_sends_one_event_with_the_topology(self) -> None:
        service, manifest, analyzer, sink, _ = self._service(["a"])
        root = f"/corpus/{repo('a').dir_name}"
        analyzer.answers[root] = analysis(3)
        analyzer.topologies[root] = TopologySummary(2, 1, 1, 0, {"HTTP": 1})

        result = service.execute(AnalyzeCorpusCommand(0, 10))

        assert (result.analyzed, result.findings_total, result.events_sent, result.accepted) == (1, 3, 1, 1)
        payload = sink.events[0]["payload"]
        assert payload["analysis_unit"] == "." and payload["topology"]["edge_count"] == 1  # type: ignore[index]
        entry = manifest.entries[repo("a").canonical]
        assert (entry.analysis_status, entry.findings_total, entry.units) == (AnalysisStatus.ANALYZED, 3, 1)
        assert entry.analyzed_at == "2026-10-28T09:30:00Z"

    def test_the_event_carries_the_key_of_the_address_and_never_the_address(self) -> None:
        service, _, analyzer, sink, _ = self._service(["a"])
        analyzer.answers[f"/corpus/{repo('a').dir_name}"] = analysis()

        service.execute(AnalyzeCorpusCommand(0, 10))

        event = sink.events[0]
        assert event["project_key"] == project_key("k" * 40, repo_identifier(repo("a")))
        assert "acme" not in str(event)

    def test_a_module_inside_an_analysed_unit_is_not_analysed_again(self) -> None:
        service, manifest, analyzer, sink, files = self._service(["a"])
        root = f"/corpus/{repo('a').dir_name}"
        files.services[repo("a").dir_name] = ["parent", "parent/child", "other"]
        analyzer.answers[f"{root}/parent"] = analysis(2)
        analyzer.answers[f"{root}/parent/child"] = analysis(2)  # already part of `parent`: must not be asked for
        analyzer.answers[f"{root}/other"] = analysis(1)

        service.execute(AnalyzeCorpusCommand(0, 10))

        assert [e["payload"]["analysis_unit"] for e in sink.events] == ["parent", "other"]  # type: ignore[index]
        assert f"{root}/parent/child" not in analyzer.calls
        assert manifest.entries[repo("a").canonical].findings_total == 3

    def test_a_root_the_analyzer_refuses_is_analysed_service_by_service_without_a_topology(self) -> None:
        service, manifest, analyzer, sink, _ = self._service(["a"])
        root = f"/corpus/{repo('a').dir_name}"
        analyzer.answers[f"{root}/svc0"] = analysis(2)
        analyzer.answers[f"{root}/svc1"] = analysis(1)  # svc2 stays unsupported and is skipped

        result = service.execute(AnalyzeCorpusCommand(0, 10))

        assert (result.analyzed, result.findings_total, result.events_sent) == (1, 3, 2)
        assert [e["payload"]["analysis_unit"] for e in sink.events] == ["svc0", "svc1"]  # type: ignore[index]
        assert all(e["payload"]["topology"] is None for e in sink.events)  # type: ignore[index]
        assert manifest.entries[repo("a").canonical].units == 2

    def test_a_project_nothing_of_which_can_be_analysed_is_unsupported_and_not_tried_again(self) -> None:
        service, manifest, analyzer, sink, _ = self._service(["a"])

        first = service.execute(AnalyzeCorpusCommand(0, 10))
        calls = len(analyzer.calls)
        second = service.execute(AnalyzeCorpusCommand(0, 10))

        assert (first.unsupported, first.analyzed) == (1, 0)
        assert manifest.entries[repo("a").canonical].analysis_status is AnalysisStatus.UNSUPPORTED
        assert (second.attempted, len(analyzer.calls)) == (0, calls)
        assert sink.events == []

    def test_a_failing_analyzer_marks_the_project_failed_and_it_is_tried_again_next_run(self) -> None:
        service, manifest, analyzer, _, _ = self._service(["a"])
        root = f"/corpus/{repo('a').dir_name}"
        analyzer.answers[root] = "failed"

        first = service.execute(AnalyzeCorpusCommand(0, 10))
        analyzer.answers[root] = analysis()
        second = service.execute(AnalyzeCorpusCommand(0, 10))

        assert (first.failed, first.analyzed) == (1, 0)
        assert (second.attempted, second.analyzed) == (1, 1)
        assert manifest.entries[repo("a").canonical].analysis_status is AnalysisStatus.ANALYZED

    def test_a_delivery_that_fails_leaves_the_project_failed_and_nothing_counted(self) -> None:
        service, manifest, analyzer, sink, _ = self._service(["a"])
        analyzer.answers[f"/corpus/{repo('a').dir_name}"] = analysis()
        sink.fail = True

        result = service.execute(AnalyzeCorpusCommand(0, 10))

        assert (result.failed, result.analyzed, result.events_sent) == (1, 0, 0)
        assert manifest.entries[repo("a").canonical].analysis_status is AnalysisStatus.FAILED

    def test_a_project_that_was_not_kept_by_the_clone_step_is_not_analysed(self) -> None:
        service, manifest, analyzer, _, _ = self._service(["a", "b"])
        manifest.entries[repo("a").canonical] = replace(
            manifest.entries[repo("a").canonical], status=CloneStatus.EXCLUDED
        )

        service.execute(AnalyzeCorpusCommand(0, 10))

        assert all(repo("a").dir_name not in call for call in analyzer.calls)

    def test_the_window_limits_which_projects_are_analysed(self) -> None:
        service, _, analyzer, _, _ = self._service(["a", "b", "c"])

        service.execute(AnalyzeCorpusCommand(1, 1))

        assert analyzer.calls == [f"/corpus/{repo('b').dir_name}"] + [
            f"/corpus/{repo('b').dir_name}/svc{i}" for i in range(3)
        ]


class TestDelivery:
    def test_events_go_in_requests_of_at_most_500_events_and_a_bounded_number_of_bytes(self) -> None:
        sink = FakeSink()
        small: list[Mapping[str, object]] = [{"payload": {"findings": []}} for _ in range(1100)]
        # Ten events of about 1 MB each: the request limit is 4 MiB, so they go three or four at a time.
        big: list[Mapping[str, object]] = [{"payload": {"names": "x" * 1_000_000}} for _ in range(10)]

        deliver(sink, small)
        small_requests = [len(r) for r in sink.requests]
        sink.requests.clear()
        deliver(sink, big)

        assert small_requests == [500, 500, 100]
        assert [len(r) for r in sink.requests] == [4, 4, 2]
        assert sum(len(r) for r in sink.requests) == 10
        assert MAX_REQUEST_BYTES == 4 * 1024 * 1024

    def test_one_event_larger_than_the_request_limit_still_goes_alone(self) -> None:
        sink = FakeSink()
        huge: list[Mapping[str, object]] = [{"payload": {"names": "x" * (MAX_REQUEST_BYTES + 10)}}, {"payload": {}}]

        deliver(sink, huge)

        assert [len(r) for r in sink.requests] == [1, 1]

    def test_the_answers_of_the_requests_are_added_up(self) -> None:
        sink = FakeSink()

        totals, requests = deliver(sink, [{"payload": {"findings": []}}] * 600)

        assert (totals.accepted, requests) == (600, 2)

    def test_nothing_to_send_is_no_request(self) -> None:
        assert deliver(FakeSink(), []) == (DeliveryResult(), 0)


class FakeReader:
    def read(self, source: Path) -> Sequence[BenchmarkLabel]:
        return [
            BenchmarkLabel("case-1", "a/B.java", "weakhash", 328, True),
            BenchmarkLabel("case-2", None, None, None, False),
        ]


class TestBenchmarks:
    def _service(self) -> tuple[LoadBenchmarksService, FakeLabels, FakeAnalyzer, FakeSink, FakeFiles]:
        files, analyzer, sink, labels = FakeFiles(), FakeAnalyzer(), FakeSink(), FakeLabels()
        service = LoadBenchmarksService(
            {"owasp-benchmark": FakeReader()},
            labels,
            files,
            ProjectAnalyzer(analyzer, files, "/corpus"),
            sink,
            FakeHasher(),
            Clock(),
        )
        return service, labels, analyzer, sink, files

    def test_the_labels_are_stored_and_the_code_is_analysed_into_benchmark_events(self) -> None:
        service, labels, analyzer, sink, files = self._service()
        analyzer.answers["/corpus/_benchmarks/owasp-benchmark"] = analysis(4)

        result = service.execute(LoadBenchmarkCommand("owasp-benchmark", Path("/data/owasp")))

        assert (result.labels_loaded, result.findings_total, result.events_sent) == (2, 4, 1)
        assert len(labels.stored["owasp-benchmark"]) == 2
        assert files.copied == ["owasp-benchmark"]
        event = sink.events[0]
        assert event["event_type"] == "benchmark_analysis"
        assert event["payload"]["benchmark"] == "owasp-benchmark"  # type: ignore[index]
        assert event["project_key"] == project_key("k" * 40, "benchmark:owasp-benchmark")

    def test_a_benchmark_without_a_label_reader_is_refused_before_anything_is_touched(self) -> None:
        service, labels, _, sink, files = self._service()

        with pytest.raises(UnknownBenchmarkError):
            service.execute(LoadBenchmarkCommand("cryptoapi-bench", Path("/data/x")))

        assert (labels.stored, files.copied, sink.events) == ({}, [], [])

    @pytest.mark.parametrize("name", ["", "../x", "OWASP", "a b"])
    def test_a_benchmark_code_that_is_not_valid_is_refused(self, name: str) -> None:
        with pytest.raises(UnknownBenchmarkError):
            self._service()[0].execute(LoadBenchmarkCommand(name, Path("/data/x")))

    def test_code_the_analyzer_refuses_still_leaves_the_labels_loaded(self) -> None:
        service, labels, _, sink, _ = self._service()

        result = service.execute(LoadBenchmarkCommand("owasp-benchmark", Path("/data/owasp")))

        assert (result.labels_loaded, result.events_sent) == (2, 0)
        assert result.analysis == "unsupported"  # said out loud: the facade turns it into a non-zero exit
        assert "owasp-benchmark" in labels.stored
        assert sink.events == []

    def test_the_facade_makes_an_unanalysed_benchmark_an_error_not_a_quiet_zero(self) -> None:
        from quancrypt_data.facade.corpus_facade import BenchmarkNotAnalysedError, CorpusFacade
        from quancrypt_data.port.inbound.corpus import LoadBenchmarkResult

        class Refused:
            def execute(self, command: LoadBenchmarkCommand) -> LoadBenchmarkResult:
                return LoadBenchmarkResult(5, "failed", 0, 0, 0, 0, 0, 0)

        facade = CorpusFacade(None, None, None, Refused(), None)  # type: ignore[arg-type]

        with pytest.raises(BenchmarkNotAnalysedError, match="5 labels were loaded.*failed"):
            facade.load_benchmark("owasp-benchmark", "/data/owasp")


class TestReport:
    def test_the_report_counts_what_the_manifest_says_and_names_the_unverified_licenses(self) -> None:
        listing = FakeListing([repo(n) for n in "abcde"])
        manifest = FakeManifest()
        manifest.entries = {
            repo("a").canonical: ManifestEntry(
                repo("a").url, CloneStatus.CLONED, analysis_status=AnalysisStatus.ANALYZED, findings_total=7
            ),
            repo("b").canonical: ManifestEntry(
                repo("b").url, CloneStatus.CLONED, analysis_status=AnalysisStatus.FAILED
            ),
            repo("c").canonical: ManifestEntry(
                repo("c").url, CloneStatus.CLONED, analysis_status=AnalysisStatus.UNSUPPORTED
            ),
            repo("d").canonical: ManifestEntry(repo("d").url, CloneStatus.EXCLUDED, ExclusionReason.LICENSE_UNVERIFIED),
            repo("e").canonical: ManifestEntry(repo("e").url, CloneStatus.FAILED, ExclusionReason.CLONE_FAILED),
        }
        writer = FakeWriter()

        result = ReportCorpusService(listing, manifest, writer, Clock()).execute()

        assert (result.listed, result.analyzed) == (5, 1)
        text = writer.text
        assert "| Listedeki proje (`corpus_projects.csv`) | 5 |" in text
        assert "| Denenen (klonlama denendi) | 5 |" in text
        assert "| Analiz edilen | 1 |" in text
        assert "| Toplam bulgu (analiz edilenlerde) | 7 |" in text
        assert "| license-unverified | 1 |" in text
        assert repo("d").url in text
        assert "KARŞILANMADI" in text  # one analysed project is far below the minimum of 50

    def test_writing_the_report_twice_gives_the_same_text(self) -> None:
        manifest = FakeManifest()
        writer = FakeWriter()
        service = ReportCorpusService(FakeListing([repo("a")]), manifest, writer, Clock())

        service.execute()
        first = writer.text
        service.execute()

        assert writer.text == first

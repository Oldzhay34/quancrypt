"""The real adapters of the corpus ports (P6.2): git, the corpus root on disk, CSV stores, the dataset reader and the two HTTP
clients (against fake servers; no network)."""

from __future__ import annotations

import csv
import os
import subprocess
from pathlib import Path

import httpx
import pytest
import respx

from quancrypt_data.domain.corpus import (
    AnalysisStatus,
    Candidate,
    CloneStatus,
    ExclusionReason,
    ManifestEntry,
    RepoRef,
    SelectedProject,
)
from quancrypt_data.infrastructure.corpus.corpus_files import LocalCorpusFiles
from quancrypt_data.infrastructure.corpus.csv_stores import (
    LIST_COLUMNS,
    MANIFEST_COLUMNS,
    CsvCorpusListStore,
    CsvManifestStore,
    MarkdownReportWriter,
)
from quancrypt_data.infrastructure.corpus.git_repository import SubprocessGitRepository
from quancrypt_data.infrastructure.corpus.hasher import HmacProjectKeyHasher
from quancrypt_data.infrastructure.corpus.http_clients import HttpCodeAnalyzer, HttpEventSink, new_client
from quancrypt_data.infrastructure.corpus.msr_dataset_reader import ColumnMap, CsvMsrDatasetReader
from quancrypt_data.port.outbound.corpus import (
    AnalysisFailedError,
    AnalysisUnsupportedError,
    CloneError,
    DatasetError,
    EventDeliveryError,
)

TOKEN = "t" * 40


def git(*args: str, cwd: Path, env: dict[str, str] | None = None) -> None:
    base = {
        "PATH": os.environ["PATH"],
        "HOME": str(cwd),
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.invalid",
    }
    subprocess.run(["git", *args], cwd=cwd, env={**base, **(env or {})}, check=True, capture_output=True)  # noqa: S603, S607


@pytest.fixture
def origin(tmp_path: Path) -> Path:
    """A small repository with one commit: a file, a symbolic link and a service directory."""
    path = tmp_path / "origin"
    path.mkdir()
    git("init", "-q", "-b", "main", cwd=path)
    (path / "README.md").write_text("hello", encoding="utf-8")
    (path / "svc").mkdir()
    (path / "svc" / "pom.xml").write_text("<project/>", encoding="utf-8")
    os.symlink("/etc/passwd", path / "link")
    git("add", "-A", cwd=path)
    git("commit", "-q", "-m", "first", cwd=path)
    return path


class TestGit:
    def test_a_clone_is_shallow_and_reports_its_commit_and_branch(self, tmp_path: Path, origin: Path) -> None:
        corpus = tmp_path / "corpus"
        adapter = SubprocessGitRepository(corpus, 60, allowed_protocol="file")

        result = adapter.clone_url(origin.as_uri(), "acme__shop")

        head = subprocess.run(  # noqa: S603
            ["git", "-C", str(origin), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,  # noqa: S607
        ).stdout.strip()
        assert (result.commit_sha, result.default_branch) == (head, "main")
        assert (corpus / "acme__shop" / "README.md").read_text(encoding="utf-8") == "hello"
        assert (corpus / "acme__shop" / ".git" / "shallow").exists()

    def test_a_symbolic_link_of_the_repository_is_checked_out_as_a_plain_file(
        self, tmp_path: Path, origin: Path
    ) -> None:
        adapter = SubprocessGitRepository(tmp_path / "corpus", 60, allowed_protocol="file")

        adapter.clone_url(origin.as_uri(), "acme__shop")

        link = tmp_path / "corpus" / "acme__shop" / "link"
        assert link.is_file() and not link.is_symlink()

    def test_no_hook_of_any_configuration_runs_and_no_sample_hook_is_copied(self, tmp_path: Path, origin: Path) -> None:
        # A template directory with a post-checkout hook that leaves a marker, named in the user's git configuration: a plain
        # `git clone` runs it (the control), the adapter must not.
        template = tmp_path / "template"
        (template / "hooks").mkdir(parents=True)
        marker = tmp_path / "marker"
        hook = template / "hooks" / "post-checkout"
        hook.write_text(f"#!/bin/sh\ntouch {marker}\n", encoding="utf-8")
        hook.chmod(0o755)
        home = tmp_path / "home"
        home.mkdir()
        (home / ".gitconfig").write_text(
            f'[init]\n\ttemplateDir = {template}\n[protocol "file"]\n\tallow = always\n', encoding="utf-8"
        )
        environment = {"HOME": str(home), "GIT_CONFIG_GLOBAL": str(home / ".gitconfig")}

        git("clone", "-q", origin.as_uri(), str(tmp_path / "control"), cwd=tmp_path, env=environment)
        assert marker.exists(), "the control clone did not run the hook, so this test would prove nothing"
        marker.unlink()

        previous = {k: os.environ.get(k) for k in environment}
        os.environ.update(environment)
        try:
            SubprocessGitRepository(tmp_path / "corpus", 60, allowed_protocol="file").clone_url(
                origin.as_uri(), "acme__shop"
            )
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        assert not marker.exists()
        hooks = tmp_path / "corpus" / "acme__shop" / ".git" / "hooks"
        assert not hooks.exists() or list(hooks.iterdir()) == []

    def test_only_the_allowed_transport_is_used(self, tmp_path: Path, origin: Path) -> None:
        adapter = SubprocessGitRepository(tmp_path / "corpus", 60)  # https only

        with pytest.raises(CloneError):
            adapter.clone_url(origin.as_uri(), "acme__shop")

        assert not (tmp_path / "corpus" / "acme__shop").exists()

    def test_a_failed_clone_leaves_nothing_behind_and_says_nothing_about_the_address(self, tmp_path: Path) -> None:
        adapter = SubprocessGitRepository(tmp_path / "corpus", 60, allowed_protocol="file")
        missing = (tmp_path / "does-not-exist-secret-name").as_uri()

        with pytest.raises(CloneError) as raised:
            adapter.clone_url(missing, "acme__shop")

        assert "secret-name" not in str(raised.value)
        assert not (tmp_path / "corpus" / "acme__shop").exists()

    def test_a_clone_larger_than_the_limit_of_one_clone_is_removed_and_refused(
        self, tmp_path: Path, origin: Path
    ) -> None:
        adapter = SubprocessGitRepository(tmp_path / "corpus", 60, allowed_protocol="file", max_clone_bytes=1)

        with pytest.raises(CloneError):
            adapter.clone_url(origin.as_uri(), "acme__shop")

        assert not (tmp_path / "corpus" / "acme__shop").exists()

    def test_an_existing_target_is_never_overwritten(self, tmp_path: Path, origin: Path) -> None:
        corpus = tmp_path / "corpus"
        (corpus / "acme__shop").mkdir(parents=True)
        (corpus / "acme__shop" / "mine").write_text("keep", encoding="utf-8")

        with pytest.raises(CloneError):
            SubprocessGitRepository(corpus, 60, allowed_protocol="file").clone_url(origin.as_uri(), "acme__shop")

        assert (corpus / "acme__shop" / "mine").read_text(encoding="utf-8") == "keep"


LICENSE_TEXT = "MIT text"


def build(root: Path, name: str = "acme__shop") -> Path:
    project = root / name
    for service in ("a", "b", "c"):
        (project / service).mkdir(parents=True)
        (project / service / "pom.xml").write_text("<project><artifactId>x</artifactId></project>", encoding="utf-8")
    (project / "pom.xml").write_text("<project><parent>spring-boot-starter-parent</parent></project>", encoding="utf-8")
    (project / "LICENSE").write_text(LICENSE_TEXT, encoding="utf-8")
    return project


class TestCorpusFiles:
    def test_the_license_is_read_by_any_of_the_usual_names(self, tmp_path: Path) -> None:
        project = build(tmp_path)
        (project / "LICENSE").rename(project / "License.md")

        assert LocalCorpusFiles(tmp_path).read_license("acme__shop") == LICENSE_TEXT

    def test_no_license_file_is_none_and_a_linked_one_is_not_followed(self, tmp_path: Path) -> None:
        project = build(tmp_path)
        (project / "LICENSE").unlink()
        outside = tmp_path / "outside.txt"
        outside.write_text("secret", encoding="utf-8")
        os.symlink(outside, project / "LICENSE")

        assert LocalCorpusFiles(tmp_path).read_license("acme__shop") is None

    def test_spring_boot_is_found_in_the_root_or_in_a_service_build_file(self, tmp_path: Path) -> None:
        project = build(tmp_path)
        files = LocalCorpusFiles(tmp_path)
        assert files.has_spring_boot("acme__shop")

        (project / "pom.xml").write_text("<project/>", encoding="utf-8")
        assert not files.has_spring_boot("acme__shop")

        (project / "b" / "pom.xml").write_text(
            "<dependency>org.springframework.boot:spring-boot-starter-web", encoding="utf-8"
        )
        assert files.has_spring_boot("acme__shop")

    def test_service_directories_hold_a_build_file_and_skip_sources_and_build_output(self, tmp_path: Path) -> None:
        project = build(tmp_path)
        for skipped in ("src", "target", "build", "node_modules", ".git", ".idea"):
            (project / skipped / "inner").mkdir(parents=True)
            (project / skipped / "inner" / "pom.xml").write_text("<project/>", encoding="utf-8")
            (project / skipped / "pom.xml").write_text("<project/>", encoding="utf-8")
        (project / "docs").mkdir()  # no build file
        (project / "group" / "deep").mkdir(parents=True)
        (project / "group" / "deep" / "build.gradle.kts").write_text("", encoding="utf-8")
        (project / "group" / "deep" / "x" / "y").mkdir(parents=True)
        (project / "group" / "deep" / "x" / "y" / "pom.xml").write_text("<project/>", encoding="utf-8")
        files = LocalCorpusFiles(tmp_path)

        found = files.service_directories("acme__shop", 2, 20)

        assert found == [
            "a",
            "b",
            "c",
            "group/deep",
        ]  # depth 3 (group/deep/x) is out of reach, src/target/... are skipped
        assert files.service_directories("acme__shop", 2, 2) == ["a", "b"]

    def test_the_size_counts_what_is_in_the_root_but_not_what_links_point_to(self, tmp_path: Path) -> None:
        root = tmp_path / "corpus"
        project = build(root)
        files = LocalCorpusFiles(root)
        before = files.size_bytes()
        big = tmp_path / "big.bin"  # outside the corpus root
        big.write_bytes(b"x" * 100_000)
        os.symlink(big, project / "link")

        assert files.size_bytes() - before < 1000
        (project / "data").write_bytes(b"y" * 5000)
        assert files.size_bytes() - before >= 5000

    def test_remove_deletes_only_a_clone_of_the_corpus_root(self, tmp_path: Path) -> None:
        build(tmp_path)
        outside = tmp_path.parent / f"{tmp_path.name}-outside"
        outside.mkdir()
        files = LocalCorpusFiles(tmp_path)

        files.remove("acme__shop")

        assert not files.exists("acme__shop")
        for bad in ("../x", "acme", "a/b", "ACME__shop", "x__../y", "_benchmarks", str(outside)):
            with pytest.raises(ValueError, match="not a directory of the corpus root"):
                files.remove(bad)
        assert outside.exists()

    def test_a_benchmark_is_copied_below_the_benchmarks_directory_without_its_git_data(self, tmp_path: Path) -> None:
        source = tmp_path / "download"
        (source / "src").mkdir(parents=True)
        (source / "src" / "A.java").write_text("class A {}", encoding="utf-8")
        (source / ".git").mkdir()
        (source / ".git" / "config").write_text("x", encoding="utf-8")
        root = tmp_path / "corpus"
        root.mkdir()
        files = LocalCorpusFiles(root)

        name = files.copy_benchmark(source, "owasp-benchmark")
        again = files.copy_benchmark(source, "owasp-benchmark")  # a second load replaces the copy

        assert name == again == "_benchmarks/owasp-benchmark"
        assert (root / "_benchmarks" / "owasp-benchmark" / "src" / "A.java").exists()
        assert not (root / "_benchmarks" / "owasp-benchmark" / ".git").exists()
        assert files.exists(name)
        with pytest.raises(ValueError, match="not valid"):
            files.copy_benchmark(source, "../escape")


def repo(name: str) -> RepoRef:
    return RepoRef.parse(f"https://github.com/acme/{name}")


class TestCsvStores:
    def test_the_list_has_exactly_the_four_columns_of_the_task_and_reads_back_in_order(self, tmp_path: Path) -> None:
        store = CsvCorpusListStore(tmp_path / "reference" / "corpus_projects.csv")
        projects = [
            SelectedProject(Candidate(repo("b"), "main", "MIT", "Java", 4), "java; services>=3; license MIT"),
            SelectedProject(Candidate(repo("a"), None, None, None, None), "to verify, with a comma"),
        ]

        store.write(projects)

        with (tmp_path / "reference" / "corpus_projects.csv").open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        assert tuple(rows[0]) == LIST_COLUMNS == ("repo_url", "default_branch", "license_spdx", "selection_reason")
        assert rows[1]["selection_reason"] == "to verify, with a comma"
        assert [r.name for r in store.read()] == ["b", "a"]

    def test_a_missing_list_is_empty_and_a_bad_row_is_skipped(self, tmp_path: Path) -> None:
        path = tmp_path / "list.csv"
        store = CsvCorpusListStore(path)
        assert store.read() == []

        path.write_text(
            "repo_url,default_branch,license_spdx,selection_reason\nnot a url,,,\nhttps://github.com/a/ok,,,\n",
            encoding="utf-8",
        )

        assert [r.name for r in store.read()] == ["ok"]

    def test_the_manifest_round_trips_every_field_and_is_sorted(self, tmp_path: Path) -> None:
        store = CsvManifestStore(tmp_path / "reports" / "corpus_manifest.csv")
        entries = {
            repo("b").canonical: ManifestEntry(repo("b").url),
            repo("a").canonical: ManifestEntry(
                repo("a").url,
                CloneStatus.CLONED,
                None,
                "f" * 40,
                "Apache-2.0",
                AnalysisStatus.ANALYZED,
                12,
                3,
                "2026-10-28T09:30:00Z",
            ),
            repo("c").canonical: ManifestEntry(repo("c").url, CloneStatus.EXCLUDED, ExclusionReason.NO_SPRING_BOOT),
        }

        store.save(entries)
        loaded = store.load()

        assert loaded == entries
        header = (tmp_path / "reports" / "corpus_manifest.csv").read_text(encoding="utf-8").splitlines()[0]
        assert header.split(",") == list(MANIFEST_COLUMNS)

    def test_a_row_that_does_not_parse_is_skipped_not_fatal(self, tmp_path: Path) -> None:
        path = tmp_path / "m.csv"
        path.write_text(
            ",".join(MANIFEST_COLUMNS) + "\nhttps://github.com/a/x,bogus,,,,pending,0,0,\n", encoding="utf-8"
        )

        assert CsvManifestStore(path).load() == {}

    def test_the_files_are_written_atomically_without_leaving_temporary_files(self, tmp_path: Path) -> None:
        MarkdownReportWriter(tmp_path / "r" / "corpus_run.md").write("# x\n")
        CsvManifestStore(tmp_path / "r" / "corpus_manifest.csv").save({})

        assert sorted(p.name for p in (tmp_path / "r").iterdir()) == ["corpus_manifest.csv", "corpus_run.md"]


class TestDatasetReader:
    def _write(self, path: Path, header: str, *rows: str) -> Path:
        path.write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")
        return path

    def test_candidates_are_read_with_what_the_dataset_says_and_nothing_more(self, tmp_path: Path) -> None:
        path = self._write(
            tmp_path / "d.csv",
            "url,lang,services,lic",
            "https://github.com/acme/shop,Java,5,MIT",
            "https://github.com/acme/other,,,",
            "https://gitlab.com/acme/elsewhere,Java,5,MIT",
            "not-a-url,Java,5,MIT",
        )
        reader = CsvMsrDatasetReader(
            ColumnMap(repo_url="url", language="lang", service_count="services", license_spdx="lic")
        )

        candidates = reader.read(path)

        assert [c.repo.name for c in candidates] == ["shop", "other"]
        assert (candidates[0].language, candidates[0].service_count, candidates[0].license_spdx) == ("Java", 5, "MIT")
        assert (candidates[1].language, candidates[1].service_count, candidates[1].license_spdx) == (None, None, None)

    def test_a_missing_column_is_an_error_that_lists_the_header_and_guesses_nothing(self, tmp_path: Path) -> None:
        path = self._write(tmp_path / "d.csv", "repository,language", "https://github.com/a/b,Java")

        with pytest.raises(DatasetError, match="repo_url.*repository, language"):
            CsvMsrDatasetReader().read(path)

    def test_an_unreadable_file_is_an_error_without_the_path(self, tmp_path: Path) -> None:
        with pytest.raises(DatasetError) as raised:
            CsvMsrDatasetReader().read(tmp_path / "secret-missing.csv")

        assert "secret-missing" not in str(raised.value)

    def test_a_byte_order_mark_does_not_hide_the_first_column(self, tmp_path: Path) -> None:
        path = tmp_path / "d.csv"
        path.write_bytes(b"\xef\xbb\xbfrepo_url\nhttps://github.com/a/b\n")

        assert [c.repo.name for c in CsvMsrDatasetReader().read(path)] == ["b"]


class TestHasher:
    def test_a_salt_that_is_short_or_the_placeholder_is_refused_and_never_printed(self) -> None:
        for bad in ("short", "CHANGE_ME" + "x" * 40):
            with pytest.raises(ValueError, match="salt"):
                HmacProjectKeyHasher(bad)
        assert "x" * 40 not in repr(HmacProjectKeyHasher("x" * 40))

    def test_the_key_is_64_lower_case_hex_digits_and_stable(self) -> None:
        hasher = HmacProjectKeyHasher("s" * 40)

        key = hasher.key_for("https://github.com/acme/shop")

        assert len(key) == 64 and set(key) <= set("0123456789abcdef")
        assert key == hasher.key_for("https://github.com/acme/shop")


ANALYZER = "http://127.0.0.1:8082"
INGEST = "http://127.0.0.1:8084/api/v1/events"


def analysis_body(findings: list[dict[str, object]] | None = None) -> dict[str, object]:
    sample = {
        "file": "src/A.java",
        "line_start": 3,
        "line_end": 3,
        "raw_name": "SHA1withRSA",
        "symbol": "A#sign",
        "algorithm_family": "RSA",
        "mode": None,
        "padding": None,
        "hash": "SHA-1",
        "key_size_bits": 2048,
        "usage_context": "SIGNATURE",
        "location_kind": "CODE",
        "priority": "P0",
        "library": "JCA",
        "confidence": 0.9,
        "detector_id": "java.jca",
    }
    return {
        "analysis_id": "00000000-0000-4000-8000-000000000001",
        "project_type": "MAVEN",
        "runtime": {"java_version": "21", "spring_boot_version": "3.3.1"},
        "findings": [sample] if findings is None else findings,
        "cbom": {"bomFormat": "CycloneDX", "specVersion": "1.6"},
        "stats": {"files_scanned": 40, "findings_total": 1, "duration_ms": 1200},
    }


def analyzer(sleeps: list[float] | None = None, attempts: int = 3) -> HttpCodeAnalyzer:
    record = sleeps if sleeps is not None else []
    return HttpCodeAnalyzer(ANALYZER, new_client(5, TOKEN), sleep=record.append, attempts=attempts)


class TestHttpCodeAnalyzer:
    @respx.mock
    def test_an_analysis_is_read_into_the_unit_and_sent_with_the_token_and_the_root(self) -> None:
        route = respx.post(f"{ANALYZER}/api/v1/analyses").mock(return_value=httpx.Response(200, json=analysis_body()))

        unit = analyzer().analyze("/corpus/acme__shop")

        request = route.calls.last.request
        assert request.headers["X-Internal-Token"] == TOKEN
        assert request.content == b'{"root":"/corpus/acme__shop","include_tests":true}'
        assert (unit.unit, unit.runtime.java_version, unit.stats.files_scanned) == (".", "21", 40)
        finding = unit.findings[0]
        assert (finding.file, finding.priority, finding.hash, finding.mode) == ("src/A.java", "P0", "SHA-1", None)
        assert not hasattr(finding, "symbol")

    @respx.mock
    def test_422_is_unsupported_not_a_failure(self) -> None:
        respx.post(f"{ANALYZER}/api/v1/analyses").mock(return_value=httpx.Response(422, json={"type": "x"}))

        with pytest.raises(AnalysisUnsupportedError):
            analyzer().analyze("/corpus/acme__shop")

    @respx.mock
    @pytest.mark.parametrize("status", [400, 401, 404, 500, 504])
    def test_any_other_status_is_a_failure_that_names_the_status_only(self, status: int) -> None:
        respx.post(f"{ANALYZER}/api/v1/analyses").mock(return_value=httpx.Response(status, text="secret body"))

        with pytest.raises(AnalysisFailedError, match=str(status)) as raised:
            analyzer().analyze("/corpus/acme__shop")

        assert "secret body" not in str(raised.value)

    @respx.mock
    def test_a_connection_error_is_tried_again_with_growing_pauses_and_then_fails(self) -> None:
        route = respx.post(f"{ANALYZER}/api/v1/analyses").mock(side_effect=httpx.ConnectError("refused"))
        sleeps: list[float] = []

        with pytest.raises(AnalysisFailedError, match="ConnectError"):
            analyzer(sleeps).analyze("/corpus/acme__shop")

        assert route.call_count == 3
        assert sleeps == [1.0, 2.0]

    @respx.mock
    def test_a_503_is_tried_again_and_a_later_answer_is_used(self) -> None:
        respx.post(f"{ANALYZER}/api/v1/analyses").mock(
            side_effect=[httpx.Response(503), httpx.Response(200, json=analysis_body())]
        )

        assert analyzer().analyze("/corpus/acme__shop").stats.files_scanned == 40

    @respx.mock
    def test_a_timeout_is_not_tried_again(self) -> None:
        route = respx.post(f"{ANALYZER}/api/v1/analyses").mock(side_effect=httpx.ReadTimeout("slow"))

        with pytest.raises(AnalysisFailedError, match="ReadTimeout"):
            analyzer().analyze("/corpus/acme__shop")

        assert route.call_count == 1

    @respx.mock
    @pytest.mark.parametrize("body", [[], {"findings": "x"}, {"findings": [1]}, {"findings": [{"file": "a"}]}])
    def test_an_answer_of_an_unexpected_shape_is_a_failure(self, body: object) -> None:
        respx.post(f"{ANALYZER}/api/v1/analyses").mock(return_value=httpx.Response(200, json=body))

        with pytest.raises(AnalysisFailedError):
            analyzer().analyze("/corpus/acme__shop")

    @respx.mock
    def test_a_redirect_is_not_followed(self) -> None:
        respx.post(f"{ANALYZER}/api/v1/analyses").mock(
            return_value=httpx.Response(302, headers={"Location": "http://evil.example/steal"})
        )

        with pytest.raises(AnalysisFailedError, match="302"):
            analyzer().analyze("/corpus/acme__shop")

    @respx.mock
    def test_the_topology_is_summarised_by_counts_without_names_or_findings(self) -> None:
        body = {
            "nodes": [
                {"id": "n1", "name": "secret-service"},
                {"id": "n2", "name": "other"},
                {"id": "n3", "name": "db"},
            ],
            "edges": [
                {"protocol": "HTTP", "tls": True, "mtls": True},
                {"protocol": "HTTP", "tls": False, "mtls": False},
                {"protocol": "MQTT", "tls": True, "mtls": False},
                {"protocol": "SOMETHING", "tls": False, "mtls": False},
            ],
        }
        respx.post(f"{ANALYZER}/api/v1/topologies").mock(return_value=httpx.Response(200, json=body))

        summary = analyzer().topology("/corpus/acme__shop")

        assert summary is not None
        assert (summary.node_count, summary.edge_count, summary.tls_edge_count, summary.mtls_edge_count) == (3, 4, 2, 1)
        assert dict(summary.protocol_counts) == {"HTTP": 2, "GRPC": 0, "MQTT": 1, "AMQP": 0, "KAFKA": 0, "OTHER": 1}
        assert "secret-service" not in str(summary)

    @respx.mock
    def test_a_root_the_analyzer_cannot_build_a_topology_for_has_none(self) -> None:
        respx.post(f"{ANALYZER}/api/v1/topologies").mock(return_value=httpx.Response(422))

        assert analyzer().topology("/corpus/acme__shop") is None


def sink(sleeps: list[float] | None = None, attempts: int = 5) -> HttpEventSink:
    record = sleeps if sleeps is not None else []
    return HttpEventSink(INGEST, new_client(5, TOKEN), sleep=record.append, attempts=attempts)


class TestHttpEventSink:
    @respx.mock
    def test_the_events_go_as_one_array_with_the_token_and_the_counts_come_back(self) -> None:
        route = respx.post(INGEST).mock(
            return_value=httpx.Response(
                200,
                json={
                    "received": 2,
                    "accepted": 1,
                    "duplicate": 1,
                    "quarantined": 0,
                    "consent_revoked": 0,
                    "superseded": 0,
                },
            )
        )

        result = sink().send([{"event_id": "1"}, {"event_id": "2"}])

        request = route.calls.last.request
        assert request.headers["X-Internal-Token"] == TOKEN
        assert request.content == b'[{"event_id":"1"},{"event_id":"2"}]'
        assert (result.accepted, result.duplicate, result.quarantined) == (1, 1, 0)

    @respx.mock
    def test_an_overloaded_ingest_api_is_waited_for_and_asked_again(self) -> None:
        route = respx.post(INGEST).mock(
            side_effect=[httpx.Response(503), httpx.Response(503), httpx.Response(200, json={"accepted": 1})]
        )
        sleeps: list[float] = []

        result = sink(sleeps).send([{"event_id": "1"}])

        assert (route.call_count, result.accepted, sleeps) == (3, 1, [1.0, 2.0])

    @respx.mock
    @pytest.mark.parametrize("status", [400, 401, 500])
    def test_a_refusal_is_a_delivery_error_that_names_the_status_only(self, status: int) -> None:
        respx.post(INGEST).mock(return_value=httpx.Response(status, text="secret body"))

        with pytest.raises(EventDeliveryError, match=str(status)) as raised:
            sink().send([{"event_id": "1"}])

        assert "secret body" not in str(raised.value)

    @respx.mock
    def test_an_unreachable_ingest_api_is_a_delivery_error(self) -> None:
        respx.post(INGEST).mock(side_effect=httpx.ConnectError("refused"))

        with pytest.raises(EventDeliveryError, match="ConnectError"):
            sink(attempts=2).send([{"event_id": "1"}])

    @respx.mock
    def test_an_answer_that_is_not_json_is_a_delivery_error(self) -> None:
        respx.post(INGEST).mock(return_value=httpx.Response(200, text="<html>"))

        with pytest.raises(EventDeliveryError, match="invalid JSON"):
            sink().send([{"event_id": "1"}])


def test_the_clients_ignore_proxy_variables_of_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "http://evil.example:3128")
    monkeypatch.setenv("HTTP_PROXY", "http://evil.example:3128")

    client = new_client(5, TOKEN)

    assert client.trust_env is False
    assert client.follow_redirects is False
    assert client.headers["X-Internal-Token"] == TOKEN

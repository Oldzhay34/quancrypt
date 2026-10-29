"""The corpus events (P6.2): derived ids, chunking, the project key, and what an event never carries."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from quancrypt_data.domain.corpus import RepoRef
from quancrypt_data.domain.corpus_events import (
    BENCHMARK_ANALYSIS,
    CORPUS_ANALYSIS,
    MAX_FINDINGS_PER_EVENT,
    AnalysisStats,
    CorpusFinding,
    Runtime,
    TopologySummary,
    UnitAnalysis,
    benchmark_identifier,
    build_events,
    is_valid_unit,
    project_key,
    repo_identifier,
)
from quancrypt_data.domain.events import MAX_RECORD_NODES, exceeds_record_size
from quancrypt_data.infrastructure.schema.json_schema_catalog import JsonSchemaCatalog
from quancrypt_data.usecase.classification import EventClassifier

SCHEMAS = Path(__file__).resolve().parents[3] / "contracts" / "schemas" / "events"
NOW = datetime(2026, 10, 28, 9, 30, tzinfo=UTC)
KEY = "c" * 64


def finding(index: int = 0, **kwargs: object) -> CorpusFinding:
    fields: dict[str, object] = {
        "file": f"src/main/java/app/C{index}.java",
        "line_start": 10,
        "line_end": 10,
        "raw_name": "SHA1withRSA",
        "algorithm_family": "RSA",
        "usage_context": "SIGNATURE",
        "location_kind": "CODE",
        "priority": "P0",
        "key_size_bits": 2048,
        "mode": None,
        "padding": None,
        "hash": "SHA-1",
        "library": "JCA",
        "confidence": 0.9,
    }
    fields.update(kwargs)
    return CorpusFinding(**fields)  # type: ignore[arg-type]


def unit(count: int = 1, name: str = ".", topology: TopologySummary | None = None) -> UnitAnalysis:
    return UnitAnalysis(
        unit=name,
        runtime=Runtime("21", "3.3.1"),
        findings=tuple(finding(i) for i in range(count)),
        stats=AnalysisStats(40, count, 1200),
        topology=topology,
    )


TOPOLOGY = TopologySummary(3, 2, 1, 0, {"HTTP": 2})


class TestProjectKey:
    def test_it_is_hmac_sha256_of_the_identifier_keyed_with_the_salt(self) -> None:
        # RFC 4231, test case 2: the key is "Jefe" and the data "what do ya want for nothing?".
        assert (
            project_key("Jefe", "what do ya want for nothing?")
            == "5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843"
        )

    def test_a_project_has_one_key_whatever_the_case_of_its_address(self) -> None:
        a = repo_identifier(RepoRef.parse("https://github.com/ACME/Shop"))
        b = repo_identifier(RepoRef.parse("https://github.com/acme/shop"))

        assert project_key("s" * 40, a) == project_key("s" * 40, b)

    def test_a_corpus_project_never_shares_the_key_of_a_user_project_of_the_same_repository(self) -> None:
        # core-service hashes the bare address of a user project (D-129): a consent revocation of that project must not
        # erase the corpus rows of the same public repository (D-301).
        address = "https://github.com/acme/shop"

        assert project_key("s" * 40, repo_identifier(RepoRef.parse(address))) != project_key("s" * 40, address)

    def test_another_salt_or_another_repository_is_another_key(self) -> None:
        assert project_key("a" * 40, "x") != project_key("b" * 40, "x")
        assert project_key("a" * 40, "x") != project_key("a" * 40, "y")

    def test_a_benchmark_is_a_project_of_its_own_name(self) -> None:
        assert benchmark_identifier("owasp-benchmark") == "benchmark:owasp-benchmark"


class TestEvents:
    def test_a_unit_becomes_one_event_that_the_real_schema_accepts(self) -> None:
        catalog = JsonSchemaCatalog(SCHEMAS)

        events = build_events(CORPUS_ANALYSIS, KEY, [unit(2, topology=TOPOLOGY)], NOW)

        assert len(events) == 1
        assert events[0]["occurred_at"] == "2026-10-28T09:30:00Z"
        assert catalog.violations(events[0]) == []
        assert EventClassifier(catalog).classify(0, events[0]).event is not None

    def test_a_benchmark_event_carries_its_code_and_is_accepted_too(self) -> None:
        catalog = JsonSchemaCatalog(SCHEMAS)

        event = build_events(BENCHMARK_ANALYSIS, KEY, [unit()], NOW, benchmark="owasp-benchmark")[0]

        assert event["payload"]["benchmark"] == "owasp-benchmark"  # type: ignore[index]
        assert catalog.violations(event) == []

    def test_a_corpus_event_without_the_benchmark_code_is_not_a_benchmark_event(self) -> None:
        event = build_events(CORPUS_ANALYSIS, KEY, [unit()], NOW)[0]

        assert "benchmark" not in event["payload"]  # type: ignore[operator]

    def test_a_unit_without_findings_is_still_one_event(self) -> None:
        events = build_events(CORPUS_ANALYSIS, KEY, [unit(0)], NOW)

        assert len(events) == 1
        assert events[0]["payload"]["findings"] == []  # type: ignore[index]

    def test_more_findings_than_one_event_holds_are_split_into_ordered_chunks_that_lose_none(self) -> None:
        total = MAX_FINDINGS_PER_EVENT * 2 + 5

        events = build_events(CORPUS_ANALYSIS, KEY, [unit(total, topology=TOPOLOGY)], NOW)

        payloads = [e["payload"] for e in events]
        assert [p["chunk_index"] for p in payloads] == [0, 1, 2]  # type: ignore[index]
        assert {p["chunk_count"] for p in payloads} == {3}  # type: ignore[index]
        sizes = [len(p["findings"]) for p in payloads]  # type: ignore[index]
        assert sum(sizes) == total
        assert max(sizes) == MAX_FINDINGS_PER_EVENT
        # The topology summary rides on the first chunk only.
        assert [p["topology"] is not None for p in payloads] == [True, False, False]  # type: ignore[index]

    def test_a_full_event_stays_below_the_record_limit_of_ingest_api(self) -> None:
        event = build_events(CORPUS_ANALYSIS, KEY, [unit(MAX_FINDINGS_PER_EVENT, topology=TOPOLOGY)], NOW)[0]

        assert not exceeds_record_size(event)
        assert MAX_RECORD_NODES > 0

    def test_the_event_ids_are_derived_so_that_a_second_run_gives_the_same_ids(self) -> None:
        first = build_events(CORPUS_ANALYSIS, KEY, [unit(900), unit(1, "services/a")], NOW)
        again = build_events(CORPUS_ANALYSIS, KEY, [unit(900), unit(1, "services/a")], datetime(2027, 1, 1, tzinfo=UTC))

        assert [e["event_id"] for e in first] == [e["event_id"] for e in again]
        assert len({e["event_id"] for e in first}) == len(first) == 3

    def test_another_project_or_another_event_type_gets_other_ids(self) -> None:
        a = build_events(CORPUS_ANALYSIS, KEY, [unit()], NOW)[0]["event_id"]
        b = build_events(CORPUS_ANALYSIS, "d" * 64, [unit()], NOW)[0]["event_id"]
        c = build_events(BENCHMARK_ANALYSIS, KEY, [unit()], NOW, benchmark="x")[0]["event_id"]

        assert len({a, b, c}) == 3

    def test_an_event_never_carries_an_address_a_local_path_or_a_commit(self) -> None:
        text = json.dumps(build_events(CORPUS_ANALYSIS, KEY, [unit(3, topology=TOPOLOGY)], NOW))

        for forbidden in ("github.com", "/corpus", "/home", "C:\\", "commit", "symbol", "repo_url"):
            assert forbidden not in text


class TestUnits:
    @pytest.mark.parametrize("name", [".", "services", "services/payment-api", "a.b/c_d"])
    def test_a_root_or_one_or_two_plain_segments_is_a_unit(self, name: str) -> None:
        assert is_valid_unit(name)

    @pytest.mark.parametrize("name", ["", "..", "../x", "a/b/c", "a b", "/abs", "a//b", "x/..", "ü", "a/", "-" * 81])
    def test_anything_else_is_not(self, name: str) -> None:
        assert not is_valid_unit(name)

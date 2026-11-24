"""The file, analyzer and location adapters (no database): CSV round trip, the snippet client against a fake analyzer,
the raw-event location rules and the configuration checks."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from quancrypt_ml.domain.labels import CONTEXT_OK, BatchRow, SampledFinding, SourceLocation
from quancrypt_ml.domain.scope import ScopeRecord
from quancrypt_ml.infrastructure.analyzer.snippet_client import AnalyzerSnippetClient
from quancrypt_ml.infrastructure.files.batch_csv import COLUMNS, CsvBatchFiles
from quancrypt_ml.infrastructure.files.text_files import JsonlScopeDatasetFiles
from quancrypt_ml.infrastructure.persistence.locator import clone_dirs, corpus_key, location_in_event, row_id
from quancrypt_ml.infrastructure.settings import ConfigError, load_analyzer, load_database, load_salt
from quancrypt_ml.port.outbound.labeling import AnalyzerUnavailableError, SnippetUnavailableError
from quancrypt_ml.port.outbound.scope import ScopeDatasetError
from tests.support.fakes import candidate

TOKEN = "t" * 40
EVENT = "0b9f2f8e-1c1d-4a2b-9e33-5a6b7c8d9e0f"


def test_the_batch_csv_round_trips_and_defuses_formula_cells(tmp_path: Path) -> None:
    files = CsvBatchFiles()
    row = BatchRow(
        SampledFinding(candidate(1), True),
        SourceLocation("/corpus/a__b", "src/X.java", 12),
        ((11, '=HYPERLINK("x")'), (12, 'Cipher.getInstance("RSA");')),
        CONTEXT_OK,
    )
    path = tmp_path / "batch.csv"
    files.write_batch(path, [row])
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")  # a spreadsheet shows Turkish letters
    rows = files.read_rows(path)
    assert list(rows[0]) == list(COLUMNS)
    assert rows[0]["finding_id"] == candidate(1).finding_id
    assert rows[0]["double_label"] == "true" and rows[0]["line"] == "12"
    assert rows[0]["context"].splitlines()[0] == '11: =HYPERLINK("x")'
    assert rows[0]["label"] == "" and rows[0]["notes"] == ""
    files.write_rows(tmp_path / "f.csv", [{"finding_id": "a", "notes": "-1 puan", "label": "=SUM(A1)"}])
    assert files.read_rows(tmp_path / "f.csv") == [{"finding_id": "a", "notes": "'-1 puan", "label": "'=SUM(A1)"}]


def test_a_csv_saved_with_semicolons_by_a_spreadsheet_is_read(tmp_path: Path) -> None:
    path = tmp_path / "tr.csv"
    path.write_text("finding_id;label;labeler;notes\nabc;HIGH;Olcay K.;not, virgüllü\n", encoding="utf-8-sig")
    assert CsvBatchFiles().read_rows(path) == [
        {"finding_id": "abc", "label": "HIGH", "labeler": "Olcay K.", "notes": "not, virgüllü"}
    ]


def _client(transport: httpx.MockTransport) -> AnalyzerSnippetClient:
    return AnalyzerSnippetClient("http://127.0.0.1:8082", TOKEN, transport=transport)


def test_the_snippet_client_asks_the_analyzer_with_the_token_and_reads_the_lines() -> None:
    seen: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        lines = [{"number": 4, "text": "a"}, {"number": 5, "text": "b"}]
        return httpx.Response(200, json={"path": "src/X.java", "lines": lines})

    lines = _client(httpx.MockTransport(answer)).context(SourceLocation("/corpus/a__b/svc", "src/X.java", 5), 5)
    assert lines == ((4, "a"), (5, "b"))
    assert seen[0].headers["X-Internal-Token"] == TOKEN
    assert dict(seen[0].url.params) == {"root": "/corpus/a__b/svc", "path": "src/X.java", "line": "5", "context": "5"}


@pytest.mark.parametrize("status", [400, 404, 422])
def test_a_location_the_analyzer_refuses_has_no_context(status: int) -> None:
    client = _client(httpx.MockTransport(lambda r: httpx.Response(status, json={"type": "x"})))
    with pytest.raises(SnippetUnavailableError):
        client.context(SourceLocation("/corpus/a", "X.java", 1), 5)


def test_an_analyzer_error_or_outage_stops_the_export() -> None:
    where = SourceLocation("/corpus/a", "X.java", 1)
    with pytest.raises(AnalyzerUnavailableError):
        _client(httpx.MockTransport(lambda r: httpx.Response(500))).context(where, 5)

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(AnalyzerUnavailableError):
        _client(httpx.MockTransport(refuse)).context(where, 5)
    with pytest.raises(AnalyzerUnavailableError):
        _client(httpx.MockTransport(lambda r: httpx.Response(200, json={"no": 1}))).context(where, 5)


def test_row_ids_and_project_keys_are_the_data_platform_ones() -> None:
    # Pinned with data-platform domain/prep.row_id and domain/corpus_events.project_key (services share no code).
    assert row_id(EVENT, 3) == "9504b21e-12e1-5d0b-a9b7-44798923c76f"
    key = "79e164c79c0ab510175384db145d10de5118edda73c5337d49606f364e9f77dd"
    assert corpus_key("s" * 40, "acme", "shop-service") == key
    assert corpus_key("s" * 40, "ACME", "Shop-Service") == key


def test_the_manifest_maps_project_keys_to_clone_directories(tmp_path: Path) -> None:
    manifest = tmp_path / "corpus_manifest.csv"
    manifest.write_text(
        "repo_url,status\nhttps://github.com/Acme/Shop-Service,analyzed\nnot a url,excluded\n", encoding="utf-8"
    )
    assert clone_dirs("s" * 40, manifest) == {corpus_key("s" * 40, "acme", "shop-service"): "acme__shop-service"}
    assert clone_dirs("s" * 40, tmp_path / "missing.csv") == {}


def test_the_location_comes_from_the_finding_at_its_ordinal_below_its_unit() -> None:
    payload = {
        "analysis_unit": "payment-service",
        "findings": [{"file": "src/A.java", "line_start": 3}, {"file": "src/B.java", "line_start": 9}],
    }
    assert location_in_event(row_id(EVENT, 1), EVENT, payload, "acme__shop") == SourceLocation(
        "/corpus/acme__shop/payment-service", "src/B.java", 9
    )
    root = {"analysis_unit": ".", "findings": [{"file": "certs/a.pem", "line_start": None}]}
    assert location_in_event(row_id(EVENT, 0), EVENT, root, "acme__shop") == SourceLocation(
        "/corpus/acme__shop", "certs/a.pem", None
    )
    assert location_in_event(row_id(EVENT, 5), EVENT, payload, "acme__shop") is None


@pytest.mark.parametrize("path", ["/etc/passwd", "../x/A.java", "src/../A.java", "src\\A.java", "src//A.java", ""])
def test_a_path_that_leaves_the_unit_is_no_location(path: str) -> None:
    payload = {"analysis_unit": ".", "findings": [{"file": path, "line_start": 1}]}
    assert location_in_event(row_id(EVENT, 0), EVENT, payload, "acme__shop") is None
    unit = {"analysis_unit": "../outside", "findings": [{"file": "A.java", "line_start": 1}]}
    assert location_in_event(row_id(EVENT, 0), EVENT, unit, "acme__shop") is None


def test_the_database_configuration_refuses_remote_hosts_and_passwords_in_urls() -> None:
    good = {
        "WAREHOUSE_DB_URL": "postgresql+psycopg://warehouse_db_app@127.0.0.1:5432/warehouse_db",
        "WAREHOUSE_DB_APP_PASSWORD": "p" * 20,
    }
    assert load_database(good).url.endswith("/warehouse_db")
    for key, value in [
        ("WAREHOUSE_DB_URL", "postgresql+psycopg://warehouse_db_app@db.example.com/warehouse_db"),
        ("WAREHOUSE_DB_URL", "postgresql+psycopg://warehouse_db_app:secret@127.0.0.1/warehouse_db"),
        ("WAREHOUSE_DB_URL", "postgresql+psycopg://warehouse_db_migrator@127.0.0.1/warehouse_db"),
        ("WAREHOUSE_DB_URL", "postgresql+psycopg://warehouse_db_app@127.0.0.1/warehouse_db?host=evil"),
        ("WAREHOUSE_DB_APP_PASSWORD", "CHANGE_ME"),
    ]:
        with pytest.raises(ConfigError) as error:
            load_database(good | {key: value})
        assert "secret" not in str(error.value) and "evil" not in str(error.value)


def test_the_analyzer_and_salt_configuration() -> None:
    assert load_analyzer({"INTERNAL_SERVICE_TOKEN": TOKEN}).url == "http://127.0.0.1:8082"
    for url in (
        "http://analyzer-service:8082",
        "https://127.0.0.1:8082",
        "http://u:p@127.0.0.1:8082",
        "http://127.0.0.1:8082/api",
    ):
        with pytest.raises(ConfigError):
            load_analyzer({"INTERNAL_SERVICE_TOKEN": TOKEN, "CORPUS_ANALYZER_URL": url})
    with pytest.raises(ConfigError):
        load_analyzer({"INTERNAL_SERVICE_TOKEN": "short"})
    with pytest.raises(ConfigError):
        load_salt({"QUANCRYPT_ANON_SALT": "CHANGE_ME" * 5})
    assert load_salt({"QUANCRYPT_ANON_SALT": "x" * 40}) == "x" * 40


def test_the_scope_files_round_trip_and_refuse_a_broken_line(tmp_path: Path) -> None:
    files = JsonlScopeDatasetFiles()
    record = ScopeRecord("a", "g", "tr", "Şifreleme nedir?", "IN_SCOPE", "pqc_concepts", "synthetic_reviewed")
    files.write(tmp_path / "s.jsonl", [record])
    assert files.read(tmp_path / "s.jsonl") == [record]
    assert "Şifreleme" in (tmp_path / "s.jsonl").read_text(encoding="utf-8")
    (tmp_path / "bad.jsonl").write_text(json.dumps({"id": "a"}) + "\nnot json\n", encoding="utf-8")
    with pytest.raises(ScopeDatasetError, match="line 1"):
        files.read(tmp_path / "bad.jsonl")

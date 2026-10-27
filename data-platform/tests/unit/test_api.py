from __future__ import annotations

import json
import logging
import traceback
from collections.abc import Sequence

import pytest
from fastapi.testclient import TestClient

from quancrypt_data.api.app import create_app
from quancrypt_data.api.gate import MAX_BODY_BYTES
from quancrypt_data.facade.ingest_facade import BadRequestError, IngestFacade, IngestResultView
from quancrypt_data.port.inbound.ingest_events import IngestEventsCommand, IngestEventsResult, InvalidBatchError

TOKEN = "t" * 40
HEADERS = {"X-Internal-Token": TOKEN}


class RecordingUseCase:
    def __init__(self) -> None:
        self.received: Sequence[object] = ()
        self.error: Exception | None = None

    def execute(self, command: IngestEventsCommand) -> IngestEventsResult:
        if self.error is not None:
            raise self.error
        self.received = command.items
        return IngestEventsResult(
            received=len(command.items),
            accepted=len(command.items),
            duplicate=0,
            quarantined=0,
            consent_revoked=0,
            superseded=0,
        )


class Check:
    name = "database"

    def __init__(self, ready: bool) -> None:
        self.ready = ready

    def is_ready(self) -> bool:
        return self.ready


def client(use_case: RecordingUseCase | None = None, *, ready: bool = True) -> tuple[TestClient, RecordingUseCase]:
    use_case = use_case or RecordingUseCase()
    app = create_app(IngestFacade(use_case), token=TOKEN, checks=[Check(ready)])
    return TestClient(app, raise_server_exceptions=False), use_case


class TestAuthentication:
    def test_a_request_without_the_token_is_refused(self) -> None:
        response = client()[0].post("/api/v1/events", json=[{}])

        assert response.status_code == 401
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json()["type"] == "https://quancrypt.local/problems/unauthorized"

    @pytest.mark.parametrize("token", ["wrong", "", TOKEN + "x", TOKEN[:-1]])
    def test_a_wrong_token_is_refused(self, token: str) -> None:
        assert client()[0].post("/api/v1/events", json=[{}], headers={"X-Internal-Token": token}).status_code == 401

    def test_a_bearer_header_is_not_the_internal_token(self) -> None:
        assert (
            client()[0].post("/api/v1/events", json=[{}], headers={"Authorization": f"Bearer {TOKEN}"}).status_code
            == 401
        )

    def test_the_refusal_carries_a_trace_id(self) -> None:
        response = client()[0].post("/api/v1/events", json=[{}])
        assert len(response.headers["X-Trace-Id"]) == 32

    def test_health_needs_no_token(self) -> None:
        test_client, _ = client()
        assert test_client.get("/health/liveness").json() == {"status": "alive"}
        assert test_client.get("/health/readiness").json() == {"status": "ready"}

    def test_readiness_fails_while_the_database_is_down(self) -> None:
        response = client(ready=False)[0].get("/health/readiness")
        assert response.status_code == 503
        assert response.json() == {"status": "not_ready", "failed": ["database"]}


class TestIngest:
    def test_a_batch_is_handed_to_the_use_case_and_the_counts_come_back(self) -> None:
        test_client, use_case = client()

        response = test_client.post("/api/v1/events", json=[{"a": 1}, {"b": 2}], headers=HEADERS)

        assert response.status_code == 200
        assert response.json() == {
            "received": 2,
            "accepted": 2,
            "duplicate": 0,
            "quarantined": 0,
            "consent_revoked": 0,
            "superseded": 0,
        }
        assert use_case.received == [{"a": 1}, {"b": 2}]

    @pytest.mark.parametrize(
        "body", [b"not json", b'{"a": 1}', b'"text"', b"5", b"null", b"[NaN]", b"[Infinity]", b"[1e999]", b"\xff\xfe"]
    )
    def test_a_body_that_is_not_a_json_array_is_a_400(self, body: bytes) -> None:
        response = client()[0].post("/api/v1/events", content=body, headers=HEADERS)

        assert response.status_code == 400
        assert response.json()["type"] == "https://quancrypt.local/problems/validation-failed"

    def test_an_empty_array_or_too_many_items_is_a_400_from_the_use_case(self) -> None:
        use_case = RecordingUseCase()
        use_case.error = InvalidBatchError("the batch is empty")

        response = client(use_case)[0].post("/api/v1/events", json=[], headers=HEADERS)

        assert response.status_code == 400
        assert response.json()["detail"] == "body: the batch is empty"

    def test_a_declared_length_above_the_limit_is_refused_before_the_body_is_read(self) -> None:
        response = client()[0].post(
            "/api/v1/events", content=b"[]", headers={**HEADERS, "Content-Length": str(MAX_BODY_BYTES + 1)}
        )
        assert response.status_code == 400

    def test_a_body_above_the_limit_is_refused(self) -> None:
        body = json.dumps([{"blob": "x" * MAX_BODY_BYTES}]).encode()
        response = client()[0].post("/api/v1/events", content=body, headers=HEADERS)

        assert response.status_code == 400
        assert response.json()["detail"] == "body: larger than 8 MiB"

    def test_an_unexpected_failure_is_a_500_that_says_nothing_about_the_cause(self) -> None:
        use_case = RecordingUseCase()
        use_case.error = RuntimeError("connection to db failed: password=hunter2")

        response = client(use_case)[0].post("/api/v1/events", json=[{}], headers=HEADERS)

        assert response.status_code == 500
        assert "hunter2" not in response.text
        assert response.json()["type"] == "https://quancrypt.local/problems/internal-error"

    def test_a_trace_id_from_the_client_is_kept_only_when_it_is_32_hex_digits(self) -> None:
        test_client, _ = client()
        good = "0123456789abcdef0123456789abcdef"

        assert test_client.get("/health/liveness", headers={"X-Trace-Id": good}).headers["X-Trace-Id"] == good
        replaced = test_client.get("/health/liveness", headers={"X-Trace-Id": "not hex; \n"}).headers["X-Trace-Id"]
        assert replaced != "not hex; \n"
        assert len(replaced) == 32

    def test_the_interactive_docs_are_off(self) -> None:
        test_client, _ = client()
        assert test_client.get("/docs").status_code == 404
        assert test_client.get("/openapi.json").status_code == 404


class TestFacade:
    def test_the_use_case_refusal_becomes_a_bad_request(self) -> None:
        use_case = RecordingUseCase()
        use_case.error = InvalidBatchError("too many")
        with pytest.raises(BadRequestError, match="too many"):
            IngestFacade(use_case).ingest([{}])

    def test_the_result_is_copied_into_the_view(self) -> None:
        assert IngestFacade(RecordingUseCase()).ingest([{}]) == IngestResultView(1, 1, 0, 0, 0, 0)


class TestProblems:
    def test_an_unknown_path_or_method_is_an_rfc_9457_problem_too(self) -> None:
        test_client, _ = client()

        unknown = test_client.get("/nowhere")
        wrong_method = test_client.get("/api/v1/events", headers=HEADERS)

        assert (unknown.status_code, wrong_method.status_code) == (404, 405)
        assert unknown.headers["content-type"] == "application/problem+json"
        assert unknown.json()["type"] == "https://quancrypt.local/problems/not-found"
        assert wrong_method.json()["type"] == "https://quancrypt.local/problems/method-not-allowed"

    def test_a_start_up_failure_is_logged_as_a_class_name_and_stops_the_service(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        def broken() -> None:
            raise ConnectionError(
                "connection to server at db.internal failed: password authentication failed for hunter2"
            )

        app = create_app(IngestFacade(RecordingUseCase()), token=TOKEN, checks=[], on_startup=broken)

        with (
            caplog.at_level(logging.ERROR),
            pytest.raises(RuntimeError, match="could not start") as raised,
            TestClient(app),
        ):
            pass

        assert "ConnectionError" in caplog.text
        assert "hunter2" not in caplog.text
        assert "hunter2" not in "".join(traceback.format_exception(raised.value))


def test_a_batch_beyond_the_concurrency_limit_gets_503_and_is_not_worked_on() -> None:
    import threading

    from quancrypt_data.api.app import MAX_CONCURRENT_BATCHES

    release = threading.Event()
    entered = threading.Semaphore(0)

    class Blocking(RecordingUseCase):
        def execute(self, command: IngestEventsCommand) -> IngestEventsResult:
            entered.release()
            release.wait(timeout=10)
            return super().execute(command)

    test_client, _ = client(Blocking())
    results: list[int] = []

    def send() -> None:
        results.append(test_client.post("/api/v1/events", json=[{}], headers=HEADERS).status_code)

    threads = [threading.Thread(target=send) for _ in range(MAX_CONCURRENT_BATCHES)]
    for thread in threads:
        thread.start()
    for _ in range(MAX_CONCURRENT_BATCHES):
        assert entered.acquire(timeout=10)

    refused = test_client.post("/api/v1/events", json=[{}], headers=HEADERS)
    release.set()
    for thread in threads:
        thread.join(timeout=10)

    assert refused.status_code == 503
    assert refused.json()["type"].endswith("/overloaded")
    assert results == [200] * MAX_CONCURRENT_BATCHES

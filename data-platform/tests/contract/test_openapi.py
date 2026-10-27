"""contracts/openapi/ingest-api.yaml against the code (contract first, D-17)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from quancrypt_data.api.app import create_app
from quancrypt_data.api.gate import MAX_BODY_BYTES
from quancrypt_data.domain.events import MAX_BATCH_EVENTS
from quancrypt_data.facade.ingest_facade import IngestFacade
from quancrypt_data.port.inbound.ingest_events import IngestEventsCommand, IngestEventsResult

TOKEN = "t" * 40
HEADERS = {"X-Internal-Token": TOKEN}
CONTRACT = Path(__file__).resolve().parents[3] / "contracts" / "openapi" / "ingest-api.yaml"


@pytest.fixture(scope="module")
def contract() -> dict[str, Any]:
    document: dict[str, Any] = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    return document


def validator(contract: dict[str, Any], name: str) -> Draft202012Validator:
    schema = contract["components"]["schemas"][name]
    return Draft202012Validator({**schema, "components": contract["components"]})


class Counting:
    def execute(self, command: IngestEventsCommand) -> IngestEventsResult:
        return IngestEventsResult(len(command.items), len(command.items) - 1, 1, 0, 0, 0)


def test_the_contract_has_the_one_command_and_its_security(contract: dict[str, Any]) -> None:
    assert contract["openapi"].startswith("3.1")
    assert list(contract["paths"]) == ["/api/v1/events"]
    operation = contract["paths"]["/api/v1/events"]["post"]
    assert operation["operationId"] == "IngestEvents"
    assert contract["security"] == [{"internalToken": []}]
    scheme = contract["components"]["securitySchemes"]["internalToken"]
    assert (scheme["in"], scheme["name"]) == ("header", "X-Internal-Token")
    assert set(operation["responses"]) == {"200", "400", "401", "500"}


def test_the_batch_limit_of_the_contract_is_the_domain_limit(contract: dict[str, Any]) -> None:
    batch = contract["components"]["schemas"]["EventBatch"]
    assert (batch["minItems"], batch["maxItems"]) == (1, MAX_BATCH_EVENTS)
    assert "8 MiB" in contract["info"]["description"]
    assert MAX_BODY_BYTES == 8 * 1024 * 1024


def test_the_200_response_matches_the_result_schema(contract: dict[str, Any]) -> None:
    client = TestClient(create_app(IngestFacade(Counting()), token=TOKEN, checks=[]))

    body = client.post("/api/v1/events", json=[{}, {}], headers=HEADERS).json()

    validator(contract, "IngestResult").validate(body)
    assert body == {
        "received": 2,
        "accepted": 1,
        "duplicate": 1,
        "quarantined": 0,
        "consent_revoked": 0,
        "superseded": 0,
    }


def test_the_problem_responses_match_the_problem_schema(contract: dict[str, Any]) -> None:
    client = TestClient(create_app(IngestFacade(Counting()), token=TOKEN, checks=[]))
    unauthorized = client.post("/api/v1/events", json=[{}])
    not_an_array = client.post("/api/v1/events", content=b"{}", headers=HEADERS)

    for response in (unauthorized, not_an_array):
        validator(contract, "Problem").validate(response.json())
        assert response.headers["content-type"] == "application/problem+json"
        assert response.headers["X-Trace-Id"]


def test_the_result_schema_is_closed_and_complete(contract: dict[str, Any]) -> None:
    schema = contract["components"]["schemas"]["IngestResult"]
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])


def test_the_trace_id_parameter_is_the_32_hex_digit_form(contract: dict[str, Any]) -> None:
    assert contract["components"]["parameters"]["TraceId"]["schema"]["pattern"] == "^[0-9a-f]{32}$"

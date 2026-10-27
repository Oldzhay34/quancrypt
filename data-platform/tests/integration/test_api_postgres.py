"""The HTTP application on the real service wiring and database: what a relay's POST does end to end inside this service."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from quancrypt_data.api.app import create_app
from quancrypt_data.infrastructure.persistence.database import DatabaseReadiness
from tests.conftest import Stack
from tests.support.envelopes import KEY_A, KEY_B, PAYLOADS, envelope

pytestmark = pytest.mark.postgres

HEADERS = {"X-Internal-Token": "t" * 40}


@pytest.fixture
def client(stack: Stack) -> Iterator[TestClient]:
    container = stack.container
    app = create_app(
        container.facade,
        token=container.settings.internal_token,
        checks=[DatabaseReadiness(container.database)],
        # The lifespan applies the migrations, as the service does at startup (idempotent: they are already applied).
        on_startup=lambda: container.database.migrate(container.settings.migrations_dir),
    )
    with TestClient(app) as test_client:
        yield test_client


def count(stack: Stack, table: str) -> int:
    with stack.instance.migrator_engine().begin() as connection:
        return int(connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one())


def test_the_service_is_ready_once_the_database_answers(client: TestClient) -> None:
    assert client.get("/health/readiness").json() == {"status": "ready"}


def test_a_relay_batch_of_every_event_type_is_stored_and_counted(client: TestClient, stack: Stack) -> None:
    batch: list[dict[str, Any]] = [envelope(name) for name in PAYLOADS if name != "consent_revoked"]

    response = client.post("/api/v1/events", json=batch, headers=HEADERS)

    assert response.status_code == 200
    assert response.json() == {
        "received": 7,
        "accepted": 7,
        "duplicate": 0,
        "quarantined": 0,
        "consent_revoked": 0,
        "superseded": 0,
    }
    assert count(stack, "raw.event") == 7


def test_the_same_request_sent_again_by_the_relay_changes_nothing(client: TestClient, stack: Stack) -> None:
    batch = [envelope(), envelope("scope_decision")]
    client.post("/api/v1/events", json=batch, headers=HEADERS)

    again = client.post("/api/v1/events", json=batch, headers=HEADERS)

    assert again.json() == {
        "received": 2,
        "accepted": 0,
        "duplicate": 2,
        "quarantined": 0,
        "consent_revoked": 0,
        "superseded": 0,
    }
    assert count(stack, "raw.event") == 2


def test_a_batch_with_a_bad_record_is_answered_200_so_that_the_relay_stops_retrying(
    client: TestClient, stack: Stack
) -> None:
    response = client.post("/api/v1/events", json=[envelope(), {"nonsense": True}], headers=HEADERS)

    assert response.status_code == 200
    assert response.json()["quarantined"] == 1
    assert (count(stack, "raw.event"), count(stack, "quarantine.event")) == (1, 1)


def test_a_revocation_over_http_erases_the_project_and_leaves_the_audit(client: TestClient, stack: Stack) -> None:
    client.post("/api/v1/events", json=[envelope(), envelope(project_key=KEY_B)], headers=HEADERS)

    response = client.post(
        "/api/v1/events",
        json=[envelope("consent_revoked", project_key=KEY_A, occurred_at="2026-10-27T11:00:00Z")],
        headers=HEADERS,
    )

    assert response.json()["consent_revoked"] == 1
    with stack.instance.migrator_engine().begin() as connection:
        keys = [row[0] for row in connection.execute(text("SELECT project_key FROM raw.event"))]
    assert keys == [KEY_B]
    assert count(stack, "ingest.ingest_audit") == 1


def test_a_batch_of_501_events_is_refused_and_nothing_is_written(client: TestClient, stack: Stack) -> None:
    response = client.post("/api/v1/events", json=[envelope() for _ in range(501)], headers=HEADERS)

    assert response.status_code == 400
    assert count(stack, "ingest.ingest_batch") == 0


def test_a_database_failure_is_a_500_and_the_batch_can_be_sent_again(client: TestClient, stack: Stack) -> None:
    batch = [envelope()]
    with stack.instance.migrator_engine().begin() as connection:
        connection.execute(text("ALTER TABLE raw.event RENAME TO event_away"))
    try:
        failed = client.post("/api/v1/events", json=batch, headers=HEADERS)
    finally:
        with stack.instance.migrator_engine().begin() as connection:
            connection.execute(text("ALTER TABLE raw.event_away RENAME TO event"))

    assert failed.status_code == 500
    assert "event_away" not in failed.text
    assert count(stack, "ingest.ingest_batch") == 0
    assert client.post("/api/v1/events", json=batch, headers=HEADERS).json()["accepted"] == 1

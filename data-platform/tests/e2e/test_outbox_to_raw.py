"""End to end (P6.1): core-service API -> core outbox -> relay -> ingest-api -> `warehouse_db.raw` (agent-service does not take part).

It needs the running stack (`make e2e`, see README.md): postgres, core-service and ingest-api, started from a throw-away env
file. The findings and the topology are derived from the approved golden files of QBank (D-123); the relay is triggered through
core-service's own internal endpoint, so no test waits for a timer. A missing variable or an unreachable service fails the test
(it never skips).
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import psycopg
import pytest
import yaml

pytestmark = pytest.mark.e2e

GOLDEN = Path(__file__).resolve().parents[3] / "reference-system" / "expected"
CONSENT = "WAREHOUSE_ANALYTICS"
# The golden file says field_device, core's contract says DEVICE.
NODE_KINDS = {"field_device": "DEVICE"}


def setting(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if not value:
        pytest.fail(f"{name} is not set: run the end-to-end test from the stack described in data-platform/README.md")
    return value


class Stack:
    """The services of the running stack, as the test sees them."""

    def __init__(self) -> None:
        self.core = httpx.Client(
            base_url=setting("E2E_CORE_URL", "http://127.0.0.1:8081"),
            headers={"Authorization": f"Bearer {setting('QUANCRYPT_SESSION_TOKEN')}"},
            timeout=30,
            trust_env=False,
        )
        self.internal = {"X-Internal-Token": setting("INTERNAL_SERVICE_TOKEN")}
        self.db: dict[str, Any] = {
            "host": "127.0.0.1",
            "port": int(setting("E2E_DB_PORT", "5432")),
            "dbname": "warehouse_db",
            "user": "warehouse_db_migrator",
            "password": setting("WAREHOUSE_DB_MIGRATOR_PASSWORD"),
        }

    def post(self, path: str, body: Any = None, **headers: str) -> httpx.Response:
        response = self.core.post(path, json=body, headers=headers)
        assert response.status_code < 300, f"POST {path}: {response.status_code} {response.text[:300]}"
        return response

    def put(self, path: str, body: Any) -> httpx.Response:
        response = self.core.put(path, json=body)
        assert response.status_code < 300, f"PUT {path}: {response.status_code} {response.text[:300]}"
        return response

    def rows(self, sql: str, *params: object) -> list[tuple[Any, ...]]:
        with psycopg.connect(**self.db) as connection, connection.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchall() if cursor.description else []

    def relay(self) -> int:
        """Drains core's outbox into ingest-api; returns how many events were sent."""
        sent = 0
        for _ in range(20):
            # Only the internal token: with an Authorization header present core-service ignores the internal scheme (D-168).
            response = httpx.post(
                f"{self.core.base_url}/api/v1/internal/outbox/relay",
                json={"batchSize": 100},
                headers=self.internal,
                timeout=30,
                trust_env=False,
            )
            assert response.status_code == 200, f"relay: {response.status_code} {response.text[:300]}"
            result = response.json()
            sent += int(result["relayedCount"])
            if result["remainingCount"] == 0:
                return sent
        pytest.fail("core-service's outbox did not drain: is ingest-api reachable from core-service?")


@pytest.fixture(scope="module")
def stack() -> Iterator[Stack]:
    stack = Stack()
    try:
        yield stack
    finally:
        stack.core.close()


def golden_findings() -> list[dict[str, Any]]:
    inventory = yaml.safe_load((GOLDEN / "crypto_inventory.yaml").read_text(encoding="utf-8"))
    return [
        {
            "path": entry["file"],
            "symbol": entry["symbol"],
            "algorithmFamily": entry["algorithm_family"],
            "usageContext": entry["usage_context"],
            "locationKind": entry["location_kind"],
            "priority": entry["priority"],
            "keySizeBits": entry.get("key_size_bits"),
            "confidence": 1.0,
            "classifiedBy": "STATIC",
        }
        for entry in inventory["entries"]
    ]


def golden_topology(finding_ids: list[str]) -> dict[str, Any]:
    topology = yaml.safe_load((GOLDEN / "topology.yaml").read_text(encoding="utf-8"))
    names = {node["id"] for node in topology["nodes"]}

    def protocol(text: str) -> str:
        return "MQTT" if "MQTT" in text.upper() else "HTTP" if "HTTP" in text.upper() else "OTHER"

    links = [
        {
            "source": edge["source"],
            "target": edge["target"],
            "protocol": protocol(edge["protocol"]),
            "tls": bool(edge["tls"]),
            "mtls": bool(edge["tls"] and edge["mtls"]),
            "callSites": [],
            "findingIds": finding_ids[:2] if index == 0 else [],
        }
        for index, edge in enumerate(topology["edges"])
        if edge["source"] in names and edge["target"] in names
    ]
    return {
        "nodes": [
            {"name": node["id"], "nodeKind": NODE_KINDS.get(node["kind"], node["kind"].upper())}
            for node in topology["nodes"]
        ],
        "links": links,
    }


class Project:
    def __init__(self, stack: Stack, *, consent: bool) -> None:
        self.stack = stack
        project = stack.post(
            "/api/v1/projects", {"identity": f"e2e-p61-{uuid.uuid4()}", "displayName": "e2e P6.1"}
        ).json()
        self.id: str = project["id"]
        self.key: str = project["projectKey"]
        self.consent_version: str | None = None
        if consent:
            notice = stack.core.get("/api/v1/privacy-notices/latest").json()
            granted = stack.post(
                f"/api/v1/projects/{self.id}/consents",
                {"consentType": CONSENT, "privacyNoticeVersion": notice["version"]},
            )
            self.consent_version = granted.headers["ETag"]

    def scan(self) -> int:
        """A whole scan of the golden QBank data; returns how many findings core stored."""
        scan_id = self.stack.post(f"/api/v1/projects/{self.id}/scans").json()["id"]
        created = self.stack.post(f"/api/v1/scans/{scan_id}/findings", {"findings": golden_findings()}).json()
        self.stack.put(f"/api/v1/scans/{scan_id}/topology", golden_topology(created["createdIds"]))
        self.stack.post(f"/api/v1/scans/{scan_id}/completion", {"outcome": "COMPLETED"})
        return int(created["createdCount"])

    def revoke(self) -> None:
        assert self.consent_version is not None
        response = self.stack.core.delete(
            f"/api/v1/projects/{self.id}/consents/{CONSENT}", headers={"If-Match": self.consent_version}
        )
        assert response.status_code == 200, response.text

    def raw_types(self) -> dict[str, int]:
        rows = self.stack.rows("SELECT event_type, count(*) FROM raw.event WHERE project_key = %s GROUP BY 1", self.key)
        return {event_type: int(count) for event_type, count in rows}

    def quarantined(self) -> int:
        return int(self.stack.rows("SELECT count(*) FROM quarantine.event WHERE project_key = %s", self.key)[0][0])


def test_the_services_are_up(stack: Stack) -> None:
    ingest = setting("E2E_INGEST_URL", "http://127.0.0.1:8084")
    assert httpx.get(f"{ingest}/health/readiness", timeout=10, trust_env=False).json() == {"status": "ready"}
    assert stack.core.get("/health/readiness").status_code == 200


def test_without_consent_nothing_reaches_raw(stack: Stack) -> None:
    project = Project(stack, consent=False)

    assert project.scan() > 0
    stack.relay()

    # D-21: no consent, no event. The outbox of the project is empty and raw has nothing of it.
    assert project.raw_types() == {}
    assert project.quarantined() == 0


def test_with_consent_the_findings_the_topology_and_the_scan_arrive_in_raw(stack: Stack) -> None:
    project = Project(stack, consent=True)

    created = project.scan()
    assert created > 0
    assert stack.relay() > 0

    types = project.raw_types()
    assert types["finding_detected"] == created
    assert types["topology_recorded"] == 1
    assert types["scan_completed"] == 1
    # Everything core wrote satisfied its own schema: nothing went to the quarantine.
    assert project.quarantined() == 0
    sources = {
        row[0] for row in stack.rows("SELECT DISTINCT source FROM raw.event WHERE project_key = %s", project.key)
    }
    assert sources == {"core-service"}
    # Lineage: every row belongs to a batch and the batch counted what it received.
    assert stack.rows(
        "SELECT count(*) FROM raw.event e LEFT JOIN ingest.ingest_batch b ON b.id = e.batch_id "
        "WHERE e.project_key = %s AND b.id IS NULL",
        project.key,
    ) == [(0,)]


def test_sending_the_same_events_again_adds_nothing(stack: Stack) -> None:
    project = Project(stack, consent=True)
    project.scan()
    stack.relay()
    before = project.raw_types()

    stack.relay()

    assert project.raw_types() == before


def test_revoking_the_consent_erases_the_project_from_raw_and_audits_it(stack: Stack) -> None:
    revoked = Project(stack, consent=True)
    kept = Project(stack, consent=True)
    revoked.scan()
    kept.scan()
    stack.relay()
    assert revoked.raw_types()["finding_detected"] > 0
    kept_before = kept.raw_types()

    revoked.revoke()
    stack.relay()

    assert revoked.raw_types() == {}
    assert revoked.quarantined() == 0
    # Another project is untouched, and the revocation itself is not kept as an event.
    assert kept.raw_types() == kept_before
    audit = stack.rows(
        "SELECT a.action_code, t.table_name, t.deleted_rows FROM ingest.ingest_audit a "
        "JOIN ingest.ingest_audit_table t ON t.audit_id = a.id WHERE a.project_key = %s ORDER BY t.table_name",
        revoked.key,
    )
    assert [(row[0], row[1]) for row in audit] == [
        ("PROJECT_DATA_DELETED", "quarantine.event"),
        ("PROJECT_DATA_DELETED", "raw.event"),
    ]
    assert audit[1][2] > 0

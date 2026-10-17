"""The `scope_decision` outbox event against its contract (D-17): `contracts/schemas/events/scope_decision.json`.

The envelope is built the way the relay (P6.1) will build it: `event_id` = row id, `event_type`, `schema_version`,
`occurred_at` and `project_key` from the columns, `payload` as stored.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from src.memory.memory_store import Database, PostgresConversationMemory, PostgresScopeDecisionLog, utc_now
from src.memory.short_term import ConversationWindow, ScopeDecisionRecord
from tests.support.json_schema_lite import validate
from tests.support.postgres import REPO_ROOT

SCHEMA = json.loads((REPO_ROOT / "contracts" / "schemas" / "events" / "scope_decision.json").read_text("utf-8"))
PROJECT = UUID("00000000-0000-0000-0000-0000000000c1")
KEY = "c" * 64

DECISIONS = [
    ScopeDecisionRecord(None, "ALLOW", 0.91, "SCOPE_CLASSIFIER", 12, "tr"),
    ScopeDecisionRecord(None, "ALLOW", 0.12345, "SCOPE_CLASSIFIER", 7, "en"),
    ScopeDecisionRecord(None, "DENY", None, "RULE_FILTER", 1, "tr"),
    ScopeDecisionRecord(None, "ALLOW", None, "LLM_SELF_CHECK", 900, "en"),
    ScopeDecisionRecord(None, "DENY", None, "FAIL_CLOSED", 2, "tr"),
]


def _envelopes(database: Database) -> list[dict[str, Any]]:
    with database.engine.connect() as connection:
        rows = connection.execute(
            text("SELECT id, event_type, schema_version, occurred_at, project_key, payload FROM outbox_event")
        ).all()
    return [
        {
            "event_id": str(row.id),
            "event_type": row.event_type,
            "schema_version": row.schema_version,
            "occurred_at": row.occurred_at.isoformat(),
            "project_key": row.project_key,
            "payload": row.payload,
        }
        for row in rows
    ]


@pytest.mark.postgres
def test_every_ring_writes_an_event_that_fits_the_contract(database: Database) -> None:
    conversation = PostgresConversationMemory(database, ConversationWindow(12, 3000, 4), utc_now, uuid4)
    session = conversation.create_session(PROJECT, KEY, "tr").session.id
    log = PostgresScopeDecisionLog(database, utc_now, uuid4)

    for decision in DECISIONS:
        log.record(
            ScopeDecisionRecord(
                session,
                decision.decision,
                decision.confidence,
                decision.deciding_ring,
                decision.latency_ms,
                decision.language,
            ),
            warehouse_consent=True,
        )

    envelopes = _envelopes(database)
    assert len(envelopes) == len(DECISIONS)
    for envelope in envelopes:
        assert validate(envelope, SCHEMA) == [], envelope
    classifier = sorted(
        e["payload"]["confidence"] for e in envelopes if e["payload"]["deciding_ring"] == "SCOPE_CLASSIFIER"
    )
    assert classifier == [0.1235, 0.91]  # the stored (rounded) value, 0.9100 -> 0.91
    assert {e["payload"]["confidence"] for e in envelopes if e["payload"]["deciding_ring"] != "SCOPE_CLASSIFIER"} == {
        None
    }
    with database.engine.connect() as connection:
        stored = sorted(
            float(v)
            for (v,) in connection.execute(text("SELECT confidence FROM scope_decision WHERE confidence IS NOT NULL"))
        )
    assert stored == classifier


@pytest.mark.parametrize(
    "payload",
    [
        {"decision": "ALLOW", "confidence": None, "deciding_ring": "SCOPE_CLASSIFIER", "latency_ms": 1, "language": "tr"},  # noqa: E501
        {"decision": "ALLOW", "confidence": 0.5, "deciding_ring": "RULE_FILTER", "latency_ms": 1, "language": "tr"},
        {"decision": "ALLOW", "confidence": None, "deciding_ring": "FAIL_CLOSED", "latency_ms": 1, "language": "tr"},
        {"decision": "DENY", "confidence": 1.5, "deciding_ring": "SCOPE_CLASSIFIER", "latency_ms": 1, "language": "tr"},
        {"decision": "DENY", "confidence": None, "deciding_ring": "RULE_FILTER", "latency_ms": -1, "language": "tr"},
        {"decision": "DENY", "confidence": None, "deciding_ring": "RULE_FILTER", "latency_ms": 1, "language": "de"},
        {
            "decision": "DENY", "confidence": None, "deciding_ring": "RULE_FILTER", "latency_ms": 1, "language": "tr",
            "request_text": "must never be here",
        },
    ],
)  # fmt: skip
def test_the_checker_rejects_payloads_the_contract_forbids(payload: dict[str, Any]) -> None:
    envelope = {
        "event_id": str(uuid4()),
        "event_type": "scope_decision",
        "schema_version": 1,
        "occurred_at": "2026-10-17T10:00:00+00:00",
        "project_key": KEY,
        "payload": payload,
    }

    assert validate(envelope, SCHEMA) != []

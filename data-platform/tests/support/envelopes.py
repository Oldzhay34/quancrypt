"""Valid sample envelopes of every event type, in the shape the outbox relays send them (core-service OutboxJson and
agent-service outbox_relay: event_id, event_type, schema_version, occurred_at, project_key, payload)."""

from __future__ import annotations

import uuid
from typing import Any

KEY_A = "a" * 64
KEY_B = "b" * 64

_ANALYSIS_PAYLOAD: dict[str, Any] = {
    "analysis_unit": ".",
    "chunk_index": 0,
    "chunk_count": 1,
    "runtime": {"java_version": "21", "spring_boot_version": "3.3.1"},
    "findings": [
        {
            "file": "src/main/java/app/Crypto.java",
            "line_start": 12,
            "line_end": 12,
            "raw_name": "RSA/ECB/PKCS1Padding",
            "algorithm_family": "RSA",
            "usage_context": "ENCRYPTION",
            "location_kind": "CODE",
            "priority": "P0",
            "key_size_bits": 1024,
            "mode": "NONE",
            "padding": "PKCS1_V1_5",
            "hash": None,
            "library": "JCA",
            "confidence": 0.9,
        }
    ],
    "topology": {
        "node_count": 3,
        "edge_count": 2,
        "tls_edge_count": 1,
        "mtls_edge_count": 0,
        "protocol_counts": {"HTTP": 2, "GRPC": 0, "MQTT": 0, "AMQP": 0, "KAFKA": 0, "OTHER": 0},
    },
    "stats": {"files_scanned": 40, "findings_total": 1, "duration_ms": 1200},
}

PAYLOADS: dict[str, dict[str, Any]] = {
    "finding_detected": {
        "algorithm_family": "RSA",
        "usage_context": "TLS_KEY_EXCHANGE",
        "location_kind": "CODE",
        "priority": "P1",
        "key_size_bits": 2048,
        "confidence": 0.9,
        "classified_by": "STATIC",
    },
    "topology_recorded": {
        "node_count": 2,
        "link_count": 1,
        "links": [{"protocol": "HTTP", "tls": True, "mtls": False}],
    },
    "scan_completed": {
        "finding_count": 3,
        "priority_counts": {"P0": 1, "P1": 2},
        "java_version": "25",
        "spring_boot_version": None,
        "duration_seconds": 12,
    },
    "plan_created": {
        "item_count": 3,
        "strategy_counts": {"HYBRID_TLS_KEX": 2, "FIX_WEAK_CLASSIC": 1},
        "effort_counts": {"S": 1, "M": 2},
    },
    "plan_item_transitioned": {
        "strategy": "HYBRID_TLS_KEX",
        "effort": "M",
        "from_state": "PLANNED",
        "to_state": "APPROVED",
    },
    "project_runtime_changed": {"previous": None, "current": {"java_version": "25", "spring_boot_version": "4.1.1"}},
    "consent_revoked": {"consent_type": "WAREHOUSE_ANALYTICS", "delete_requested": False},
    "scope_decision": {
        "decision": "ALLOW",
        "confidence": 0.93,
        "deciding_ring": "SCOPE_CLASSIFIER",
        "latency_ms": 41,
        "language": "tr",
    },
    "corpus_analysis": _ANALYSIS_PAYLOAD,
    "benchmark_analysis": {"benchmark": "owasp-benchmark", **_ANALYSIS_PAYLOAD},
}


def envelope(
    event_type: str = "finding_detected",
    *,
    project_key: str = KEY_A,
    event_id: str | None = None,
    occurred_at: str = "2026-10-27T10:00:00Z",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "event_id": event_id or str(uuid.uuid4()),
        "event_type": event_type,
        "schema_version": 1,
        "occurred_at": occurred_at,
        "project_key": project_key,
        "payload": dict(PAYLOADS[event_type]) if payload is None else payload,
    }

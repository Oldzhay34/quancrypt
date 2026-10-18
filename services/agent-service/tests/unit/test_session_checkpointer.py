"""The session checkpointer (D-253): what it writes is only the allow-listed channels and metadata, never above
64 KiB, never for a sub-graph namespace, and only when the call may persist."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from src.memory.short_term import StoredCheckpoint
from src.workflows.agent_graph import PERSISTED_CHANNELS, PERSISTED_METADATA, SessionCheckpointer, checkpoint_config

SESSION = UUID("00000000-0000-0000-0000-0000000000b1")
CHECKPOINT_ID = "1f1cb0a7-7994-6389-8002-7408bc1b3327"


class Store:
    def __init__(self) -> None:
        self.puts: list[tuple[UUID, UUID, str, bytes]] = []

    def get(self, session_id: UUID) -> StoredCheckpoint | None:
        if not self.puts:
            return None
        _, checkpoint_id, state_type, state = self.puts[-1]
        return StoredCheckpoint(checkpoint_id, state_type, state, None)  # type: ignore[arg-type]

    def put(self, session_id: UUID, checkpoint_id: UUID, state_type: str, state: bytes) -> bool:
        self.puts.append((session_id, checkpoint_id, state_type, state))
        return True

    def purge_idle(self) -> int:
        return 0


def checkpoint(values: dict[str, Any]) -> dict[str, Any]:
    return {
        "v": 4,
        "id": CHECKPOINT_ID,
        "ts": "2026-10-18T12:00:00+00:00",
        "channel_values": values,
        "channel_versions": dict.fromkeys(values, 1),
        "versions_seen": {},
        "updated_channels": None,
    }


METADATA = {"source": "loop", "step": 3, "parents": {}, "run_id": "r-1", "counters_since_delta_snapshot": {}}


def test_only_allow_listed_channels_and_metadata_are_written_and_the_id_lives_in_its_column() -> None:
    store = Store()
    saver = SessionCheckpointer(store)
    values = {
        "message": "Which algorithms are used where?",
        "draft": "draft text",
        "final": "final text",
        "last_intent": "inventory",
        "scan_id": "00000000-0000-0000-0000-00000000b001",
        "plan_exists": True,
        "evidence": [{"kind": "code_location", "reference": "A.java:3", "source_version": None}],
        "budget": {"prompt_tokens": 3, "completion_tokens": 2},
    }

    saver.put(checkpoint_config(SESSION, persist=True), checkpoint(values), METADATA, {})  # type: ignore[arg-type]

    [(session, checkpoint_id, state_type, state)] = store.puts
    assert (session, str(checkpoint_id), state_type) == (SESSION, CHECKPOINT_ID, "msgpack")
    body = JsonPlusSerializer(pickle_fallback=False, allowed_msgpack_modules=None).loads_typed((state_type, state))
    assert set(body["checkpoint"]["channel_values"]) <= PERSISTED_CHANNELS
    assert set(body["metadata"]) <= PERSISTED_METADATA
    assert "id" not in body["checkpoint"]
    assert b"Which algorithms" not in state and b"draft text" not in state and b"final text" not in state


def test_reading_restores_the_id_from_the_column() -> None:
    store = Store()
    saver = SessionCheckpointer(store)
    saver.put(checkpoint_config(SESSION, persist=True), checkpoint({"last_intent": "qkd"}), METADATA, {})  # type: ignore[arg-type]

    found = saver.get_tuple(checkpoint_config(SESSION, persist=False))

    assert found is not None
    assert found.checkpoint["id"] == CHECKPOINT_ID and found.checkpoint["channel_values"] == {"last_intent": "qkd"}


def test_a_call_that_may_not_persist_writes_nothing() -> None:
    store = Store()
    SessionCheckpointer(store).put(checkpoint_config(SESSION, persist=False), checkpoint({}), METADATA, {})  # type: ignore[arg-type]

    assert store.puts == []


def test_a_checkpoint_above_64_kib_is_skipped() -> None:
    store = Store()
    huge = {"evidence": [{"kind": "code_location", "reference": "x" * 1000, "source_version": None}] * 80}

    SessionCheckpointer(store).put(checkpoint_config(SESSION, persist=True), checkpoint(huge), METADATA, {})  # type: ignore[arg-type]

    assert store.puts == []


def test_a_sub_graph_namespace_is_refused() -> None:
    config = {"configurable": {"thread_id": str(SESSION), "checkpoint_ns": "child", "persist": True}}
    saver = SessionCheckpointer(Store())

    with pytest.raises(ValueError, match="root namespace"):
        saver.put(config, checkpoint({}), METADATA, {})  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="root namespace"):
        saver.get_tuple(config)  # type: ignore[arg-type]


def test_threads_are_deleted_with_their_session_only() -> None:
    with pytest.raises(NotImplementedError):
        SessionCheckpointer(Store()).delete_thread(str(uuid4()))

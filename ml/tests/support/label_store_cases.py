"""The LabelStore contract (LSP, hexagonal-service section 7): the fake and the PostgreSQL adapter run the same cases."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from quancrypt_ml.domain.labels import FIRST, SECOND, LabelRecord, Resolution
from quancrypt_ml.port.outbound.labeling import BatchExistsError, LabelStore, NewBatch, ResolutionConflictError

AT = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)
KEY = "a" * 64


def new_batch(name: str = "batch_001", size: int = 4) -> NewBatch:
    items = [(str(uuid.uuid4()), KEY if i % 2 else "b" * 64, i < 2) for i in range(size)]
    return NewBatch(str(uuid.uuid4()), name, AT, 42, items)


def case_batches_are_stored_once_and_read_back(store: LabelStore) -> None:
    batch = new_batch()
    store.create_batch(batch)
    stored = store.batch("batch_001")
    assert stored is not None and stored.id == batch.id and (stored.size, stored.double_size) == (4, 2)
    assert stored.items == {f: d for f, _, d in batch.items}
    assert store.batch("batch_002") is None
    with pytest.raises(BatchExistsError):
        store.create_batch(new_batch())


def case_labels_of_a_labeller_are_replaced_as_a_whole(store: LabelStore) -> None:
    batch = new_batch()
    store.create_batch(batch)
    ids = [f for f, _, _ in batch.items]
    store.replace_labels(batch.id, FIRST, [LabelRecord(f, "HIGH", "olcay", None) for f in ids], AT)
    store.replace_labels(batch.id, SECOND, [LabelRecord(ids[0], "LOW", "arkadaş", "emin değilim")], AT)
    store.replace_labels(batch.id, FIRST, [LabelRecord(f, "MEDIUM", "olcay", None) for f in ids[:3]], AT)
    assert store.labels(batch.id, FIRST) == dict.fromkeys(ids[:3], "MEDIUM")
    assert store.labels(batch.id, SECOND) == {ids[0]: "LOW"}


def case_a_failing_replacement_keeps_the_previous_labels(store: LabelStore) -> None:
    batch = new_batch()
    store.create_batch(batch)
    ids = [f for f, _, _ in batch.items]
    store.replace_labels(batch.id, FIRST, [LabelRecord(f, "HIGH", "olcay", None) for f in ids], AT)
    foreign = [LabelRecord(ids[0], "LOW", "olcay", None), LabelRecord(str(uuid.uuid4()), "LOW", "olcay", None)]
    with pytest.raises(Exception):  # noqa: B017 (the fake raises ValueError, PostgreSQL an IntegrityError)
        store.replace_labels(batch.id, FIRST, foreign, AT)
    assert store.labels(batch.id, FIRST) == dict.fromkeys(ids, "HIGH")


def _disagreeing(store: LabelStore) -> tuple[NewBatch, list[str]]:
    """A batch whose first two records (the double-label ones) have different labels from the two labellers."""
    batch = new_batch()
    store.create_batch(batch)
    ids = [f for f, _, _ in batch.items]
    store.replace_labels(batch.id, FIRST, [LabelRecord(f, "HIGH", "olcay", None) for f in ids], AT)
    store.replace_labels(batch.id, SECOND, [LabelRecord(f, "LOW", "arkadas", None) for f in ids[:2]], AT)
    return batch, ids


def case_resolutions_are_added_and_replaced(store: LabelStore) -> None:
    batch, ids = _disagreeing(store)
    store.replace_resolutions(batch.id, [Resolution(ids[0], "LOW", "olcay", None)], AT)
    again = [Resolution(ids[0], "HIGH", "olcay", "yeniden"), Resolution(ids[1], "LOW", "olcay", None)]
    store.replace_resolutions(batch.id, again, AT)
    assert store.resolutions(batch.id) == {ids[0]: "HIGH", ids[1]: "LOW"}


def case_a_record_that_is_no_disagreement_cannot_be_resolved(store: LabelStore) -> None:
    batch, ids = _disagreeing(store)
    mixed = [Resolution(ids[0], "LOW", "olcay", None), Resolution(ids[2], "LOW", "olcay", None)]
    with pytest.raises(ResolutionConflictError):
        store.replace_resolutions(batch.id, mixed, AT)
    assert store.resolutions(batch.id) == {}


def case_a_reimport_drops_the_resolutions_its_new_labels_make_stale(store: LabelStore) -> None:
    batch, ids = _disagreeing(store)
    both = [Resolution(ids[0], "MEDIUM", "olcay", None), Resolution(ids[1], "MEDIUM", "olcay", None)]
    store.replace_resolutions(batch.id, both, AT)
    # The second labeller changes the first record (still a disagreement, but another pair) and keeps the second.
    second = [LabelRecord(ids[0], "CRITICAL", "arkadas", None), LabelRecord(ids[1], "LOW", "arkadas", None)]
    store.replace_labels(batch.id, SECOND, second, AT)
    assert store.resolutions(batch.id) == {ids[1]: "MEDIUM"}
    # The first labeller now agrees with the second on the second record: its resolution is gone too.
    store.replace_labels(batch.id, FIRST, [LabelRecord(ids[1], "LOW", "olcay", None)], AT)
    assert store.resolutions(batch.id) == {}


CASES: list[Callable[[LabelStore], None]] = [
    case_batches_are_stored_once_and_read_back,
    case_labels_of_a_labeller_are_replaced_as_a_whole,
    case_a_failing_replacement_keeps_the_previous_labels,
    case_resolutions_are_added_and_replaced,
    case_a_record_that_is_no_disagreement_cannot_be_resolved,
    case_a_reimport_drops_the_resolutions_its_new_labels_make_stale,
]

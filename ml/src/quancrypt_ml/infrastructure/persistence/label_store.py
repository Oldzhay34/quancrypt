"""LabelStore over warehouse_db.labels (ml/migrations 0001). Every method is one transaction at READ COMMITTED.

Two imports of the same labeller of a batch at once are serialised by an advisory lock on the batch, so the
delete and insert of one never interleave with the other's (the last one wins as a whole)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import IntegrityError

from quancrypt_ml.domain.labels import LabelRecord, Resolution
from quancrypt_ml.port.outbound.labeling import BatchExistsError, NewBatch, ResolutionConflictError, StoredBatch

# Records of a batch whose two labels differ (the only records a resolution may stand for).
_DISAGREEMENTS = (
    "SELECT f.finding_id FROM labels.gold_label f JOIN labels.gold_label s "
    "ON s.batch_id = f.batch_id AND s.finding_id = f.finding_id AND s.labeler_role = 'SECOND' "
    "WHERE f.batch_id = :batch AND f.labeler_role = 'FIRST' AND f.risk_class <> s.risk_class"
)
# A resolution stands for a pair of labels: it goes when its record's label changed or the pair no longer differs.
_DELETE_STALE_RESOLUTIONS = (
    "DELETE FROM labels.label_resolution WHERE batch_id = :batch "  # noqa: S608 (two module constants, no input)
    "AND (finding_id = ANY(CAST(:changed AS uuid[])) OR finding_id NOT IN (" + _DISAGREEMENTS + "))"
)


def _labeler_id(connection: Connection, name: str) -> str:
    """The id of a labeller by name, created on first use (two imports that create one name at once agree on it)."""
    connection.execute(
        text("INSERT INTO labels.labeler (id, name) VALUES (:id, :name) ON CONFLICT (name) DO NOTHING"),
        {"id": str(uuid.uuid4()), "name": name},
    )
    return str(
        connection.execute(text("SELECT id::text FROM labels.labeler WHERE name = :name"), {"name": name}).scalar_one()
    )


def _lock_batch(connection: Connection, batch_id: str) -> None:
    """A transaction-scoped advisory lock per batch: a row lock (`FOR UPDATE`) would need UPDATE on label_batch, which
    the application role does not have and does not need otherwise."""
    connection.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:name, 0))"), {"name": "quancrypt-labels:" + batch_id}
    )


class PostgresLabelStore:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def create_batch(self, batch: NewBatch) -> None:
        try:
            with self._engine.begin() as connection:
                connection.execute(
                    text("INSERT INTO labels.label_batch (id, name, created_at, seed) VALUES (:id, :name, :at, :seed)"),
                    {"id": batch.id, "name": batch.name, "at": batch.created_at, "seed": batch.seed},
                )
                findings = [{"finding": f, "key": k} for f, k, _ in batch.items]
                connection.execute(
                    text(
                        "INSERT INTO labels.labeled_finding (finding_id, project_key) VALUES (:finding, :key) "
                        "ON CONFLICT (finding_id) DO NOTHING"
                    ),
                    findings,
                )
                # A finding keeps the project key it was first stored with; another one is a broken invariant.
                mismatched = connection.execute(
                    text(
                        "SELECT count(*) FROM labels.labeled_finding l "
                        "JOIN unnest(CAST(:findings AS uuid[]), CAST(:keys AS text[])) AS n(finding_id, project_key) "
                        "ON n.finding_id = l.finding_id WHERE l.project_key <> n.project_key"
                    ),
                    {"findings": [f for f, _, _ in batch.items], "keys": [k for _, k, _ in batch.items]},
                ).scalar_one()
                if mismatched:
                    raise ValueError("a finding is stored with another project key")
                connection.execute(
                    text(
                        "INSERT INTO labels.label_batch_item (batch_id, finding_id, double_label) "
                        "VALUES (:batch, :finding, :double)"
                    ),
                    [{"batch": batch.id, "finding": f, "double": d} for f, _, d in batch.items],
                )
        except IntegrityError as error:
            if "uq_label_batch_name" in str(error.orig):
                raise BatchExistsError(batch.name) from None
            raise

    def batch(self, name: str) -> StoredBatch | None:
        with self._engine.begin() as connection:
            head = connection.execute(
                text("SELECT id::text, name FROM labels.label_batch WHERE name = :name"), {"name": name}
            ).first()
            if head is None:
                return None
            items = connection.execute(
                text("SELECT finding_id::text, double_label FROM labels.label_batch_item WHERE batch_id = :id"),
                {"id": head[0]},
            ).all()
        mapping = {str(finding): bool(double) for finding, double in items}
        return StoredBatch(head[0], head[1], len(mapping), sum(mapping.values()), mapping)

    def replace_labels(self, batch_id: str, labeler_role: str, records: Sequence[LabelRecord], at: datetime) -> None:
        with self._engine.begin() as connection:
            _lock_batch(connection, batch_id)
            previous = connection.execute(
                text(
                    "SELECT finding_id::text, risk_class FROM labels.gold_label "
                    "WHERE batch_id = :batch AND labeler_role = :role"
                ),
                {"batch": batch_id, "role": labeler_role},
            ).all()
            before = {str(finding): str(label) for finding, label in previous}
            connection.execute(
                text("DELETE FROM labels.gold_label WHERE batch_id = :batch AND labeler_role = :role"),
                {"batch": batch_id, "role": labeler_role},
            )
            if records:
                self._insert_labels(connection, batch_id, labeler_role, records, at)
            after = {r.finding_id: r.label for r in records}
            changed = [f for f in set(before) | set(after) if before.get(f) != after.get(f)]
            connection.execute(
                text(_DELETE_STALE_RESOLUTIONS),
                {"batch": batch_id, "changed": changed},
            )

    def _insert_labels(
        self, connection: Connection, batch_id: str, labeler_role: str, records: Sequence[LabelRecord], at: datetime
    ) -> None:
        ids = {name: _labeler_id(connection, name) for name in sorted({r.labeler_name for r in records})}
        connection.execute(
            text(
                "INSERT INTO labels.gold_label "
                "(batch_id, finding_id, labeler_role, labeler_id, risk_class, notes, labeled_at) "
                "VALUES (:batch, :finding, :role, :labeler, :label, :notes, :at)"
            ),
            [
                {
                    "batch": batch_id,
                    "finding": r.finding_id,
                    "role": labeler_role,
                    "labeler": ids[r.labeler_name],
                    "label": r.label,
                    "notes": r.notes,
                    "at": at,
                }  # fmt: skip
                for r in records
            ],
        )

    def labels(self, batch_id: str, labeler_role: str) -> dict[str, str]:
        with self._engine.begin() as connection:
            rows = connection.execute(
                text(
                    "SELECT finding_id::text, risk_class FROM labels.gold_label "
                    "WHERE batch_id = :batch AND labeler_role = :role"
                ),
                {"batch": batch_id, "role": labeler_role},
            ).all()
        return {str(finding): str(label) for finding, label in rows}

    def replace_resolutions(self, batch_id: str, resolutions: Sequence[Resolution], at: datetime) -> None:
        if not resolutions:
            return
        with self._engine.begin() as connection:
            _lock_batch(connection, batch_id)
            open_ = {str(row[0]) for row in connection.execute(text(_DISAGREEMENTS), {"batch": batch_id})}
            if not {r.finding_id for r in resolutions} <= open_:
                raise ResolutionConflictError("a record to resolve is no longer a disagreement")
            ids = {name: _labeler_id(connection, name) for name in sorted({r.resolved_by for r in resolutions})}
            connection.execute(
                text(
                    "DELETE FROM labels.label_resolution "
                    "WHERE batch_id = :batch AND finding_id = ANY(CAST(:ids AS uuid[]))"
                ),
                {"batch": batch_id, "ids": [r.finding_id for r in resolutions]},
            )
            connection.execute(
                text(
                    "INSERT INTO labels.label_resolution "
                    "(batch_id, finding_id, risk_class, resolved_by, notes, resolved_at) "
                    "VALUES (:batch, :finding, :label, :by, :notes, :at)"
                ),
                [
                    {
                        "batch": batch_id,
                        "finding": r.finding_id,
                        "label": r.label,
                        "by": ids[r.resolved_by],
                        "notes": r.notes,
                        "at": at,
                    }  # fmt: skip
                    for r in resolutions
                ],
            )

    def resolutions(self, batch_id: str) -> dict[str, str]:
        with self._engine.begin() as connection:
            rows = connection.execute(
                text("SELECT finding_id::text, risk_class FROM labels.label_resolution WHERE batch_id = :batch"),
                {"batch": batch_id},
            ).all()
        return {str(finding): str(label) for finding, label in rows}

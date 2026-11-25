"""ResultSink over warehouse_db.ml_outputs (ml/migrations 0002).

`store` writes the model versions of one training run (the risk model and its baselines) in one transaction: each
version of that name and version is deleted (its predictions, explanations, metrics and publication go by CASCADE) and
written again. A failure anywhere leaves every earlier version as it was (acid-3nf-database section 5).

Lock order (D-330, D-331): the advisory locks of the model names in name order; then the ingest-api project key locks
(`quancrypt-ingest:<key>`, the lock a KVKK erasure and the preprocessing hold while they delete or rewrite a key's
rows) in key order, for the keys of the new predictions and of the predictions of the versions being replaced; only
then are rows touched. Two runs never interleave; an erasure takes no model lock, and no row of a key the run has not
locked is touched, so a run and an erasure do not deadlock.

Under the key locks an erasure has either committed or not begun, so the state is read, not a clock: a prediction is
written only if its finding is still in prep.finding (data-platform migration 0003). prep.finding is absent only where
data-platform never migrated (no warehouse data, nothing erased); then every prediction is written."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import replace

from sqlalchemy import Connection, Engine, text

from quancrypt_ml.port.outbound.risk import FindingConflictError, PublishedVersionError, StoredModel

__all__ = ["FindingConflictError", "PostgresResultSink", "PublishedVersionError"]

INGEST_LOCK_NAMESPACE = "quancrypt-ingest:"  # data-platform repositories.LOCK_NAMESPACE (the KVKK erasure's key lock)


def _lock(connection: Connection, name: str) -> None:
    connection.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:name, 0))"), {"name": name})


def _refuse_unpublishing(connection: Connection, models: Sequence[StoredModel]) -> None:
    for model in models:
        if model.publish:
            continue
        published = connection.execute(
            text(
                "SELECT EXISTS (SELECT 1 FROM ml_outputs.published_model p JOIN ml_outputs.model_version v "
                "ON v.id = p.model_version_id WHERE v.model_name = :name AND v.version = :version)"
            ),
            {"name": model.model_name, "version": model.version},
        ).scalar_one()
        if published:
            raise PublishedVersionError("a published version cannot be written again unpublished")


def _table_exists(connection: Connection, schema: str, name: str) -> bool:
    # The catalog is read directly, as data-platform's eraser does (to_regclass needs USAGE on the schema).
    return bool(
        connection.execute(
            text(
                "SELECT EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = :schema AND c.relname = :name AND c.relkind IN ('r', 'p'))"
            ),
            {"schema": schema, "name": name},
        ).scalar_one()
    )


def _replaced_keys(connection: Connection, models: Sequence[StoredModel]) -> set[str]:
    """The project keys of the predictions the replaced versions hold (their rows go by CASCADE)."""
    rows = connection.execute(
        text(
            "SELECT DISTINCT s.project_key FROM ml_outputs.model_version v "
            "JOIN unnest(CAST(:names AS text[]), CAST(:versions AS text[])) AS r(model_name, version) "
            "ON r.model_name = v.model_name AND r.version = v.version "
            "JOIN ml_outputs.risk_prediction p ON p.model_version_id = v.id "
            "JOIN ml_outputs.scored_finding s ON s.finding_id = p.finding_id"
        ),
        {"names": [m.model_name for m in models], "versions": [m.version for m in models]},
    ).scalars()
    return {str(k) for k in rows}


def _present_findings(connection: Connection, findings: Sequence[str]) -> set[str] | None:
    """The given findings that are still in the warehouse, or None where there is no warehouse (see the module)."""
    if not _table_exists(connection, "prep", "finding"):
        return None
    if not findings:
        return set()
    rows = connection.execute(
        text("SELECT id::text FROM prep.finding WHERE id = ANY(CAST(:findings AS uuid[]))"),
        {"findings": list(findings)},
    ).scalars()
    return {str(f) for f in rows}


def _version(connection: Connection, model: StoredModel) -> str:
    version_id = str(uuid.uuid4())
    connection.execute(
        text("DELETE FROM ml_outputs.model_version WHERE model_name = :name AND version = :version"),
        {"name": model.model_name, "version": model.version},
    )
    connection.execute(
        text(
            "INSERT INTO ml_outputs.model_version "
            "(id, model_name, version, algorithm, label_source, mlflow_run_id, trained_at) "
            "VALUES (:id, :name, :version, :algorithm, :source, :run, :at)"
        ),
        {
            "id": version_id,
            "name": model.model_name,
            "version": model.version,
            "algorithm": model.algorithm,
            "source": model.label_source,
            "run": model.mlflow_run_id,
            "at": model.trained_at,
        },  # fmt: skip
    )
    return version_id


def _predictions(connection: Connection, model: StoredModel, version_id: str) -> None:
    if not model.predictions:
        return
    connection.execute(
        text(
            "INSERT INTO ml_outputs.scored_finding (finding_id, project_key) VALUES (:finding, :key) "
            "ON CONFLICT (finding_id) DO NOTHING"
        ),
        [{"finding": p.finding_id, "key": p.project_key} for p in model.predictions],
    )
    mismatched = connection.execute(
        text(
            "SELECT count(*) FROM ml_outputs.scored_finding s "
            "JOIN unnest(CAST(:findings AS uuid[]), CAST(:keys AS text[])) AS n(finding_id, project_key) "
            "ON n.finding_id = s.finding_id WHERE s.project_key <> n.project_key"
        ),
        {"findings": [p.finding_id for p in model.predictions], "keys": [p.project_key for p in model.predictions]},
    ).scalar_one()
    if mismatched:
        raise FindingConflictError("a finding is stored with another project key")
    connection.execute(
        text(
            "INSERT INTO ml_outputs.risk_prediction (model_version_id, finding_id, risk_class, risk_score) "
            "VALUES (:version, :finding, :class, :score)"
        ),
        [
            {"version": version_id, "finding": p.finding_id, "class": p.risk_class, "score": p.risk_score}
            for p in model.predictions
        ],
    )
    explanations = [
        {"version": version_id, "finding": p.finding_id, "rank": rank, "feature": a.feature, "value": a.value}
        for p in model.predictions
        for rank, a in enumerate(p.explanation, start=1)
    ]
    if explanations:
        connection.execute(
            text(
                "INSERT INTO ml_outputs.risk_explanation (model_version_id, finding_id, rank, feature, shap_value) "
                "VALUES (:version, :finding, :rank, :feature, :value)"
            ),
            explanations,
        )


def _metrics(connection: Connection, model: StoredModel, version_id: str) -> None:
    if not model.metrics:
        return
    connection.execute(
        text(
            "INSERT INTO ml_outputs.model_metric (model_version_id, scope, fold, metric, label, value) "
            "VALUES (:version, :scope, :fold, :metric, :label, :value)"
        ),
        [
            {
                "version": version_id,
                "scope": m.scope,
                "fold": m.fold,
                "metric": m.metric,
                "label": m.label,
                "value": m.value,
            }  # fmt: skip
            for m in model.metrics
        ],
    )


def _publish(connection: Connection, model: StoredModel, version_id: str) -> None:
    if not model.publish:
        return
    connection.execute(
        text("DELETE FROM ml_outputs.published_model WHERE model_name = :name"), {"name": model.model_name}
    )
    connection.execute(
        text(
            "INSERT INTO ml_outputs.published_model (model_name, model_version_id, published_at) "
            "VALUES (:name, :version, :at)"
        ),
        {"name": model.model_name, "version": version_id, "at": model.trained_at},
    )


class PostgresResultSink:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def store(self, models: Sequence[StoredModel]) -> int:
        if not models:
            return 0
        with self._engine.begin() as connection:
            for name in sorted({m.model_name for m in models}):
                _lock(connection, "quancrypt-ml-outputs:" + name)
            new_keys = {p.project_key for m in models for p in m.predictions}
            for key in sorted(new_keys | _replaced_keys(connection, models)):
                _lock(connection, INGEST_LOCK_NAMESPACE + key)
            _refuse_unpublishing(connection, models)
            present = _present_findings(connection, sorted({p.finding_id for m in models for p in m.predictions}))
            skipped = 0
            for model in models:
                kept = [p for p in model.predictions if present is None or p.finding_id in present]
                skipped += len(model.predictions) - len(kept)
                version_id = _version(connection, model)
                written = replace(model, predictions=kept)
                _predictions(connection, written, version_id)
                _metrics(connection, written, version_id)
                _publish(connection, written, version_id)
            return skipped

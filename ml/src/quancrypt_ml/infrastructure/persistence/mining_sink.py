"""The mining sinks over warehouse_db.ml_outputs (ml/migrations 0004). A technique's run is deleted (its rows go by
CASCADE) and written again in one transaction; K-Means and HDBSCAN are written together in one (D-340c).

Lock order, as ResultSink's (D-330, D-331, D-338h): the advisory locks of the techniques being written, in name order;
then the ingest-api project key locks in key order, for the keys of the new rows and of the rows being replaced; only
then are rows touched. Under the key locks a KVKK erasure has either committed or not begun, so a project's row is
written only while the project still has a finding in prep.finding. prep.finding is absent only where data-platform
never migrated; then every row is written."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import Connection, Engine, text

from quancrypt_ml.domain.mining import AnomalyScore, Rule
from quancrypt_ml.infrastructure.persistence.result_sink import INGEST_LOCK_NAMESPACE
from quancrypt_ml.port.outbound.mining import MiningRun, TechniqueClusters

TECHNIQUE_LOCK_NAMESPACE = "quancrypt-mining:"


def _lock(connection: Connection, name: str) -> None:
    connection.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:name, 0))"), {"name": name})


def _present(connection: Connection, keys: set[str]) -> set[str]:
    """The keys that still have findings (the caller already holds their locks)."""
    exists = connection.execute(
        text(
            "SELECT EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'prep' AND c.relname = 'finding' AND c.relkind IN ('r', 'p'))"
        )
    ).scalar_one()
    if not exists:
        return keys
    found = connection.execute(
        text("SELECT DISTINCT project_key FROM prep.finding WHERE project_key = ANY(CAST(:keys AS text[]))"),
        {"keys": sorted(keys)},
    ).scalars()
    return {str(k) for k in found}


def _lock_keys(connection: Connection, table: str, techniques: Sequence[str], keys: set[str]) -> None:
    replaced = connection.execute(
        text(f"SELECT project_key FROM ml_outputs.{table} WHERE technique = ANY(CAST(:t AS text[]))"),  # noqa: S608
        {"t": list(techniques)},
    ).scalars()
    for key in sorted(keys | {str(k) for k in replaced}):
        _lock(connection, INGEST_LOCK_NAMESPACE + key)


def _write_clusters(connection: Connection, clustering: TechniqueClusters, present: set[str]) -> None:
    technique = clustering.technique
    _replace_run(connection, technique, clustering.run)
    if clustering.archetypes:
        connection.execute(
            text(
                "INSERT INTO ml_outputs.archetype (technique, cluster_no, name, rationale) "
                "VALUES (:t, :no, :name, :rationale)"
            ),
            [
                {"t": technique, "no": a.cluster_no, "name": a.name, "rationale": a.rationale}
                for a in clustering.archetypes
            ],
        )
    kept = [a for a in clustering.assignments if a.project_key in present]
    if kept:
        connection.execute(
            text(
                "INSERT INTO ml_outputs.project_archetype (technique, project_key, cluster_no) VALUES (:t, :key, :no)"
            ),
            [{"t": technique, "key": a.project_key, "no": a.cluster_no} for a in kept],
        )


def _replace_run(connection: Connection, technique: str, run: MiningRun) -> None:
    connection.execute(text("DELETE FROM ml_outputs.mining_run WHERE technique = :t"), {"t": technique})
    connection.execute(
        text(
            "INSERT INTO ml_outputs.mining_run (technique, mlflow_run_id, run_at, project_count) "
            "VALUES (:t, :run, :at, :count)"
        ),
        {"t": technique, "run": run.mlflow_run_id, "at": run.run_at, "count": run.project_count},
    )
    if run.parameters:
        connection.execute(
            text("INSERT INTO ml_outputs.mining_run_parameter (technique, name, value) VALUES (:t, :name, :value)"),
            [{"t": technique, "name": name, "value": value} for name, value in sorted(run.parameters.items())],
        )


class PostgresMiningSink:
    """ClusterSink, RuleSink and AnomalySink."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def store_clusters(self, clusterings: Sequence[TechniqueClusters]) -> int:
        techniques = sorted(c.technique for c in clusterings)
        with self._engine.begin() as connection:
            for technique in techniques:
                _lock(connection, TECHNIQUE_LOCK_NAMESPACE + technique)
            keys = {a.project_key for c in clusterings for a in c.assignments}
            _lock_keys(connection, "project_archetype", techniques, keys)
            present = _present(connection, keys)
            for clustering in clusterings:
                _write_clusters(connection, clustering, present)
            return len(keys - present)

    def store_rules(self, run: MiningRun, rules: Sequence[Rule]) -> None:
        with self._engine.begin() as connection:
            _lock(connection, TECHNIQUE_LOCK_NAMESPACE + "FP_GROWTH")
            _replace_run(connection, "FP_GROWTH", run)
            if not rules:
                return
            connection.execute(
                text(
                    "INSERT INTO ml_outputs.association_rule (technique, rule_no, support, confidence, lift) "
                    "VALUES ('FP_GROWTH', :no, :support, :confidence, :lift)"
                ),
                [
                    {"no": no, "support": r.support, "confidence": r.confidence, "lift": r.lift}
                    for no, r in enumerate(rules, start=1)
                ],
            )
            connection.execute(
                text(
                    "INSERT INTO ml_outputs.association_rule_item (technique, rule_no, item, side) "
                    "VALUES ('FP_GROWTH', :no, :item, :side)"
                ),
                [
                    {"no": no, "item": item, "side": side}
                    for no, r in enumerate(rules, start=1)
                    for side, items in (("ANTECEDENT", r.antecedent), ("CONSEQUENT", r.consequent))
                    for item in items
                ],
            )

    def store_anomalies(self, run: MiningRun, scores: Sequence[AnomalyScore]) -> int:
        technique = "ISOLATION_FOREST"
        with self._engine.begin() as connection:
            _lock(connection, TECHNIQUE_LOCK_NAMESPACE + technique)
            keys = {s.project_key for s in scores}
            _lock_keys(connection, "anomaly", [technique], keys)
            present = _present(connection, keys)
            _replace_run(connection, technique, run)
            kept = [s for s in scores if s.project_key in present]
            if kept:
                connection.execute(
                    text(
                        "INSERT INTO ml_outputs.anomaly (technique, project_key, score, is_flagged) "
                        "VALUES (:t, :key, :score, :flagged)"
                    ),
                    [{"t": technique, "key": s.project_key, "score": s.score, "flagged": s.is_flagged} for s in kept],
                )
            return len(scores) - len(kept)

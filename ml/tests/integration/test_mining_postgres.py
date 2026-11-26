"""The mining tables (ml/migrations 0004), the sink and the data source against a real warehouse_db: contracts,
constraints, the KVKK erasure and the key lock."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError, OperationalError

from quancrypt_ml.domain.mining import AnomalyScore, ProjectLibraries, ProjectProfile
from quancrypt_ml.infrastructure.persistence import database
from quancrypt_ml.infrastructure.persistence.mining_data import PostgresMiningData
from quancrypt_ml.infrastructure.persistence.mining_sink import PostgresMiningSink
from quancrypt_ml.infrastructure.persistence.result_sink import INGEST_LOCK_NAMESPACE
from quancrypt_ml.port.outbound.mining import ClusterAssignment, MiningRun, TechniqueClusters
from tests.support.mining_fakes import corpus, key, libraries
from tests.support.mining_port_cases import AT, DATA_CASES, SINK_CASES, DataFactory, SinkHarness, SinkState
from tests.support.postgres import PostgresInstance

pytestmark = pytest.mark.postgres

TABLES = (
    "mining_run", "mining_run_parameter", "archetype", "project_archetype", "association_rule",
    "association_rule_item", "anomaly",
)  # fmt: skip
FAMILIES = ("rsa", "unknown")
CONTEXTS = ("token_signature", "tls_key_exchange")


def _admin(pg: PostgresInstance, *statements: str) -> None:
    with pg.engine("warehouse_db_migrator").begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


@pytest.fixture
def sink(pg: PostgresInstance) -> Iterator[PostgresMiningSink]:
    _admin(pg, "TRUNCATE ml_outputs.mining_run CASCADE", "DROP SCHEMA IF EXISTS prep CASCADE")
    engine = database.engine(pg.settings())
    yield PostgresMiningSink(engine)
    engine.dispose()
    _admin(pg, "DROP SCHEMA IF EXISTS prep CASCADE")


def _rows(pg: PostgresInstance, sql: str) -> list[tuple[object, ...]]:
    with pg.engine("warehouse_db_migrator").begin() as connection:
        return [tuple(r) for r in connection.execute(text(sql)).all()]


def _present(pg: PostgresInstance) -> Callable[[list[str]], None]:
    """A stand-in for data-platform's prep.finding (the one column the sink reads)."""
    _admin(
        pg,
        "CREATE SCHEMA IF NOT EXISTS prep",
        "CREATE TABLE IF NOT EXISTS prep.finding (project_key char(64) NOT NULL)",
        "GRANT USAGE ON SCHEMA prep TO warehouse_db_app",
        "GRANT SELECT ON prep.finding TO warehouse_db_app",
    )

    def present(keys: list[str]) -> None:
        with pg.engine("warehouse_db_migrator").begin() as connection:
            connection.execute(text("TRUNCATE prep.finding"))
            for found in keys:
                connection.execute(text("INSERT INTO prep.finding VALUES (:k)"), {"k": found})

    return present


def _harness(pg: PostgresInstance, sink: PostgresMiningSink) -> SinkHarness:
    def read() -> SinkState:
        items = _rows(
            pg, "SELECT rule_no, side, item FROM ml_outputs.association_rule_item ORDER BY rule_no, side, item"
        )
        rules = [
            tuple(tuple(str(i) for no_, side, i in items if no_ == no and side == wanted) for wanted in
                  ("ANTECEDENT", "CONSEQUENT"))
            for no in sorted({int(str(r[0])) for r in items})
        ]  # fmt: skip
        return SinkState(
            {str(t): int(str(c)) for t, c in _rows(pg, "SELECT technique, project_count FROM ml_outputs.mining_run")},
            set(_rows(pg, "SELECT technique, cluster_no, name FROM ml_outputs.archetype")),  # type: ignore[arg-type]
            set(_rows(pg, "SELECT technique, project_key, cluster_no FROM ml_outputs.project_archetype")),  # type: ignore[arg-type]
            rules,  # type: ignore[arg-type]
            set(_rows(pg, "SELECT project_key, is_flagged FROM ml_outputs.anomaly")),  # type: ignore[arg-type]
        )

    return SinkHarness(sink, read, _present(pg))  # type: ignore[arg-type]


@pytest.mark.parametrize("case", SINK_CASES, ids=lambda c: c.__name__)
def test_the_postgres_sink_keeps_the_contract(
    case: Callable[[SinkHarness], None], pg: PostgresInstance, sink: PostgresMiningSink
) -> None:
    case(_harness(pg, sink))


def test_the_parameters_are_stored_and_without_a_warehouse_every_project_is_written(
    pg: PostgresInstance, sink: PostgresMiningSink
) -> None:
    run = MiningRun("0" * 32, AT, 1, {"contamination": "0.1", "seed": "42"})
    assert sink.store_anomalies(run, [AnomalyScore(key(1), -0.1, True)]) == 0
    assert _rows(pg, "SELECT name, value FROM ml_outputs.mining_run_parameter ORDER BY name") == [
        ("contamination", "0.1"), ("seed", "42"),
    ]  # fmt: skip


def test_the_kvkk_erasure_removes_a_projects_assignments_and_score(
    pg: PostgresInstance, sink: PostgresMiningSink
) -> None:
    run = MiningRun("0" * 32, AT, 2, {})
    assigned = [ClusterAssignment(key(1), None), ClusterAssignment(key(2), None)]
    sink.store_clusters([TechniqueClusters("HDBSCAN", run, [], assigned)])
    sink.store_anomalies(run, [AnomalyScore(key(1), 0.1, False), AnomalyScore(key(2), 0.1, False)])
    # The statements data-platform's eraser runs for the registered tables (application role, D-338h).
    with pg.engine("warehouse_db_app").begin() as connection:
        for table in ("project_archetype", "anomaly"):
            connection.execute(text(f"DELETE FROM ml_outputs.{table} WHERE project_key = :k"), {"k": key(1)})
    assert _rows(pg, "SELECT project_key FROM ml_outputs.project_archetype") == [(key(2),)]
    assert _rows(pg, "SELECT project_key FROM ml_outputs.anomaly") == [(key(2),)]


def test_a_run_waits_for_an_erasure_that_holds_the_key_lock_and_then_leaves_the_project_out(
    pg: PostgresInstance, sink: PostgresMiningSink
) -> None:
    present = _present(pg)
    present([key(1), key(2)])
    skipped: list[int] = []
    run = MiningRun("0" * 32, AT, 2, {})
    scores = [AnomalyScore(key(1), 0.1, False), AnomalyScore(key(2), 0.1, False)]
    with pg.engine("warehouse_db_migrator").begin() as holder:
        holder.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:n, 0))"), {"n": INGEST_LOCK_NAMESPACE + key(1)}
        )
        holder.execute(text("DELETE FROM prep.finding WHERE project_key = :k"), {"k": key(1)})
        worker = threading.Thread(target=lambda: skipped.append(sink.store_anomalies(run, scores)))
        worker.start()
        time.sleep(1.0)
        assert worker.is_alive()  # waiting for the key lock
    worker.join(30)
    assert skipped == [1] and _rows(pg, "SELECT project_key FROM ml_outputs.anomaly") == [(key(2),)]


RUN = "INSERT INTO ml_outputs.mining_run VALUES ('{t}', NULL, now(), 1)"


@pytest.mark.parametrize(
    ("technique", "statement", "constraint"),
    [
        ("KMEANS", "INSERT INTO ml_outputs.mining_run VALUES ('PREFIXSPAN', NULL, now(), 1)", "fk_mining_run_technique"),
        ("KMEANS", RUN.format(t="KMEANS"), "pk_mining_run"),
        ("KMEANS", "INSERT INTO ml_outputs.archetype VALUES ('KMEANS', 0, 'n', 'r')", "ck_archetype_cluster"),
        ("FP_GROWTH", "INSERT INTO ml_outputs.archetype VALUES ('FP_GROWTH', 1, 'n', 'r')", "ck_archetype_technique"),
        ("KMEANS", f"INSERT INTO ml_outputs.project_archetype VALUES ('KMEANS', '{'a' * 64}', NULL)", "ck_project_archetype_noise"),
        ("KMEANS", f"INSERT INTO ml_outputs.project_archetype VALUES ('KMEANS', '{'a' * 64}', 3)", "fk_project_archetype_cluster"),
        ("HDBSCAN", "INSERT INTO ml_outputs.project_archetype VALUES ('HDBSCAN', 'x', NULL)", "ck_project_archetype_key"),
        ("FP_GROWTH", "INSERT INTO ml_outputs.association_rule VALUES ('FP_GROWTH', 1, 1.5, 0.5, 1)", "ck_association_rule_support"),
        ("FP_GROWTH", "INSERT INTO ml_outputs.association_rule_item VALUES ('FP_GROWTH', 9, 'lib:a', 'ANTECEDENT')", "fk_association_rule_item_rule"),
        ("ISOLATION_FOREST", "INSERT INTO ml_outputs.anomaly VALUES ('ISOLATION_FOREST', 'x', 0, false)", "ck_anomaly_key"),
    ],
)  # fmt: skip
def test_every_constraint_refuses_what_it_guards(
    pg: PostgresInstance, sink: PostgresMiningSink, technique: str, statement: str, constraint: str
) -> None:
    _admin(pg, RUN.format(t=technique))
    with pytest.raises(IntegrityError, match=constraint):
        _admin(pg, statement)


def test_a_rule_item_is_a_library_or_a_family(pg: PostgresInstance, sink: PostgresMiningSink) -> None:
    _admin(
        pg, RUN.format(t="FP_GROWTH"), "INSERT INTO ml_outputs.association_rule VALUES ('FP_GROWTH', 1, 0.5, 0.5, 1)"
    )
    with pytest.raises(IntegrityError, match="ck_association_rule_item_item"):
        _admin(pg, "INSERT INTO ml_outputs.association_rule_item VALUES ('FP_GROWTH', 1, 'com/acme', 'ANTECEDENT')")


def _marts(pg: PostgresInstance) -> DataFactory:
    """Stand-ins for the two dbt marts with the columns the source reads (data-platform tests build the real ones)."""
    shares = [f"share_alg_{f}" for f in FAMILIES] + [f"share_ctx_{c}" for c in CONTEXTS]
    shares += ["share_p0", "share_p1", "share_p2", "share_p3"]
    _admin(
        pg,
        "DROP SCHEMA IF EXISTS marts CASCADE",
        "CREATE SCHEMA marts",
        "CREATE TABLE marts.mart_archetypes (project_key char(64), origin varchar(16), analysis_unit_count bigint, "
        "finding_count bigint, findings_per_unit double precision, "
        + ", ".join(f"{c} double precision" for c in shares)
        + ")",
        "CREATE TABLE marts.mart_risk_features (project_key char(64), origin varchar(16), library varchar(64), "
        "algorithm_family varchar(32), in_test_code boolean)",
        "GRANT USAGE ON SCHEMA marts TO warehouse_db_app",
        "GRANT SELECT ON ALL TABLES IN SCHEMA marts TO warehouse_db_app",
    )

    def factory(
        profiles: list[ProjectProfile], usages: list[ProjectLibraries], with_findings: int
    ) -> PostgresMiningData:
        with pg.engine("warehouse_db_migrator").begin() as connection:
            for p in profiles:
                values: dict[str, object] = {
                    "project_key": p.project_key, "origin": "CORPUS", "analysis_unit_count": p.analysis_unit_count,
                    "finding_count": p.finding_count, "findings_per_unit": p.findings_per_unit,
                }  # fmt: skip
                values.update({f"share_alg_{k.lower()}": v for k, v in p.family_shares.items()})
                values.update({f"share_ctx_{k.lower()}": v for k, v in p.context_shares.items()})
                values.update({f"share_{k.lower()}": v for k, v in p.priority_shares.items()})
                columns = ", ".join(values)
                marks = ", ".join(f":{c}" for c in values)
                connection.execute(text(f"INSERT INTO marts.mart_archetypes ({columns}) VALUES ({marks})"), values)
            rows = [(u.project_key, library, family, False) for u in usages for library, family in u.usages]
            known = {u.project_key for u in usages}
            # projects whose findings are all test code
            rows += [(key(900 + i), "jjwt", "RSA", True) for i in range(max(0, with_findings - len(known)))]
            for found, library, family, in_test in rows:
                connection.execute(
                    text("INSERT INTO marts.mart_risk_features VALUES (:k, 'CORPUS', :l, :f, :t)"),
                    {"k": found, "l": library or "~UNRESOLVED", "f": family, "t": in_test},
                )
            if rows:  # rows of another origin are never read
                connection.execute(
                    text("INSERT INTO marts.mart_risk_features VALUES (:k, 'BENCHMARK', 'x', 'RSA', false)"),
                    {"k": key(999)},
                )
        return PostgresMiningData(database.engine(pg.settings()))

    return factory


@pytest.mark.parametrize("case", DATA_CASES, ids=lambda c: c.__name__)
def test_the_postgres_data_source_keeps_the_contract(case: Callable[[DataFactory], None], pg: PostgresInstance) -> None:
    case(_marts(pg))
    _admin(pg, "DROP SCHEMA IF EXISTS marts CASCADE")


def test_the_application_role_cannot_change_the_techniques(pg: PostgresInstance) -> None:
    assert len(_rows(pg, "SELECT code FROM ml_outputs.mining_technique")) == 4
    with pytest.raises(Exception, match="permission denied"), pg.engine("warehouse_db_app").begin() as connection:
        connection.execute(text("INSERT INTO ml_outputs.mining_technique VALUES ('X', 'x')"))
    with pg.engine("warehouse_db_app").begin() as connection:
        for table in TABLES:
            connection.execute(text(f"SELECT count(*) FROM ml_outputs.{table}"))


def test_the_two_clusterings_are_written_together_or_not_at_all(pg: PostgresInstance, sink: PostgresMiningSink) -> None:
    run = MiningRun("0" * 32, AT, 1, {})
    kept = [TechniqueClusters("HDBSCAN", run, [], [ClusterAssignment(key(1), None)])]
    sink.store_clusters(kept)
    # K-Means may not leave a project without a cluster: the second clustering fails, so the first is not written either.
    bad = [
        TechniqueClusters("HDBSCAN", run, [], [ClusterAssignment(key(2), None)]),
        TechniqueClusters("KMEANS", run, [], [ClusterAssignment(key(2), None)]),
    ]
    with pytest.raises(IntegrityError, match="ck_project_archetype_noise"):
        sink.store_clusters(bad)
    assert _rows(pg, "SELECT technique, project_key FROM ml_outputs.project_archetype") == [("HDBSCAN", key(1))]


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_scores_and_lifts_are_finite_numbers(pg: PostgresInstance, sink: PostgresMiningSink, value: str) -> None:
    _admin(pg, RUN.format(t="ISOLATION_FOREST"), RUN.format(t="FP_GROWTH"))
    with pytest.raises(IntegrityError, match="ck_anomaly_score"):
        _admin(pg, f"INSERT INTO ml_outputs.anomaly VALUES ('ISOLATION_FOREST', '{'a' * 64}', '{value}', false)")
    with pytest.raises(IntegrityError, match="ck_association_rule_lift"):
        _admin(pg, f"INSERT INTO ml_outputs.association_rule VALUES ('FP_GROWTH', 1, 0.5, 0.5, '{value}')")


def test_the_data_is_read_in_one_transaction(pg: PostgresInstance) -> None:
    _marts(pg)([], [], 0)
    engine = database.engine(pg.settings())
    begun: list[str] = []
    event.listen(engine, "begin", lambda connection: begun.append(str(connection.get_isolation_level())))
    PostgresMiningData(engine).snapshot()
    engine.dispose()
    _admin(pg, "DROP SCHEMA IF EXISTS marts CASCADE")
    assert begun == ["REPEATABLE READ"]


def test_a_warehouse_rebuild_cannot_empty_a_running_read(pg: PostgresInstance) -> None:
    """dbt builds a new table and renames it over the old one. Under REPEATABLE READ the new table would show no rows to
    a read that started earlier, so the read locks both marts before its first query and the rebuild waits."""
    _marts(pg)(corpus()[:2], libraries()[:2], 2)
    engine = database.engine(pg.settings())
    rebuild: list[str] = []

    def rebuild_after_the_first_read(
        connection: object, cursor: object, statement: str, parameters: object, context: object, executemany: bool
    ) -> None:
        if rebuild or "FROM marts.mart_archetypes" not in statement:
            return
        try:
            _admin(
                pg,
                "SET LOCAL lock_timeout = '500ms'",
                "CREATE TABLE marts.rebuilt AS SELECT * FROM marts.mart_risk_features",
                "DROP TABLE marts.mart_risk_features",
                "ALTER TABLE marts.rebuilt RENAME TO mart_risk_features",
                "GRANT SELECT ON marts.mart_risk_features TO warehouse_db_app",
            )
            rebuild.append("swapped")
        except OperationalError:
            rebuild.append("waited")

    event.listen(engine, "after_cursor_execute", rebuild_after_the_first_read)
    data = PostgresMiningData(engine).snapshot()
    engine.dispose()
    _admin(pg, "DROP SCHEMA IF EXISTS marts CASCADE")
    assert len(data.libraries) == 2 and data.projects_with_findings == 2
    assert rebuild == ["waited"]

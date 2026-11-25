"""ml_outputs (ml/migrations 0002) and its adapters against a real warehouse_db: schema and grants, storing and replacing
a model version, publication, constraints, the KVKK erasure, and the training data read of the mart."""

from __future__ import annotations

import re
import threading
import time
import uuid
from collections.abc import Callable, Iterator, Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import Connection, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from quancrypt_ml.domain.risk_features import RiskRow
from quancrypt_ml.infrastructure.persistence import database
from quancrypt_ml.infrastructure.persistence.result_sink import (
    INGEST_LOCK_NAMESPACE,
    FindingConflictError,
    PostgresResultSink,
)
from quancrypt_ml.infrastructure.persistence.training_data import PostgresTrainingData
from quancrypt_ml.port.outbound.risk import (
    Attribution,
    MetricValue,
    Prediction,
    ResultSink,
    StoredModel,
    TrainingDataSource,
)
from tests.support.postgres import PostgresInstance
from tests.support.risk_port_cases import DATA_CASES, ERASURE_CASES, SINK_CASES, DataFactory, Reader, Warehouse

pytestmark = pytest.mark.postgres

AT = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)
KEY_A, KEY_B = "a" * 64, "b" * 64
TABLES = ("model_metric", "risk_explanation", "risk_prediction", "published_model", "model_version", "scored_finding")


@pytest.fixture
def sink(pg: PostgresInstance) -> Iterator[PostgresResultSink]:
    with pg.engine("warehouse_db_migrator").begin() as connection:
        connection.execute(text("TRUNCATE " + ", ".join(f"ml_outputs.{t}" for t in TABLES) + " CASCADE"))
        # the erasure tests' stand-in for prep.finding (see _warehouse): absent, so the sink writes every prediction
        connection.execute(text("DROP SCHEMA IF EXISTS prep CASCADE"))
    engine = database.engine(pg.settings())
    yield PostgresResultSink(engine)
    engine.dispose()


def _model(predictions: list[Prediction], version: str = "v1", publish: bool = True) -> StoredModel:
    metrics = [
        MetricValue("CV_FOLD", 1, "MACRO_F1", "ALL", 0.7), MetricValue("CV_MEAN", 0, "MACRO_F1", "ALL", 0.7),
        MetricValue("TEST", 0, "RECALL", "CRITICAL", 0.5),
    ]  # fmt: skip
    return StoredModel("risk_model", version, "XGBOOST", "GOLD", "0" * 32, AT, metrics, predictions, publish)


def _prediction(key: str = KEY_A) -> Prediction:
    explanation = [Attribution("onehot__priority_P0", 0.6), Attribution("flags__in_test_code", -0.2)]
    return Prediction(str(uuid.uuid4()), key, "CRITICAL", 0.8812, explanation)


def _count(pg: PostgresInstance, table: str, where: str = "true", **params: object) -> int:
    with pg.engine("warehouse_db_migrator").begin() as connection:
        return int(
            connection.execute(text(f"SELECT count(*) FROM ml_outputs.{table} WHERE {where}"), params).scalar_one()
        )


def test_the_schema_has_its_tables_and_lookups_and_the_reader_sees_nothing(pg: PostgresInstance) -> None:
    with pg.engine("warehouse_db_migrator").begin() as connection:
        tables = set(
            connection.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'ml_outputs'")).scalars()
        )
    assert {"model_version", "published_model", "scored_finding", "risk_prediction", "risk_explanation", "model_metric",
            "algorithm", "label_source", "metric_scope", "metric", "metric_label", "risk_class"} == tables  # fmt: skip
    with pytest.raises(DBAPIError, match="permission denied"), pg.engine("warehouse_reader").begin() as connection:
        connection.execute(text("SELECT 1 FROM ml_outputs.risk_prediction"))
    with pytest.raises(DBAPIError, match="permission denied"), pg.engine("warehouse_db_app").begin() as connection:
        connection.execute(text("UPDATE ml_outputs.model_version SET version = 'x'"))


def test_a_model_version_is_stored_published_and_replaced_as_a_whole(
    pg: PostgresInstance, sink: PostgresResultSink
) -> None:
    first = [_prediction(), _prediction(KEY_B)]
    sink.store([_model(first)])
    assert (_count(pg, "risk_prediction"), _count(pg, "risk_explanation"), _count(pg, "model_metric")) == (2, 4, 3)
    assert _count(pg, "published_model") == 1
    sink.store([_model([_prediction()])])  # trained again: the old rows go
    assert (_count(pg, "model_version"), _count(pg, "risk_prediction"), _count(pg, "risk_explanation")) == (1, 1, 2)
    sink.store([_model([], version="v2")])  # another version takes the publication
    with pg.engine("warehouse_db_migrator").begin() as connection:
        published = connection.execute(
            text(
                "SELECT v.version FROM ml_outputs.published_model p JOIN ml_outputs.model_version v ON v.id = p.model_version_id"
            )
        ).scalar_one()
    assert published == "v2" and _count(pg, "model_version") == 2


def test_a_baseline_is_stored_without_predictions_and_unpublished(
    pg: PostgresInstance, sink: PostgresResultSink
) -> None:
    sink.store(
        [
            StoredModel(
                "rule_baseline",
                "v1",
                "RULE_BASELINE",
                "GOLD",
                None,
                AT,
                [MetricValue("TEST", 0, "MACRO_F1", "ALL", 0.6)],
                [],
                False,
            )
        ]
    )
    assert (_count(pg, "model_version"), _count(pg, "published_model"), _count(pg, "model_metric")) == (1, 0, 1)


def test_a_finding_with_another_project_key_is_refused_and_nothing_is_written(
    pg: PostgresInstance, sink: PostgresResultSink
) -> None:
    prediction = _prediction()
    sink.store([_model([prediction])])
    moved = Prediction(prediction.finding_id, KEY_B, "LOW", 0.2, [])
    with pytest.raises(FindingConflictError):
        sink.store([_model([moved], version="v2")])
    assert _count(pg, "model_version", "version = 'v2'") == 0


def test_the_kvkk_erasure_of_a_project_key_takes_its_predictions_and_explanations(
    pg: PostgresInstance, sink: PostgresResultSink
) -> None:
    sink.store([_model([_prediction(KEY_A), _prediction(KEY_A), _prediction(KEY_B)])])
    # The statement data-platform's eraser runs for the registered table (application role, D-327d).
    with pg.engine("warehouse_db_app").begin() as connection:
        deleted = connection.execute(
            text("DELETE FROM ml_outputs.scored_finding WHERE project_key = :k"), {"k": KEY_A}
        ).rowcount
    assert deleted == 2
    assert (_count(pg, "risk_prediction"), _count(pg, "risk_explanation")) == (1, 2)
    assert _count(pg, "model_version") == 1 and _count(pg, "model_metric") == 3  # metrics hold no project data


@pytest.mark.parametrize(
    ("statement", "constraint"),
    [
        ("INSERT INTO ml_outputs.model_metric VALUES (:v, 'CV_FOLD', 0, 'MACRO_F1', 'ALL', 1)", "ck_model_metric_fold"),
        ("INSERT INTO ml_outputs.model_metric VALUES (:v, 'TEST', 2, 'MACRO_F1', 'ALL', 1)", "ck_model_metric_fold"),
        ("INSERT INTO ml_outputs.model_metric VALUES (:v, 'TEST', 0, 'LOSS', 'ALL', 1)", "fk_model_metric_metric"),
        ("INSERT INTO ml_outputs.risk_prediction VALUES (:v, :f, 'LOW', 1.5)", "ck_risk_prediction_score"),
        ("INSERT INTO ml_outputs.risk_prediction VALUES (:v, :g, 'SEVERE', 0.5)", "fk_risk_prediction_class"),
        ("INSERT INTO ml_outputs.risk_explanation VALUES (:v, :f, 4, 'x', 0.1)", "ck_risk_explanation_rank"),
        ("INSERT INTO ml_outputs.risk_explanation VALUES (:v, :f, 3, 'bad feature', 0.1)", "ck_risk_explanation_feature"),
        ("INSERT INTO ml_outputs.model_version VALUES (gen_random_uuid(), 'Risk Model', 'v1', 'XGBOOST', 'GOLD', NULL, now())", "ck_model_version_name"),
        ("INSERT INTO ml_outputs.scored_finding VALUES (gen_random_uuid(), 'x')", "ck_scored_finding_project_key"),
    ],
)  # fmt: skip
def test_every_constraint_refuses_what_it_guards(
    pg: PostgresInstance, sink: PostgresResultSink, statement: str, constraint: str
) -> None:
    prediction = _prediction()
    sink.store([_model([prediction])])
    unscored = str(uuid.uuid4())  # a scored finding without a prediction yet
    with pg.engine("warehouse_db_migrator").begin() as connection:
        version = connection.execute(text("SELECT id FROM ml_outputs.model_version")).scalar_one()
        connection.execute(text("INSERT INTO ml_outputs.scored_finding VALUES (:g, :k)"), {"g": unscored, "k": KEY_A})
    with pytest.raises(IntegrityError, match=constraint), pg.engine("warehouse_db_app").begin() as connection:
        connection.execute(text(statement), {"v": version, "f": prediction.finding_id, "g": unscored})


def _mart(pg: PostgresInstance) -> None:
    """marts.mart_risk_features with the columns the training data reads (the shape dbt gives it, P7.1 + P7.2)."""
    with pg.engine("warehouse_db_migrator").begin() as connection:
        for statement in (
            "CREATE SCHEMA IF NOT EXISTS marts",
            "DROP TABLE IF EXISTS marts.mart_risk_features",
            "CREATE TABLE marts.mart_risk_features (finding_id uuid, project_key char(64), algorithm_family varchar(32), "
            "quantum_status varchar(32), usage_context varchar(32), location_kind varchar(32), priority varchar(16), "
            "key_size_bits integer, mode varchar(64), padding varchar(64), hash varchar(64), library varchar(64), "
            "confidence numeric(4,3), in_test_code boolean, hndl_exposure boolean, is_outlier_project boolean, "
            "java_major integer, spring_boot_version varchar(32), project_finding_count bigint, gold_label varchar(16), "
            "silver_label varchar(16))",
            "GRANT USAGE ON SCHEMA marts TO warehouse_db_app",
            "GRANT SELECT ON marts.mart_risk_features TO warehouse_db_app",
        ):
            connection.execute(text(statement))


def test_the_training_data_reads_the_mart_with_its_labels(pg: PostgresInstance) -> None:
    with pg.engine("warehouse_db_migrator").begin() as connection:
        for statement in (
            "CREATE SCHEMA IF NOT EXISTS marts",
            "DROP TABLE IF EXISTS marts.mart_risk_features",
            "CREATE TABLE marts.mart_risk_features (finding_id uuid, project_key char(64), algorithm_family varchar(32), "
            "quantum_status varchar(32), usage_context varchar(32), location_kind varchar(32), priority varchar(16), "
            "key_size_bits integer, mode varchar(64), padding varchar(64), hash varchar(64), library varchar(64), "
            "confidence numeric(4,3), in_test_code boolean, hndl_exposure boolean, is_outlier_project boolean, "
            "java_major integer, spring_boot_version varchar(32), project_finding_count bigint, gold_label varchar(16), "
            "silver_label varchar(16))",
            "GRANT USAGE ON SCHEMA marts TO warehouse_db_app",
            "GRANT SELECT ON marts.mart_risk_features TO warehouse_db_app",
            f"INSERT INTO marts.mart_risk_features VALUES ('{uuid.uuid4()}', '{KEY_A}', 'RSA', 'VULNERABLE', "
            "'TLS_KEY_EXCHANGE', 'CODE', 'P1', NULL, NULL, NULL, NULL, 'JCA', 0.9, false, true, false, 21, '3.3.1', 12, "
            "NULL, 'HIGH')",
        ):
            connection.execute(text(statement))
    engine = database.engine(pg.settings())
    rows = PostgresTrainingData(engine).rows()
    engine.dispose()
    assert len(rows) == 1
    row = rows[0]
    assert (row.priority, row.key_size_bits, row.java_major, row.gold_label, row.silver_label, row.confidence) == (
        "P1", None, 21, None, "HIGH", 0.9,
    )  # fmt: skip


# ---------------------------------------------------------------- the shared port contracts on PostgreSQL


def _read_state(pg: PostgresInstance) -> Callable[[], dict[tuple[str, str], dict[str, object]]]:
    def read() -> dict[tuple[str, str], dict[str, object]]:
        with pg.engine("warehouse_db_migrator").begin() as connection:
            versions = connection.execute(
                text(
                    "SELECT v.id, v.model_name, v.version, p.model_version_id IS NOT NULL, "
                    "(SELECT count(*) FROM ml_outputs.model_metric m WHERE m.model_version_id = v.id) "
                    "FROM ml_outputs.model_version v LEFT JOIN ml_outputs.published_model p ON p.model_version_id = v.id"
                )
            ).all()
            state: dict[tuple[str, str], dict[str, object]] = {}
            for version_id, name, version, published, metrics in versions:
                predictions = connection.execute(
                    text(
                        "SELECT finding_id::text, risk_class FROM ml_outputs.risk_prediction WHERE model_version_id = :v"
                    ),
                    {"v": version_id},
                ).all()
                state[(name, version)] = {
                    "predictions": {str(f): str(c) for f, c in predictions}, "published": bool(published), "metrics": int(metrics),
                }  # fmt: skip
        return state

    return read


@pytest.mark.parametrize("case", SINK_CASES, ids=lambda c: c.__name__)
def test_the_postgres_sink_keeps_the_contract(
    pg: PostgresInstance, sink: PostgresResultSink, case: Callable[[ResultSink, Reader], None]
) -> None:
    case(sink, _read_state(pg))


@pytest.mark.parametrize("case", DATA_CASES, ids=lambda c: c.__name__)
def test_the_postgres_training_data_keeps_the_contract(
    pg: PostgresInstance, case: Callable[[DataFactory], None]
) -> None:
    engine = database.engine(pg.settings())

    def factory(rows: Sequence[RiskRow]) -> TrainingDataSource:
        _mart(pg)
        with pg.engine("warehouse_db_migrator").begin() as connection:
            for r in rows:
                connection.execute(
                    text(
                        "INSERT INTO marts.mart_risk_features VALUES (:f, :k, :a, :q, :u, :l, :p, :ks, :m, :pad, :h, :lib, "
                        ":c, :t, :hn, :o, :j, :sb, :n, :g, :s)"
                    ),
                    {
                        "f": r.finding_id,
                        "k": r.project_key,
                        "a": r.algorithm_family,
                        "q": r.quantum_status,
                        "u": r.usage_context,
                        "l": r.location_kind,
                        "p": r.priority,
                        "ks": r.key_size_bits,
                        "m": r.mode,
                        "pad": r.padding,
                        "h": r.hash,
                        "lib": r.library,
                        "c": r.confidence,
                        "t": r.in_test_code,
                        "hn": r.hndl_exposure,
                        "o": r.is_outlier_project,
                        "j": r.java_major,
                        "sb": r.spring_boot_version,
                        "n": r.project_finding_count,
                        "g": r.gold_label,
                        "s": r.silver_label,
                    },  # fmt: skip
                )
        return PostgresTrainingData(engine)

    case(factory)
    engine.dispose()


def _warehouse(pg: PostgresInstance) -> Warehouse:
    """A stand-in for data-platform's prep.finding (the one column the sink reads, and the key; the real table is
    data-platform migration 0003) and a committed KVKK erasure of a key."""
    with pg.engine("warehouse_db_migrator").begin() as connection:
        connection.execute(text("CREATE SCHEMA IF NOT EXISTS prep"))
        connection.execute(
            text("CREATE TABLE IF NOT EXISTS prep.finding (id uuid PRIMARY KEY, project_key char(64) NOT NULL)")
        )
        connection.execute(text("GRANT USAGE ON SCHEMA prep TO warehouse_db_app"))
        connection.execute(text("GRANT SELECT ON prep.finding TO warehouse_db_app"))

    def present(findings: Sequence[tuple[str, str]]) -> None:
        with pg.engine("warehouse_db_migrator").begin() as connection:
            for finding, key in findings:
                connection.execute(text("INSERT INTO prep.finding VALUES (:f, :k)"), {"f": finding, "k": key})

    def erase(project_key: str) -> None:
        with pg.engine("warehouse_db_migrator").begin() as connection:
            connection.execute(text("DELETE FROM prep.finding WHERE project_key = :k"), {"k": project_key})
            connection.execute(text("DELETE FROM ml_outputs.scored_finding WHERE project_key = :k"), {"k": project_key})

    return Warehouse(present, erase)


@pytest.mark.parametrize("case", ERASURE_CASES, ids=lambda c: c.__name__)
def test_the_postgres_sink_keeps_the_erasure_contract(
    pg: PostgresInstance, sink: PostgresResultSink, case: Callable[[ResultSink, Reader, Warehouse], None]
) -> None:
    case(sink, _read_state(pg), _warehouse(pg))


def _hold_key_lock(holder: Connection, key: str) -> None:
    holder.execute(text("BEGIN"))
    holder.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:n, 0))"), {"n": INGEST_LOCK_NAMESPACE + key})


def test_a_run_waits_for_an_erasure_that_holds_the_key_lock_and_then_leaves_its_findings_out(
    pg: PostgresInstance, sink: PostgresResultSink
) -> None:
    """D-331: an erasure that holds the key lock and commits while store waits is seen (state, not a clock)."""
    warehouse = _warehouse(pg)
    kept, erased = _prediction(KEY_A), _prediction(KEY_B)
    warehouse.present([(kept.finding_id, KEY_A), (erased.finding_id, KEY_B)])
    result: list[int] = []
    with pg.engine("warehouse_db_migrator").connect() as holder:
        _hold_key_lock(holder, KEY_B)
        holder.execute(text("DELETE FROM prep.finding WHERE project_key = :k"), {"k": KEY_B})
        worker = threading.Thread(target=lambda: result.append(sink.store([_model([kept, erased])])))
        worker.start()
        time.sleep(1.0)
        assert worker.is_alive() and _count(pg, "model_version") == 0  # store waits for the erasure
        holder.execute(text("COMMIT"))
        worker.join(10)
    assert result == [1]
    assert _count(pg, "risk_prediction") == 1 and _count(pg, "scored_finding", "project_key = :k", k=KEY_B) == 0


def test_a_run_gives_up_writing_nothing_when_an_erasure_holds_the_key_lock_too_long(
    pg: PostgresInstance, sink: PostgresResultSink
) -> None:
    with pg.engine("warehouse_db_migrator").connect() as holder:
        _hold_key_lock(holder, KEY_A)
        with pytest.raises(DBAPIError):
            sink.store([_model([_prediction(KEY_A)])])  # the session lock timeout (5 s)
        holder.execute(text("ROLLBACK"))
    assert _count(pg, "model_version") == 0


def test_the_key_lock_name_is_data_platforms() -> None:
    """The erasure's lock name (data-platform repositories.LOCK_NAMESPACE) and the sink's are one name."""
    source = (Path(__file__).resolve().parents[3] / "data-platform" / "src" / "quancrypt_data" / "infrastructure"
              / "persistence" / "repositories.py").read_text(encoding="utf-8")  # fmt: skip
    match = re.search(r'^LOCK_NAMESPACE = "([^"]+)"$', source, re.M)
    assert match is not None and match.group(1) == INGEST_LOCK_NAMESPACE


def test_model_b_codes_are_in_the_lookups_and_a_scope_version_is_stored(
    pg: PostgresInstance, sink: PostgresResultSink
) -> None:
    """ml migration 0003 (P7.3, D-333f): Model B's codes; a scope classifier version holds metrics and no predictions."""
    expected = {
        "algorithm": {"LINEAR_SVM"}, "label_source": {"SCOPE_SET"}, "metric_scope": {"VALIDATION"},
        "metric": {"OUT_OF_SCOPE_RECALL", "FALSE_REJECT_RATE", "UNSURE_RATE", "THRESHOLD", "UNSURE_LOW", "UNSURE_HIGH",
                   "ROC_AUC"},
        "metric_label": {"TR", "EN", "JAILBREAK", "BOUNDARY"},
    }  # fmt: skip
    with pg.engine("warehouse_db_migrator").begin() as connection:
        for table, codes in expected.items():
            present = set(connection.execute(text(f"SELECT code FROM ml_outputs.{table}")).scalars())
            assert codes <= present, table
    metrics = [
        MetricValue("VALIDATION", 0, "THRESHOLD", "ALL", 0.42), MetricValue("TEST", 0, "OUT_OF_SCOPE_RECALL", "TR", 1.0),
        MetricValue("TEST", 0, "FALSE_REJECT_RATE", "BOUNDARY", 0.125),
    ]  # fmt: skip
    sink.store([StoredModel("scope_classifier", "v1", "LINEAR_SVM", "SCOPE_SET", "0" * 32, AT, metrics, [], True)])
    assert _count(pg, "model_metric") == 3 and _count(pg, "risk_prediction") == 0
    assert _count(pg, "model_version", "label_source = 'SCOPE_SET' AND algorithm = 'LINEAR_SVM'") == 1
    assert _count(pg, "published_model", "model_name = 'scope_classifier'") == 1

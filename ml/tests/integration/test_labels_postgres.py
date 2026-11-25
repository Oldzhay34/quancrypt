"""The labels schema and the PostgreSQL adapters against a real warehouse_db (acid-3nf-database section 7): migration,
constraints, the LabelStore contract, atomicity, the KVKK erasure, concurrent imports, and the candidate and location
reads of the export."""

from __future__ import annotations

import json
import threading
import uuid
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from quancrypt_ml.domain.labels import FIRST, SECOND, Candidate, LabelRecord, Resolution, SourceLocation
from quancrypt_ml.infrastructure.persistence import database
from quancrypt_ml.infrastructure.persistence.candidates import PostgresCandidateSource
from quancrypt_ml.infrastructure.persistence.label_store import PostgresLabelStore
from quancrypt_ml.infrastructure.persistence.locator import PostgresSourceLocator, corpus_key, row_id
from quancrypt_ml.port.outbound.labeling import LabelStore, SourceLocator
from tests.support.label_store_cases import AT, CASES, KEY, new_batch
from tests.support.port_cases import CANDIDATE_CASES, LOCATOR_CASES, CandidateFactory, LocatorFactory
from tests.support.postgres import MIGRATIONS_DIR, PostgresInstance

pytestmark = pytest.mark.postgres

SALT = "s" * 40
TABLES = ("gold_label", "label_resolution", "label_batch_item", "label_batch", "labeled_finding", "labeler")


@pytest.fixture
def store(pg: PostgresInstance) -> Iterator[PostgresLabelStore]:
    with pg.engine("warehouse_db_migrator").begin() as connection:
        connection.execute(text("TRUNCATE " + ", ".join(f"labels.{t}" for t in TABLES) + " CASCADE"))
    engine = database.engine(pg.settings())
    yield PostgresLabelStore(engine)
    engine.dispose()


def test_the_migration_creates_the_schema_once_with_its_own_version_table(pg: PostgresInstance) -> None:
    database.migrate(pg.settings(migrator=True), MIGRATIONS_DIR)  # a second run changes nothing
    with pg.engine("warehouse_db_migrator").begin() as connection:
        tables = connection.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'labels' ORDER BY tablename")
        ).scalars()
        assert list(tables) == sorted(["gold_label", "label_batch", "label_batch_item", "label_resolution",
                                       "labeled_finding", "labeler", "labeler_role", "risk_class"])  # fmt: skip
        # The head of the chain (0002 adds ml_outputs, P7.2).
        assert connection.execute(text("SELECT version_num FROM public.ml_alembic_version")).scalar_one() == "0002"
        classes = connection.execute(text("SELECT code FROM labels.risk_class ORDER BY sort_order")).scalars()
        assert list(classes) == ["CRITICAL", "HIGH", "MEDIUM", "LOW"]


def test_the_reader_sees_nothing_and_the_application_role_cannot_change_the_schema(pg: PostgresInstance) -> None:
    with pytest.raises(DBAPIError, match="permission denied"), pg.engine("warehouse_reader").begin() as connection:
        connection.execute(text("SELECT 1 FROM labels.gold_label"))
    with pytest.raises(DBAPIError, match="permission denied"), pg.engine("warehouse_db_app").begin() as connection:
        connection.execute(text("CREATE TABLE labels.x (id int)"))
    with pytest.raises(DBAPIError, match="permission denied"), pg.engine("warehouse_db_app").begin() as connection:
        connection.execute(text("INSERT INTO labels.risk_class VALUES ('NEW', 'x', 9)"))
    for statement in (
        "UPDATE public.ml_alembic_version SET version_num = '0000'",
        "DELETE FROM public.ml_alembic_version",
        "INSERT INTO public.ml_alembic_version VALUES ('9999')",
    ):
        with pytest.raises(DBAPIError, match="permission denied"), pg.engine("warehouse_db_app").begin() as connection:
            connection.execute(text(statement))


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.__name__)
def test_the_postgres_label_store_keeps_the_contract(
    store: PostgresLabelStore, case: Callable[[LabelStore], None]
) -> None:
    case(store)


@pytest.mark.parametrize(
    ("statement", "constraint"),
    [
        ("INSERT INTO labels.label_batch VALUES (gen_random_uuid(), 'Batch 1', now(), 1)", "ck_label_batch_name"),
        ("INSERT INTO labels.labeled_finding VALUES (gen_random_uuid(), 'XYZ')", "ck_labeled_finding_project_key"),
        ("INSERT INTO labels.label_batch_item VALUES (gen_random_uuid(), :finding, false)",
         "fk_label_batch_item_batch"),
        ("INSERT INTO labels.label_batch_item VALUES (:batch, gen_random_uuid(), false)",
         "fk_label_batch_item_finding"),
        ("INSERT INTO labels.gold_label VALUES (:batch, :finding, 'FIRST', :labeler, 'SEVERE', NULL, now())",
         "fk_gold_label_risk_class"),
        ("INSERT INTO labels.gold_label VALUES (:batch, :finding, 'THIRD', :labeler, 'LOW', NULL, now())",
         "fk_gold_label_role"),
        ("INSERT INTO labels.gold_label VALUES (:batch, :finding, 'FIRST', :labeler, 'LOW', ' x', now())",
         "ck_gold_label_notes"),
        ("INSERT INTO labels.gold_label VALUES (:batch, gen_random_uuid(), 'FIRST', :labeler, 'LOW', NULL, now())",
         "fk_gold_label_item"),
        ("INSERT INTO labels.labeler VALUES (gen_random_uuid(), ' olcay')", "ck_labeler_name"),
        ("INSERT INTO labels.labeler VALUES (gen_random_uuid(), 'olcay')", "uq_labeler_name"),
    ],
)  # fmt: skip
def test_every_constraint_refuses_what_it_guards(
    pg: PostgresInstance, store: PostgresLabelStore, statement: str, constraint: str
) -> None:
    batch = new_batch()
    store.create_batch(batch)
    store.replace_labels(batch.id, FIRST, [LabelRecord(batch.items[0][0], "LOW", "olcay", None)], AT)
    with pg.engine("warehouse_db_app").begin() as connection:
        labeler = connection.execute(text("SELECT id FROM labels.labeler")).scalar_one()
    params = {"batch": batch.id, "finding": batch.items[1][0], "labeler": labeler, "key": KEY}
    with pytest.raises(IntegrityError, match=constraint), pg.engine("warehouse_db_app").begin() as connection:
        connection.execute(text(statement), params)


def test_the_kvkk_erasure_of_a_project_key_takes_its_items_labels_and_resolutions(
    pg: PostgresInstance, store: PostgresLabelStore
) -> None:
    batch = new_batch(size=6)  # odd positions carry KEY
    store.create_batch(batch)
    ids = [f for f, _, _ in batch.items]
    store.replace_labels(batch.id, FIRST, [LabelRecord(f, "HIGH", "olcay", None) for f in ids], AT)
    store.replace_labels(batch.id, SECOND, [LabelRecord(ids[1], "LOW", "arkadas", None)], AT)
    store.replace_resolutions(batch.id, [Resolution(ids[1], "LOW", "olcay", None)], AT)
    # The statement data-platform's eraser runs for the registered table (application role, D-322g, D-324a).
    with pg.engine("warehouse_db_app").begin() as connection:
        deleted = connection.execute(
            text("DELETE FROM labels.labeled_finding WHERE project_key = :key"), {"key": KEY}
        ).rowcount
    assert deleted == 3
    kept = {f for f, k, _ in batch.items if k != KEY}
    assert set(store.labels(batch.id, FIRST)) == kept
    assert store.resolutions(batch.id) == {}
    stored = store.batch("batch_001")
    assert stored is not None and set(stored.items) == kept


def test_two_imports_of_one_labeller_at_once_leave_one_of_them_whole(store: PostgresLabelStore) -> None:
    batch = new_batch(size=40)
    store.create_batch(batch)
    ids = [f for f, _, _ in batch.items]
    errors: list[BaseException] = []

    def run(label: str) -> None:
        try:
            for _ in range(5):
                store.replace_labels(batch.id, FIRST, [LabelRecord(f, label, f"kişi {label}", None) for f in ids], AT)
        except BaseException as error:  # noqa: BLE001 (collected and asserted below)
            errors.append(error)

    threads = [threading.Thread(target=run, args=(label,)) for label in ("HIGH", "LOW")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    labels = store.labels(batch.id, FIRST)
    assert set(labels) == set(ids) and len(set(labels.values())) == 1


def _warehouse_tables(pg: PostgresInstance) -> None:
    """The three relations the export reads, in the shape data-platform and dbt give them (prep 0003, raw 0001, the
    mart of P6.6 + P7.1), created by the migrator and readable by the application role."""
    with pg.engine("warehouse_db_migrator").begin() as connection:
        for statement in (
            "CREATE SCHEMA IF NOT EXISTS raw",
            "CREATE SCHEMA IF NOT EXISTS prep",
            "CREATE SCHEMA IF NOT EXISTS marts",
            "DROP TABLE IF EXISTS raw.event, prep.finding, marts.mart_risk_features",
            "CREATE TABLE raw.event (event_id uuid PRIMARY KEY, event_type varchar(32) NOT NULL, project_key char(64) "
            "NOT NULL, payload jsonb NOT NULL)",
            "CREATE TABLE prep.finding (id uuid PRIMARY KEY, project_key char(64) NOT NULL, source_event_id uuid NOT NULL)",
            "CREATE TABLE marts.mart_risk_features (finding_id uuid, project_key char(64), origin varchar(16), "
            "algorithm_family varchar(32), quantum_status varchar(32), usage_context varchar(32), location_kind varchar(32), "
            "priority varchar(16), key_size_bits integer, mode varchar(64), padding varchar(64), hash varchar(64), "
            "library varchar(64), confidence numeric(4,3), in_test_code boolean, hndl_exposure boolean)",
            "GRANT USAGE ON SCHEMA raw, prep, marts TO warehouse_db_app",
            "GRANT SELECT ON raw.event, prep.finding, marts.mart_risk_features TO warehouse_db_app",
        ):
            connection.execute(text(statement))


def test_the_export_reads_candidates_and_the_real_location_of_a_corpus_finding(
    pg: PostgresInstance, tmp_path: Path
) -> None:
    _warehouse_tables(pg)
    key = corpus_key(SALT, "acme", "shop")
    event, other = str(uuid.uuid4()), str(uuid.uuid4())
    found, user = row_id(event, 1), str(uuid.uuid4())
    payload = {"analysis_unit": "payment", "findings": [{"file": "A.java", "line_start": 1},
                                                        {"file": "src/B.java", "line_start": 7}]}  # fmt: skip
    with pg.engine("warehouse_db_migrator").begin() as connection:
        connection.execute(
            text("INSERT INTO raw.event VALUES (:e, 'corpus_analysis', :k, CAST(:p AS jsonb)), "
                 "(:o, 'finding_detected', :k, CAST('{}' AS jsonb))"),
            {"e": event, "o": other, "k": key, "p": json.dumps(payload)},
        )  # fmt: skip
        connection.execute(
            text("INSERT INTO prep.finding VALUES (:f, :k, :e), (:u, :k, :o)"),
            {"f": found, "u": user, "k": key, "e": event, "o": other},
        )
        connection.execute(
            text("INSERT INTO marts.mart_risk_features VALUES (:f, :k, 'CORPUS', 'RSA', 'VULNERABLE', 'ENCRYPTION', "
                 "'CODE', 'P1', 2048, NULL, 'OAEP', 'SHA-256', 'JCA', 0.9, false, true)"),
            {"f": found, "k": key},
        )  # fmt: skip
    manifest = tmp_path / "corpus_manifest.csv"
    manifest.write_text("repo_url,status\nhttps://github.com/Acme/Shop,analyzed\n", encoding="utf-8")
    engine = database.engine(pg.settings())
    candidates = PostgresCandidateSource(engine)
    rows = candidates.candidates()
    assert [(c.finding_id, c.algorithm_family, c.confidence, c.hndl_exposure) for c in rows] == [
        (found, "RSA", 0.9, True)
    ]
    assert candidates.known([found, user]) == {found}
    located = PostgresSourceLocator(engine, SALT, manifest).locate([found, user])
    assert {f: (loc.root, loc.path, loc.line) for f, loc in located.items()} == {
        found: ("/corpus/acme__shop/payment", "src/B.java", 7)
    }
    engine.dispose()


def test_bound_values_never_reach_a_database_error_message(pg: PostgresInstance, store: PostgresLabelStore) -> None:
    batch = new_batch()
    store.create_batch(batch)
    secret_note = "gizli-not-" + "x" * 600  # longer than the column: the insert fails
    with pytest.raises(DBAPIError) as error:
        store.replace_labels(batch.id, FIRST, [LabelRecord(batch.items[0][0], "LOW", "olcay", secret_note)], AT)
    assert "gizli-not" not in str(error.value)


# ---------------------------------------------------------------- the shared port contracts on PostgreSQL


def _insert_candidates(pg: PostgresInstance, rows: Sequence[Candidate]) -> None:
    columns = (
        "finding_id, project_key, origin, algorithm_family, quantum_status, usage_context, location_kind, priority, "
        "key_size_bits, mode, padding, hash, library, confidence, in_test_code, hndl_exposure"
    )
    with pg.engine("warehouse_db_migrator").begin() as connection:
        for c in rows:
            connection.execute(
                text(f"INSERT INTO marts.mart_risk_features ({columns}) VALUES (:f, :k, :o, :a, :q, :u, :l, :p, :ks, "
                     ":m, :pad, :h, :lib, :conf, :t, :hn)"),
                {"f": c.finding_id, "k": c.project_key, "o": c.origin, "a": c.algorithm_family, "q": c.quantum_status,
                 "u": c.usage_context, "l": c.location_kind, "p": c.priority, "ks": c.key_size_bits, "m": c.mode,
                 "pad": c.padding, "h": c.hash, "lib": c.library, "conf": c.confidence, "t": c.in_test_code,
                 "hn": c.hndl_exposure},
            )  # fmt: skip


@pytest.mark.parametrize("case", CANDIDATE_CASES, ids=lambda c: c.__name__)
def test_the_postgres_candidate_source_keeps_the_contract(
    pg: PostgresInstance, case: Callable[[CandidateFactory], None]
) -> None:
    _warehouse_tables(pg)
    engine = database.engine(pg.settings())

    def factory(rows: Sequence[Candidate]) -> PostgresCandidateSource:
        _insert_candidates(pg, rows)
        return PostgresCandidateSource(engine)

    case(factory)
    engine.dispose()


@pytest.mark.parametrize("case", LOCATOR_CASES, ids=lambda c: c.__name__)
def test_the_postgres_locator_keeps_the_contract(
    pg: PostgresInstance, tmp_path: Path, case: Callable[[LocatorFactory], None]
) -> None:
    """Each location becomes the raw corpus event and the prep finding it would come from (unit, file, line)."""
    _warehouse_tables(pg)
    manifest = tmp_path / "corpus_manifest.csv"
    manifest.write_text("repo_url,status\nhttps://github.com/acme/shop,analyzed\n", encoding="utf-8")
    key = corpus_key(SALT, "acme", "shop")
    engine = database.engine(pg.settings())

    def factory(locations: Sequence[SourceLocation]) -> tuple[SourceLocator, list[str]]:
        ids: list[str] = []
        with pg.engine("warehouse_db_migrator").begin() as connection:
            for location in locations:
                event = str(uuid.uuid4())
                unit = location.root.removeprefix("/corpus/acme__shop").lstrip("/") or "."
                payload = {"analysis_unit": unit, "findings": [{"file": location.path, "line_start": location.line}]}
                connection.execute(
                    text("INSERT INTO raw.event VALUES (:e, 'corpus_analysis', :k, CAST(:p AS jsonb))"),
                    {"e": event, "k": key, "p": json.dumps(payload)},
                )
                # The id prep gives the first finding of the event (data-platform row_id).
                ids.append(row_id(event, 0))
                connection.execute(
                    text("INSERT INTO prep.finding VALUES (:f, :k, :e)"), {"f": ids[-1], "k": key, "e": event}
                )
        return PostgresSourceLocator(engine, SALT, manifest), ids

    case(factory)
    engine.dispose()

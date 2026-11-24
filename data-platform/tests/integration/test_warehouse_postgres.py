"""The warehouse (P6.6): the real dbt project built against a real PostgreSQL after the real pipeline (ingest, preprocess).

Needs Docker (the throw-away PostgreSQL) and `make warehouse-deps` once (dbt_utils). dbt runs as the child process the
command line uses, in its own environment (requirements-dbt.txt)."""

from __future__ import annotations

import os
import subprocess
import tempfile
import threading
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from quancrypt_data.infrastructure.persistence.repositories import StaticProjectKeyTableRegistry
from quancrypt_data.infrastructure.persistence.warehouse_lock import PostgresWarehouseBuildLock
from quancrypt_data.infrastructure.warehouse.dbt_cli_builder import DbtCliBuilder, DbtConnection
from quancrypt_data.port.outbound.warehouse import WarehouseBusyError
from quancrypt_data.usecase.build_warehouse_service import BuildWarehouseService
from tests.conftest import Stack
from tests.integration.test_prep_postgres import CORPUS_KEY, corpus_events, corpus_finding, ingest, pipeline, rows
from tests.support.envelopes import KEY_A, KEY_B, envelope

DATA_PLATFORM = Path(__file__).resolve().parents[2]
PROJECT = DATA_PLATFORM / "dbt" / "quancrypt_dw"
DBT = (
    "uv",
    "run",
    "--python",
    "3.12",
    "--no-project",
    "--with-requirements",
    str(DATA_PLATFORM / "requirements-dbt.txt"),
    "dbt",
)
WAREHOUSE_SCHEMAS = "staging, snapshots, core, marts"
FACTS = ("core.fact_crypto_finding", "core.fact_topology_summary", "core.fact_service_link", "core.fact_scope_decision")
WAREHOUSE_TABLES_WITH_KEY = (
    "marts.mart_inventory_summary", "marts.mart_service_runtime", "marts.mart_topology_coverage",
    "marts.mart_risk_features", *FACTS, "core.fact_migration_step", "core.dim_service", "core.dim_project",
    "snapshots.dim_service_snapshot", "snapshots.dim_project_snapshot",
)  # fmt: skip


def revoked(key: str, at: datetime | None = None) -> dict[str, object]:
    when = (at or datetime.now(UTC)).isoformat().replace("+00:00", "Z")
    return envelope("consent_revoked", project_key=key, occurred_at=when, event_id=str(uuid.uuid4()))


def build_service(stack: Stack, wait_s: float = 30.0) -> BuildWarehouseService:
    instance = stack.instance
    connection = DbtConnection(
        "127.0.0.1", instance.port, "warehouse_db_migrator", instance.migrator_password, "warehouse_db"
    )
    return BuildWarehouseService(
        PostgresWarehouseBuildLock(instance.settings(), wait_s), DbtCliBuilder(PROJECT, DBT, connection, timeout_s=900)
    )


def run_dbt(stack: Stack, *args: str) -> subprocess.CompletedProcess[bytes]:
    """A dbt command of the project against the throw-away database, with the environment the command line gives it."""
    instance = stack.instance
    with tempfile.TemporaryDirectory() as profiles:
        (Path(profiles) / "profiles.yml").write_text((PROJECT / "profiles.yml.example").read_text())
        environment = {
            **{k: v for k, v in os.environ.items() if k in ("PATH", "HOME")},
            "DBT_USER": "warehouse_db_migrator", "DBT_PASSWORD": instance.migrator_password, "DBT_PORT": str(instance.port),
            "DBT_SEND_ANONYMOUS_USAGE_STATS": "false",
        }  # fmt: skip
        return subprocess.run(  # noqa: S603
            [*DBT, *args, "--project-dir", str(PROJECT), "--profiles-dir", profiles],
            env=environment, capture_output=True, check=False,
        )  # fmt: skip


@pytest.fixture
def warehouse(stack: Stack) -> Iterator[Stack]:
    """The stack with the warehouse schemas dropped (dbt builds them from nothing) before and after."""
    assert (PROJECT / "dbt_packages" / "dbt_utils").is_dir(), "run `make warehouse-deps` once (dbt deps)"
    drop = text(f"DROP SCHEMA IF EXISTS {WAREHOUSE_SCHEMAS} CASCADE")
    with stack.instance.migrator_engine().begin() as connection:
        connection.execute(drop)
    yield stack
    with stack.instance.migrator_engine().begin() as connection:
        connection.execute(drop)


def count(engine: Engine, table: str, where: str = "true", **params: Any) -> int:
    return int(rows(engine, f"SELECT count(*) FROM {table} WHERE {where}", **params)[0][0])  # noqa: S608


def seed_and_prepare(stack: Stack, tmp_path: Path) -> None:
    """A corpus project (two findings of its own) and a user project (every kind of core and agent event) through the real
    ingest and preprocessing."""
    ingest(
        stack,
        *corpus_events(CORPUS_KEY, corpus_finding(), corpus_finding("src/main/java/Other.java", line=9, hash="SHA-256")),
        envelope("finding_detected"), envelope("topology_recorded"), envelope("project_runtime_changed"),
        envelope("scope_decision"), envelope("scope_decision", event_id=str(uuid.uuid4()), payload={"decision": "DENY"}),
    )  # fmt: skip
    pipeline(stack, tmp_path).execute()


class TestBuild:
    def test_dbt_builds_every_model_and_every_test_passes(self, warehouse: Stack, tmp_path: Path) -> None:
        seed_and_prepare(warehouse, tmp_path)

        result = build_service(warehouse).execute()

        assert result.ok, result.failed
        assert result.tests_failed == 0 and result.tests_passed > 80
        assert result.built["model"] >= 30 and result.built["snapshot"] == 2 and result.built["seed"] == 2
        engine = warehouse.instance.migrator_engine()
        assert count(engine, "core.fact_crypto_finding") == count(engine, "prep.finding")
        assert count(engine, "core.dim_project", "is_current") == count(engine, "prep.project_snapshot")
        assert count(engine, "core.fact_scope_decision") == count(engine, "prep.scope_decision") > 0
        assert count(engine, "marts.mart_inventory_summary") > 0
        assert count(engine, "marts.mart_guardrail_quality") > 0
        assert count(engine, "core.fact_migration_step") == 0 == count(engine, "marts.mart_migration_outcomes")
        # Every table dbt builds with a project_key column is in the erasure registry, and the other way round (KVKK).
        holders = {
            f"{schema}.{name}"
            for schema, name in rows(
                engine,
                "SELECT c.table_schema, c.table_name FROM information_schema.columns c "
                "JOIN information_schema.tables t ON t.table_schema = c.table_schema AND t.table_name = c.table_name "
                "WHERE c.column_name = 'project_key' AND t.table_type = 'BASE TABLE' "
                "AND c.table_schema IN ('core', 'snapshots', 'marts')",
            )
        }
        assert holders == set(WAREHOUSE_TABLES_WITH_KEY)
        registered = {t.qualified for t in StaticProjectKeyTableRegistry().tables()}
        assert set(WAREHOUSE_TABLES_WITH_KEY) <= registered
        # The facts take their date from the analysis time prep keeps (D-316a).
        assert count(engine, "core.fact_crypto_finding", "date_key = 19000101") == 0

    def test_a_second_build_gives_the_same_warehouse(self, warehouse: Stack, tmp_path: Path) -> None:
        seed_and_prepare(warehouse, tmp_path)
        service = build_service(warehouse)
        service.execute()
        engine = warehouse.instance.migrator_engine()
        before = {
            t: count(engine, t)
            for t in (*FACTS, "core.dim_project", "core.dim_service", "marts.mart_inventory_summary")
        }

        again = service.execute()

        assert again.ok
        assert {t: count(engine, t) for t in before} == before, "SCD2 adds no row when nothing changed"

    def test_the_risk_mart_has_no_user_rows_and_the_inventory_counts_a_location_once(
        self, warehouse: Stack, tmp_path: Path
    ) -> None:
        seed_and_prepare(warehouse, tmp_path)
        ingest(warehouse, envelope("finding_detected", event_id=str(uuid.uuid4())))  # the same scan again (D-317a)
        pipeline(warehouse, tmp_path).execute()
        build_service(warehouse).execute()
        engine = warehouse.instance.migrator_engine()

        assert count(engine, "marts.mart_risk_features", "origin = 'USER'") == 0
        assert count(engine, "marts.mart_risk_features", "origin = 'CORPUS'") > 0
        user = rows(
            engine,
            "SELECT sum(location_count), sum(raw_finding_count) FROM marts.mart_inventory_summary WHERE origin = 'USER'",
        )[0]
        assert user[1] >= user[0] and user[0] >= 1

    def test_a_new_runtime_version_adds_a_service_row_and_the_facts_follow_the_current_one(
        self, warehouse: Stack, tmp_path: Path
    ) -> None:
        seed_and_prepare(warehouse, tmp_path)
        service = build_service(warehouse)
        service.execute()
        engine = warehouse.instance.migrator_engine()
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE prep.analysis_unit SET java_version = '25' WHERE project_key = :k"), {"k": CORPUS_KEY}
            )

        service.execute()

        history = rows(
            engine,
            "SELECT java_version, is_current FROM core.dim_service WHERE project_key = :k ORDER BY valid_from",
            k=CORPUS_KEY,
        )
        assert [row[1] for row in history] == [False, True] and history[-1][0] == "25"
        assert count(engine, "core.fact_crypto_finding f JOIN core.dim_service s ON s.service_sk = f.service_sk",
                     "f.project_key = :k AND NOT s.is_current", k=CORPUS_KEY) == 0  # fmt: skip


class TestLocations:
    def test_two_usages_on_one_line_are_two_locations(self, warehouse: Stack, tmp_path: Path) -> None:
        # SHA1withRSA is a signature and a hash on one line (D-190c): one location per usage, not per line.
        ingest(
            warehouse,
            *corpus_events(
                CORPUS_KEY,
                corpus_finding(line=7),
                corpus_finding(line=7, algorithm_family="SHA1", usage_context="HASH", hash="SHA-1", padding=None),
            ),
        )
        pipeline(warehouse, tmp_path).execute()
        build_service(warehouse).execute()
        engine = warehouse.instance.migrator_engine()

        service = rows(engine, "SELECT location_count, vulnerable_location_count FROM marts.mart_service_runtime")
        inventory = rows(engine, "SELECT sum(location_count), sum(raw_finding_count) FROM marts.mart_inventory_summary")
        assert service == [(2, 1)]
        assert inventory == [(2, 2)]

    def test_a_service_without_findings_has_no_locations(self, warehouse: Stack, tmp_path: Path) -> None:
        ingest(warehouse, envelope("project_runtime_changed", project_key=KEY_B))  # a unit that only has a runtime
        pipeline(warehouse, tmp_path).execute()
        build_service(warehouse).execute()

        counts = rows(
            warehouse.instance.migrator_engine(),
            "SELECT location_count, vulnerable_location_count, hndl_location_count FROM marts.mart_service_runtime "
            "WHERE project_key = :k",
            k=KEY_B,
        )

        assert counts == [(0, 0, 0)]


class TestErasure:
    def test_the_revocation_test_of_dbt_fails_when_a_revoked_key_is_still_in_the_warehouse(
        self, warehouse: Stack, tmp_path: Path
    ) -> None:
        seed_and_prepare(warehouse, tmp_path)
        build_service(warehouse).execute()
        ingest(warehouse, revoked(KEY_A))
        assert run_dbt(warehouse, "test", "--select", "no_revoked_project_in_warehouse").returncode == 0
        with warehouse.instance.migrator_engine().begin() as connection:  # the erasure missed a row
            connection.execute(
                text("INSERT INTO core.fact_crypto_finding (finding_id, project_key) VALUES (gen_random_uuid(), :k)"),
                {"k": KEY_A},
            )

        failed = run_dbt(warehouse, "test", "--select", "no_revoked_project_in_warehouse")

        assert failed.returncode != 0

    def test_consent_revoked_leaves_no_row_of_the_key_anywhere(self, warehouse: Stack, tmp_path: Path) -> None:
        seed_and_prepare(warehouse, tmp_path)
        ingest(warehouse, envelope("finding_detected", project_key=KEY_B, event_id=str(uuid.uuid4())))
        pipeline(warehouse, tmp_path).execute()
        build_service(warehouse).execute()
        engine = warehouse.instance.migrator_engine()
        assert count(engine, "core.fact_crypto_finding", "project_key = :k", k=KEY_A) > 0

        ingest(warehouse, revoked(KEY_A))

        for table in ("raw.event", "prep.project_snapshot", "prep.finding", *WAREHOUSE_TABLES_WITH_KEY):
            assert count(engine, table, "project_key = :k", k=KEY_A) == 0, table
        assert count(engine, "core.fact_crypto_finding", "project_key = :k", k=KEY_B) > 0, "another project stays"
        audited = dict(rows(engine, "SELECT table_name, deleted_rows FROM ingest.ingest_audit_table"))
        assert audited["core.fact_crypto_finding"] > 0 and audited["marts.mart_inventory_summary"] > 0
        assert audited["snapshots.dim_project_snapshot"] >= 1 and audited["core.dim_project"] >= 1

    def test_an_erasure_before_dbt_ever_ran_is_not_an_error(self, warehouse: Stack, tmp_path: Path) -> None:
        seed_and_prepare(warehouse, tmp_path)

        ingest(warehouse, revoked(KEY_A))  # no warehouse table exists yet

        engine = warehouse.instance.migrator_engine()
        audited = dict(rows(engine, "SELECT table_name, deleted_rows FROM ingest.ingest_audit_table"))
        assert audited["core.fact_crypto_finding"] == 0 and count(engine, "raw.event", "project_key = :k", k=KEY_A) == 0

    def test_a_build_after_a_revocation_does_not_bring_the_key_back_from_stale_prep(
        self, warehouse: Stack, tmp_path: Path
    ) -> None:
        seed_and_prepare(warehouse, tmp_path)
        service = build_service(warehouse)
        service.execute()
        engine = warehouse.instance.migrator_engine()
        stale = {
            t: rows(engine, f"SELECT * FROM {t} WHERE project_key = :k", k=KEY_A) for t in ("prep.project_snapshot",)
        }  # noqa: S608
        assert stale["prep.project_snapshot"], "the key is in prep before the revocation"
        ingest(warehouse, revoked(KEY_A))
        # A build that read prep before the erasure: put the rows of the key (older than the revocation) back into prep.
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO prep.project_snapshot (project_key, origin, is_outlier_project) VALUES (:k, 'USER', false)"
                ),
                {"k": KEY_A},
            )
            connection.execute(
                text(
                    "INSERT INTO prep.analysis_unit (project_key, unit_path, analysed_at) VALUES (:k, '.', now() - interval '1 day')"
                ),
                {"k": KEY_A},
            )
            connection.execute(text(
                "INSERT INTO prep.finding (id, project_key, unit_path, source_event_id, file_path, algorithm_family, usage_context, "
                "location_kind, priority, confidence, in_test_code) VALUES (gen_random_uuid(), :k, '.', gen_random_uuid(), 'a/b.java', "
                "'RSA', 'ENCRYPTION', 'CODE', 'P0', 0.9, false)"), {"k": KEY_A})  # fmt: skip

        assert service.execute().ok

        for table in WAREHOUSE_TABLES_WITH_KEY:
            assert count(engine, table, "project_key = :k", k=KEY_A) == 0, table

    def test_a_row_dated_after_the_revocation_is_kept(self, warehouse: Stack, tmp_path: Path) -> None:
        seed_and_prepare(warehouse, tmp_path)
        ingest(warehouse, revoked(KEY_A, datetime(2026, 1, 1, tzinfo=UTC)))
        engine = warehouse.instance.migrator_engine()
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO prep.project_snapshot (project_key, origin, is_outlier_project) VALUES (:k, 'USER', false)"
                ),
                {"k": KEY_A},
            )
            connection.execute(
                text("INSERT INTO prep.analysis_unit (project_key, unit_path, analysed_at) VALUES (:k, '.', now())"),
                {"k": KEY_A},
            )

        assert build_service(warehouse).execute().ok

        assert count(engine, "core.dim_service", "project_key = :k", k=KEY_A) == 1


class TestDeleteMacro:
    def test_the_macro_erases_a_key_from_every_warehouse_table(self, warehouse: Stack, tmp_path: Path) -> None:
        seed_and_prepare(warehouse, tmp_path)
        build_service(warehouse).execute()
        engine = warehouse.instance.migrator_engine()
        assert count(engine, "core.fact_crypto_finding", "project_key = :k", k=CORPUS_KEY) > 0
        instance = warehouse.instance

        with tempfile.TemporaryDirectory() as profiles:
            (Path(profiles) / "profiles.yml").write_text((PROJECT / "profiles.yml.example").read_text())
            environment = {
                **{k: v for k, v in os.environ.items() if k in ("PATH", "HOME")},
                "DBT_USER": "warehouse_db_migrator", "DBT_PASSWORD": instance.migrator_password, "DBT_PORT": str(instance.port),
                "DBT_SEND_ANONYMOUS_USAGE_STATS": "false",
            }  # fmt: skip
            done = subprocess.run(  # noqa: S603
                [*DBT, "run-operation", "delete_project_key", "--args", f"{{project_key: {CORPUS_KEY}}}",
                 "--project-dir", str(PROJECT), "--profiles-dir", profiles],
                env=environment, capture_output=True, check=False,
            )  # fmt: skip

        assert done.returncode == 0, done.stdout[-600:]
        for table in WAREHOUSE_TABLES_WITH_KEY:
            assert count(engine, table, "project_key = :k", k=CORPUS_KEY) == 0, table
        assert count(engine, "core.fact_crypto_finding", "project_key = :k", k=KEY_A) > 0

    def test_the_macro_refuses_anything_but_a_project_key(self, warehouse: Stack) -> None:
        instance = warehouse.instance
        with tempfile.TemporaryDirectory() as profiles:
            (Path(profiles) / "profiles.yml").write_text((PROJECT / "profiles.yml.example").read_text())
            environment = {
                **{k: v for k, v in os.environ.items() if k in ("PATH", "HOME")},
                "DBT_USER": "warehouse_db_migrator", "DBT_PASSWORD": instance.migrator_password, "DBT_PORT": str(instance.port),
                "DBT_SEND_ANONYMOUS_USAGE_STATS": "false",
            }  # fmt: skip
            done = subprocess.run(  # noqa: S603
                [*DBT, "run-operation", "delete_project_key", "--args", "{project_key: \"x' or '1'='1\"}",
                 "--project-dir", str(PROJECT), "--profiles-dir", profiles],
                env=environment, capture_output=True, check=False,
            )  # fmt: skip

        assert done.returncode != 0


class TestRolesAndLock:
    def test_the_reader_reads_marts_and_nothing_else(self, warehouse: Stack, tmp_path: Path) -> None:
        seed_and_prepare(warehouse, tmp_path)
        build_service(warehouse).execute()
        reader = warehouse.instance.reader_engine()

        assert count(reader, "marts.mart_inventory_summary") > 0
        for table in ("core.fact_crypto_finding", "core.dim_project", "snapshots.dim_project_snapshot", "prep.finding",
                      "staging.stg_finding", "raw.event", "ingest.ingest_audit"):  # fmt: skip
            with pytest.raises(DBAPIError, match="permission denied"):
                count(reader, table)
        with pytest.raises(DBAPIError, match="permission denied"), reader.begin() as connection:
            connection.execute(text("DELETE FROM marts.mart_inventory_summary"))

    def test_the_application_role_erases_but_neither_inserts_nor_reads_prep_here(
        self, warehouse: Stack, tmp_path: Path
    ) -> None:
        seed_and_prepare(warehouse, tmp_path)
        build_service(warehouse).execute()
        app = warehouse.instance.app_engine()

        with app.begin() as connection:
            connection.execute(text("DELETE FROM core.fact_crypto_finding WHERE project_key = :k"), {"k": KEY_B})
        for statement in ("INSERT INTO core.fact_crypto_finding (finding_id) VALUES (gen_random_uuid())",
                          "UPDATE core.dim_project SET origin = 'USER'", "DROP TABLE core.dim_project"):  # fmt: skip
            with pytest.raises(DBAPIError, match="permission denied|must be owner"), app.begin() as connection:
                connection.execute(text(statement))

    def test_a_second_build_gives_up_while_the_first_holds_the_lock_and_gets_it_when_it_ends(
        self, warehouse: Stack
    ) -> None:
        settings = warehouse.instance.settings()
        waiter = PostgresWarehouseBuildLock(settings, wait_s=1.0)

        with PostgresWarehouseBuildLock(settings).held(), pytest.raises(WarehouseBusyError), waiter.held():
            pass

        with waiter.held():  # free again once the first is released
            pass

    def test_a_lock_connection_that_dies_during_the_build_fails_the_build(self, warehouse: Stack) -> None:
        lock = PostgresWarehouseBuildLock(warehouse.instance.settings())
        engine = warehouse.instance.migrator_engine()

        # The server ends the session that holds the lock, as a restart would; the build must not end as a success.
        with (
            pytest.raises(Exception, match="lock|terminat|closed|connection"),  # noqa: B017 (driver specific errors)
            lock.held(),
            engine.begin() as admin,
        ):
            admin.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_locks WHERE locktype = 'advisory' AND granted "
                    "AND pid <> pg_backend_pid()"
                )
            )

    def test_an_erasure_waits_while_a_build_holds_the_lock(self, warehouse: Stack, tmp_path: Path) -> None:
        seed_and_prepare(warehouse, tmp_path)
        done = threading.Event()
        failure: list[BaseException] = []

        def erase() -> None:
            try:
                ingest(warehouse, revoked(KEY_A))
            except BaseException as exc:  # noqa: BLE001 (reported below)
                failure.append(exc)
            done.set()

        with PostgresWarehouseBuildLock(warehouse.instance.settings()).held():
            worker = threading.Thread(target=erase)
            worker.start()
            assert not done.wait(1.5), "the erasure did not wait for the build lock"
        worker.join(15)

        assert done.is_set() and not failure
        assert count(warehouse.instance.migrator_engine(), "raw.event", "project_key = :k", k=KEY_A) == 0

"""warehouse_db corpus and benchmark landing (P6.2, D-298): two event sources, two event types and `raw.benchmark_label`.

`corpus_analysis` events come from the corpus flow (source `corpus`) and `benchmark_analysis` events from the benchmark flow (source
`benchmark`); the source stays a dependency of the event type (`ingest.event_type`), as in 0001. `raw.benchmark_label` is the
landing table of a benchmark's own ground truth: it holds no project key, so the erasure of a project never touches it. Its columns
are provisional until the label files of CryptoAPI-Bench and OWASP Benchmark have been seen (D-298h): this revision is edited in
place until a database outside the throw-away test containers has applied it.

Decisions: D-298.

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

APP_ROLE = "warehouse_db_app"

STATEMENTS = (
    "INSERT INTO ingest.event_source (code, description, sort_order) VALUES "
    "('corpus', 'Events written by the corpus flow of the data platform (static analysis of the open-source corpus)', 3), "
    "('benchmark', 'Events written by the benchmark flow of the data platform (static analysis of benchmark code)', 4)",
    "INSERT INTO ingest.event_type (code, source_code, description, sort_order) VALUES "
    "('corpus_analysis', 'corpus', 'The static analysis of a corpus project, or of one of its service directories', 9), "
    "('benchmark_analysis', 'benchmark', 'The static analysis of the code of a benchmark', 10)",
    # The benchmarks whose labels can be loaded. Another benchmark is a new row (a migration), after the user approves it.
    "CREATE TABLE ingest.benchmark (code varchar(40) NOT NULL, description varchar(200) NOT NULL, sort_order smallint NOT NULL, "
    "CONSTRAINT pk_benchmark PRIMARY KEY (code), CONSTRAINT ck_benchmark_code CHECK (code ~ '^[a-z0-9][a-z0-9-]{0,39}$'))",
    "INSERT INTO ingest.benchmark (code, description, sort_order) VALUES "
    "('cryptoapi-bench', 'CryptoAPI-Bench: Java cryptographic API misuse test cases', 1), "
    "('owasp-benchmark', 'OWASP Benchmark for Java: test cases with the expected result of each', 2)",
    # One row per test case of a benchmark. NULL means the benchmark's label file does not say; nothing is guessed.
    "CREATE TABLE raw.benchmark_label ("
    "benchmark varchar(40) NOT NULL, case_id varchar(256) NOT NULL, file_path varchar(1024), category varchar(128), "
    "cwe integer, expected_vulnerable boolean NOT NULL, "
    "CONSTRAINT pk_benchmark_label PRIMARY KEY (benchmark, case_id), "
    "CONSTRAINT fk_benchmark_label_benchmark FOREIGN KEY (benchmark) REFERENCES ingest.benchmark (code) ON DELETE RESTRICT, "
    "CONSTRAINT ck_benchmark_label_case_id CHECK (btrim(case_id) <> ''), "
    "CONSTRAINT ck_benchmark_label_cwe CHECK (cwe IS NULL OR cwe > 0))",
    # When a benchmark was loaded and with how many labels: a fact about the load (the benchmark), not about one label, so it
    # is not a column of the label (that would make it depend on part of the key, 2NF).
    "CREATE TABLE raw.benchmark_load ("
    "benchmark varchar(40) NOT NULL, loaded_at timestamptz NOT NULL, label_count integer NOT NULL, "
    "CONSTRAINT pk_benchmark_load PRIMARY KEY (benchmark), "
    "CONSTRAINT fk_benchmark_load_benchmark FOREIGN KEY (benchmark) REFERENCES ingest.benchmark (code) ON DELETE RESTRICT, "
    "CONSTRAINT ck_benchmark_load_label_count CHECK (label_count >= 0))",
    f"GRANT SELECT ON ingest.benchmark TO {APP_ROLE}",
    # Loaded again from the files: deleted and written in one transaction, never updated.
    f"GRANT SELECT, INSERT, DELETE ON raw.benchmark_label, raw.benchmark_load TO {APP_ROLE}",
)


def upgrade() -> None:
    connection = op.get_bind()
    for statement in STATEMENTS:
        connection.exec_driver_sql(statement)


def downgrade() -> None:
    raise NotImplementedError(
        "Migrations are forward-only (acid-3nf-database section 4); fix forward with a new revision."
    )

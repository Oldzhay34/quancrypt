"""prep analysis time and the erasure registry of the warehouse tables (P6.6, D-316a, D-317g, D-319).

- `prep.analysis_unit.analysed_at` is when a unit was analysed (the largest `occurred_at` of the events that feed it) and
  `prep.topology_summary.recorded_at` when a topology was recorded: the warehouse fact tables take their date from them.
- prep is derived data (preprocessing rewrites it from raw), so the rows written before this revision are deleted instead of
  being given an invented time: run `quancrypt-data preprocess` again.
- `ingest.project_key_table` lists the warehouse tables dbt builds (core, snapshots, marts) that hold rows of a project key:
  the erasure of a consent_revoked event covers them too. The tables do not exist until dbt builds them; the eraser skips
  a table that is not there (pg_class).

Revision ID: 0004
Revises: 0003
"""

from __future__ import annotations

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

# (code, description): every warehouse table with a project_key column (docs/data/warehouse-design.md section 10).
WAREHOUSE_TABLES = (
    ("marts.mart_inventory_summary", "Inventory counts of a project (mart)"),
    ("marts.mart_service_runtime", "Runtime versions and findings of a service (mart)"),
    ("marts.mart_topology_coverage", "TLS and mTLS coverage of a project topology (mart)"),
    ("marts.mart_risk_features", "Model-ready finding rows (mart)"),
    ("core.fact_crypto_finding", "Crypto findings (fact)"),
    ("core.fact_topology_summary", "Topology summaries (fact)"),
    ("core.fact_service_link", "Service links (fact)"),
    ("core.fact_scope_decision", "Scope decisions (fact)"),
    ("core.fact_migration_step", "Migration steps (fact, empty until phase 8)"),
    ("core.dim_service", "Services with their runtime history (dimension)"),
    ("core.dim_project", "Projects with their history (dimension)"),
    ("snapshots.dim_service_snapshot", "History of the services (snapshot)"),
    ("snapshots.dim_project_snapshot", "History of the projects (snapshot)"),
)
FIRST_SORT_ORDER = 10

STATEMENTS = (
    "DELETE FROM quarantine.prep_record",
    "DELETE FROM prep.project_snapshot",
    "ALTER TABLE prep.analysis_unit ADD COLUMN analysed_at timestamptz NOT NULL",
    "ALTER TABLE prep.topology_summary ADD COLUMN recorded_at timestamptz NOT NULL",
    "INSERT INTO ingest.project_key_table (code, description, sort_order) VALUES "
    + ", ".join(
        f"('{code}', '{description}', {FIRST_SORT_ORDER + i})" for i, (code, description) in enumerate(WAREHOUSE_TABLES)
    ),
)


def upgrade() -> None:
    connection = op.get_bind()
    for statement in STATEMENTS:
        connection.exec_driver_sql(statement)


def downgrade() -> None:
    raise NotImplementedError(
        "Migrations are forward-only (acid-3nf-database section 4); fix forward with a new revision."
    )

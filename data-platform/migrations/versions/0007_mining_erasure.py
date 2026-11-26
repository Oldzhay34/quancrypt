"""The erasure registry of the mining results (P7.4, D-338h).

`marts.mart_archetypes` (dbt) and `ml_outputs.project_archetype` and `ml_outputs.anomaly` (ml/migrations 0004) hold a
project key. The consent_revoked erasure covers them; the eraser skips a table until it has been created (pg_class).
Association rules and cluster names carry no project key; they keep an erased project's share until the next mining run.

Revision ID: 0007
Revises: 0006
"""

from __future__ import annotations

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

STATEMENTS = (
    "INSERT INTO ingest.project_key_table (code, description, sort_order) VALUES "
    "('marts.mart_archetypes', 'Project crypto profiles (warehouse mart)', 32), "
    "('ml_outputs.project_archetype', 'Cluster assignments of a project (ml_outputs)', 33), "
    "('ml_outputs.anomaly', 'Anomaly score of a project (ml_outputs)', 34)",
)


def upgrade() -> None:
    connection = op.get_bind()
    for statement in STATEMENTS:
        connection.exec_driver_sql(statement)


def downgrade() -> None:
    raise NotImplementedError("migrations move forward only (acid-3nf-database section 4)")

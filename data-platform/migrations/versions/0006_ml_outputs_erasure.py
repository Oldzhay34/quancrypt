"""The erasure registry of Model A's outputs (P7.2, D-327d).

`ml_outputs.scored_finding` (created by ml/migrations 0002) holds a project key; the predictions and SHAP explanations of
the finding go with it by CASCADE. The consent_revoked erasure covers it; the eraser skips the table until `ml migrate`
has created it (pg_class).

Revision ID: 0006
Revises: 0005
"""

from __future__ import annotations

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

STATEMENTS = (
    "INSERT INTO ingest.project_key_table (code, description, sort_order) VALUES "
    "('ml_outputs.scored_finding', 'Model A scored findings (ml_outputs; predictions and explanations by CASCADE)', 31)",
)


def upgrade() -> None:
    connection = op.get_bind()
    for statement in STATEMENTS:
        connection.exec_driver_sql(statement)


def downgrade() -> None:
    raise NotImplementedError("migrations move forward only (acid-3nf-database section 4)")

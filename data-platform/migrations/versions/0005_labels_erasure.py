"""The erasure registry of the gold labels (P7.1, D-322g).

`labels.labeled_finding` (created by ml/migrations, the labels schema of Model A) holds a project key; the batch items,
labels and resolutions of the finding go with it by CASCADE (D-324a). The consent_revoked erasure covers it; the eraser skips the table until
`ml migrate` has created it (pg_class).

Revision ID: 0005
Revises: 0004
"""

from __future__ import annotations

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

STATEMENTS = (
    "INSERT INTO ingest.project_key_table (code, description, sort_order) VALUES "
    "('labels.labeled_finding', 'Labelled findings (labels; batch items, labels and resolutions by CASCADE)', 30)",
)


def upgrade() -> None:
    connection = op.get_bind()
    for statement in STATEMENTS:
        connection.exec_driver_sql(statement)


def downgrade() -> None:
    raise NotImplementedError("migrations move forward only (acid-3nf-database section 4)")

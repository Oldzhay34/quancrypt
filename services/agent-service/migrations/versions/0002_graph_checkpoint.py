"""graph_checkpoint (P4.6, D-252e, D-253): the latest LangGraph checkpoint of a chat session, one row per session.

The state is opaque (the checkpoint without its id, plus the source/step/parents metadata, serialized as msgpack) and is never
queried; its digest sits next to it (acid-3nf-database section 3, the only 3NF/BCNF exception of the table). The row belongs to
its session and goes with it (CASCADE). The application role gets DML through the init script's default privileges (D-54).

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

DDL = (
    "CREATE TABLE graph_checkpoint (\n"
    "  session_id    uuid        NOT NULL,\n"
    "  checkpoint_id uuid        NOT NULL,\n"
    "  state_type    varchar(32) NOT NULL,\n"
    "  state         bytea       NOT NULL,\n"
    "  state_sha256  char(64)    NOT NULL,\n"
    "  updated_at    timestamptz NOT NULL,\n"
    "  CONSTRAINT pk_graph_checkpoint PRIMARY KEY (session_id),\n"
    "  CONSTRAINT fk_graph_checkpoint_session FOREIGN KEY (session_id) REFERENCES chat_session (id) ON DELETE CASCADE,\n"
    "  CONSTRAINT ck_graph_checkpoint_type CHECK (state_type = 'msgpack'),\n"
    "  CONSTRAINT ck_graph_checkpoint_size CHECK (octet_length(state) BETWEEN 1 AND 65536),\n"
    "  CONSTRAINT ck_graph_checkpoint_sha CHECK (state_sha256 ~ '^[0-9a-f]{64}$')\n"
    ")",
    "CREATE INDEX ix_graph_checkpoint_updated ON graph_checkpoint (updated_at)",
)


def upgrade() -> None:
    connection = op.get_bind()
    for statement in DDL:
        connection.exec_driver_sql(statement)


def downgrade() -> None:
    raise NotImplementedError(
        "Migrations are forward-only (acid-3nf-database section 4); fix forward with a new revision."
    )

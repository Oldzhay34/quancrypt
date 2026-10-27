"""warehouse_db landing layer (P6.1, D-295, D-296): schemas `raw`, `quarantine` and `ingest`.

Plain SQL, so the database is the single source of the constraints (CHECK, UNIQUE, foreign keys). `raw.event` is the only place
where an event's payload lives as jsonb; `quarantine.event` keeps the original record of what failed validation. The `ingest`
schema holds the lookups, the batch lineage and the erasure audit. `prep` is created by P6.4. The application role gets exactly
the privileges below: DML on the entity tables, SELECT on the code lists, nothing else (the init script's default privileges
only cover `public`, D-54).

Decisions: D-295 and D-296.

Revision ID: 0001
Revises:
"""

from __future__ import annotations

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

APP_ROLE = "warehouse_db_app"

SCHEMAS = ("raw", "quarantine", "ingest")

LOOKUPS = (
    ("ingest.event_source", "code varchar(32)"),
    ("ingest.audit_action", "code varchar(32)"),
    ("ingest.project_key_table", "code varchar(64)"),
    ("quarantine.error_code", "code varchar(32)"),
)

LOOKUP_DATA = (
    "INSERT INTO ingest.event_source (code, description, sort_order) VALUES "
    "('core-service', 'Events written by core-service (transactional outbox)', 1), "
    "('agent-service', 'Events written by agent-service (transactional outbox)', 2)",
    "INSERT INTO ingest.audit_action (code, description, sort_order) VALUES "
    "('PROJECT_DATA_DELETED', 'The rows of a project key were erased after consent_revoked', 1)",
    "INSERT INTO ingest.project_key_table (code, description, sort_order) VALUES "
    "('raw.event', 'Landing table of the events', 1), "
    "('quarantine.event', 'Quarantine of the records that failed validation', 2)",
    "INSERT INTO quarantine.error_code (code, description, sort_order) VALUES "
    "('malformed-envelope', 'Not a JSON object, no usable event_id or event_type, or text PostgreSQL cannot store', 1), "
    "('unknown-event-type', 'No schema for the event type', 2), "
    "('schema-violation', 'The envelope does not match the schema of its event type', 3)",
)

DDL = (
    # event_type is a lookup of its own: its source is a dependency of the type (event_type -> source).
    "CREATE TABLE ingest.event_type ("
    "code varchar(32) NOT NULL, source_code varchar(32) NOT NULL, description varchar(200) NOT NULL, "
    "sort_order smallint NOT NULL, "
    "CONSTRAINT pk_event_type PRIMARY KEY (code), "
    "CONSTRAINT uq_event_type_code_source UNIQUE (code, source_code), "
    "CONSTRAINT fk_event_type_source FOREIGN KEY (source_code) REFERENCES ingest.event_source (code) ON DELETE RESTRICT)",
    "INSERT INTO ingest.event_type (code, source_code, description, sort_order) VALUES "
    "('finding_detected', 'core-service', 'A crypto finding was recorded', 1), "
    "('topology_recorded', 'core-service', 'A service topology was recorded', 2), "
    "('scan_completed', 'core-service', 'A scan completed', 3), "
    "('plan_created', 'core-service', 'A migration plan was created', 4), "
    "('plan_item_transitioned', 'core-service', 'A plan item changed state', 5), "
    "('project_runtime_changed', 'core-service', 'The runtime profile of a project changed', 6), "
    "('consent_revoked', 'core-service', 'A consent was revoked or the project deleted (a command: never stored)', 7), "
    "('scope_decision', 'agent-service', 'The scope guard decided on a request', 8)",
    "CREATE TABLE ingest.ingest_batch ("
    "id uuid NOT NULL, received_at timestamptz NOT NULL, received_count integer NOT NULL, "
    "duplicate_count integer NOT NULL DEFAULT 0, "
    "CONSTRAINT pk_ingest_batch PRIMARY KEY (id), "
    "CONSTRAINT uq_ingest_batch_id_received_at UNIQUE (id, received_at), "
    "CONSTRAINT ck_ingest_batch_received_count CHECK (received_count BETWEEN 1 AND 500), "
    "CONSTRAINT ck_ingest_batch_duplicate_count CHECK (duplicate_count BETWEEN 0 AND received_count))",
    # source is derived from event_type; the composite foreign key makes the database refuse a pair that does not belong
    # together (the column is kept because the landing layer carries its lineage, P6.1 prompt).
    "CREATE TABLE raw.event ("
    "event_id uuid NOT NULL, batch_id uuid NOT NULL, source varchar(32) NOT NULL, source_ref varchar(512), "
    "event_type varchar(32) NOT NULL, schema_version integer NOT NULL, occurred_at timestamptz NOT NULL, "
    "received_at timestamptz NOT NULL, project_key char(64) NOT NULL, payload jsonb NOT NULL, "
    "CONSTRAINT pk_event PRIMARY KEY (event_id), "
    "CONSTRAINT fk_event_batch FOREIGN KEY (batch_id, received_at) "
    "REFERENCES ingest.ingest_batch (id, received_at) ON DELETE RESTRICT, "
    "CONSTRAINT fk_event_event_type_source FOREIGN KEY (event_type, source) "
    "REFERENCES ingest.event_type (code, source_code) ON DELETE RESTRICT, "
    "CONSTRAINT ck_event_schema_version CHECK (schema_version > 0), "
    "CONSTRAINT ck_event_project_key CHECK (project_key ~ '^[0-9a-f]{64}$'), "
    "CONSTRAINT ck_event_payload_object CHECK (jsonb_typeof(payload) = 'object'), "
    "CONSTRAINT ck_event_not_a_command CHECK (event_type <> 'consent_revoked'))",
    "CREATE INDEX ix_event_project_key ON raw.event (project_key)",
    "CREATE INDEX ix_event_batch_id ON raw.event (batch_id)",
    "CREATE TABLE quarantine.event ("
    "id uuid NOT NULL, batch_id uuid NOT NULL, event_id varchar(64), project_key char(64), "
    "record_sha256 char(64) NOT NULL, record jsonb NOT NULL, error_code varchar(32) NOT NULL, "
    "error_message varchar(500) NOT NULL, quarantined_at timestamptz NOT NULL, "
    "CONSTRAINT pk_quarantine_event PRIMARY KEY (id), "
    "CONSTRAINT uq_quarantine_event_record UNIQUE (record_sha256), "
    "CONSTRAINT fk_quarantine_event_batch FOREIGN KEY (batch_id, quarantined_at) "
    "REFERENCES ingest.ingest_batch (id, received_at) ON DELETE RESTRICT, "
    "CONSTRAINT fk_quarantine_event_error_code FOREIGN KEY (error_code) "
    "REFERENCES quarantine.error_code (code) ON DELETE RESTRICT, "
    "CONSTRAINT ck_quarantine_event_project_key CHECK (project_key IS NULL OR project_key ~ '^[0-9a-f]{64}$'), "
    "CONSTRAINT ck_quarantine_event_sha256 CHECK (record_sha256 ~ '^[0-9a-f]{64}$'))",
    "CREATE INDEX ix_quarantine_event_project_key ON quarantine.event (project_key) WHERE project_key IS NOT NULL",
    "CREATE INDEX ix_quarantine_event_batch_id ON quarantine.event (batch_id)",
    "CREATE TABLE ingest.ingest_audit ("
    "id uuid NOT NULL, performed_at timestamptz NOT NULL, action_code varchar(32) NOT NULL, project_key char(64) NOT NULL, "
    "event_id uuid NOT NULL, revoked_at timestamptz NOT NULL, "
    "CONSTRAINT pk_ingest_audit PRIMARY KEY (id), "
    "CONSTRAINT uq_ingest_audit_event UNIQUE (event_id), "
    "CONSTRAINT fk_ingest_audit_action FOREIGN KEY (action_code) REFERENCES ingest.audit_action (code) ON DELETE RESTRICT, "
    "CONSTRAINT ck_ingest_audit_project_key CHECK (project_key ~ '^[0-9a-f]{64}$'))",
    "CREATE INDEX ix_ingest_audit_project_key ON ingest.ingest_audit (project_key, revoked_at)",
    "CREATE TABLE ingest.ingest_audit_table ("
    "audit_id uuid NOT NULL, table_name varchar(64) NOT NULL, deleted_rows bigint NOT NULL, "
    "CONSTRAINT pk_ingest_audit_table PRIMARY KEY (audit_id, table_name), "
    "CONSTRAINT fk_ingest_audit_table_audit FOREIGN KEY (audit_id) REFERENCES ingest.ingest_audit (id) ON DELETE RESTRICT, "
    "CONSTRAINT fk_ingest_audit_table_name FOREIGN KEY (table_name) "
    "REFERENCES ingest.project_key_table (code) ON DELETE RESTRICT, "
    "CONSTRAINT ck_ingest_audit_table_deleted_rows CHECK (deleted_rows >= 0))",
)

CREATE_LOOKUP = (
    "CREATE TABLE {table} ({code} NOT NULL, description varchar(200) NOT NULL, sort_order smallint NOT NULL, "
    "CONSTRAINT pk_{name} PRIMARY KEY (code))"
)

GRANTS = (
    f"GRANT USAGE ON SCHEMA raw, quarantine, ingest TO {APP_ROLE}",
    # The application reads the code lists and never changes them.
    f"GRANT SELECT ON ingest.event_source, ingest.event_type, ingest.audit_action, ingest.project_key_table, "
    f"quarantine.error_code TO {APP_ROLE}",
    # Events and quarantined records are written once and erased on consent_revoked; never updated.
    f"GRANT SELECT, INSERT, DELETE ON raw.event, quarantine.event TO {APP_ROLE}",
    f"GRANT SELECT, INSERT ON ingest.ingest_batch, ingest.ingest_audit, ingest.ingest_audit_table TO {APP_ROLE}",
    f"GRANT UPDATE (duplicate_count) ON ingest.ingest_batch TO {APP_ROLE}",
    # Alembic's own table is created by the migrator in `public`, where the init script's default privileges would give the
    # application role DML on it: the application never changes the schema version.
    f"REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON public.alembic_version FROM {APP_ROLE}",
)


def upgrade() -> None:
    connection = op.get_bind()
    for schema in SCHEMAS:
        connection.exec_driver_sql(f"CREATE SCHEMA {schema}")
    for table, code in LOOKUPS:
        name = table.split(".")[1]
        connection.exec_driver_sql(CREATE_LOOKUP.format(table=table, code=code, name=name))
    for statement in LOOKUP_DATA:
        connection.exec_driver_sql(statement)
    for statement in DDL:
        connection.exec_driver_sql(statement)
    for statement in GRANTS:
        connection.exec_driver_sql(statement)


def downgrade() -> None:
    raise NotImplementedError(
        "Migrations are forward-only (acid-3nf-database section 4); fix forward with a new revision."
    )

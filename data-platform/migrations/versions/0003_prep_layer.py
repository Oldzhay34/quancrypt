"""warehouse_db prep layer (P6.4, D-310, D-311): the clean, canonical and anonymous entity tables the preprocessing
pipeline writes, and the quarantine of the records it set aside.

prep is no warehouse: no dimensional model, entity tables in 3NF (docs/data/prep-erd.md). Every row belongs to a project
snapshot and goes with it (ON DELETE CASCADE): the erasure of a project key (consent_revoked) deletes the snapshot and the
prep quarantine rows of the key, the registry lists both. The code lists are lookup tables seeded here.

Revision ID: 0003
Revises: 0002
"""

from __future__ import annotations

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

APP_ROLE = "warehouse_db_app"

# (table, codes): crypto-domain section 1 and the event schemas; quarantine_filter holds the filters of the pipeline.
LOOKUPS = (
    ("prep.algorithm_family", (
        "RSA", "ECDSA", "ECDH", "EDDSA", "DH", "DSA", "ML_KEM", "ML_DSA", "SLH_DSA", "AES", "DES", "TRIPLE_DES",
        "CHACHA20", "SHA1", "SHA2", "SHA3", "MD5", "HMAC", "X25519", "HYBRID_X25519_MLKEM768", "UNKNOWN",
    )),
    ("prep.usage_context", (
        "TLS_KEY_EXCHANGE", "TLS_SERVER_AUTH", "MTLS_CLIENT_AUTH", "CERTIFICATE", "ENCRYPTION", "KEY_WRAP", "SIGNATURE",
        "TOKEN_SIGNATURE", "KEY_AGREEMENT", "HASH", "SYMMETRIC_ENCRYPTION", "KEYSTORE", "UNKNOWN",
    )),
    ("prep.location_kind", ("CODE", "CONFIG", "CERTIFICATE_FILE", "KEYSTORE_FILE", "BUILD_FILE", "TEST_CODE")),
    ("prep.priority", ("P0", "P1", "P2", "P3")),
    ("prep.protocol", ("HTTP", "GRPC", "MQTT", "AMQP", "KAFKA", "OTHER")),
    ("prep.decision", ("ALLOW", "DENY")),
    ("prep.deciding_ring", ("RULE_FILTER", "SCOPE_CLASSIFIER", "LLM_SELF_CHECK", "FAIL_CLOSED")),
    ("prep.language", ("tr", "en")),
    ("prep.project_origin", ("CORPUS", "BENCHMARK", "USER")),
    ("quarantine.prep_filter", (
        "SchemaValidator", "Deduplicator", "GeneratedCodeExcluder", "TestCodeFlagger", "Canonicalizer", "Anonymizer",
        "MissingValueHandler", "OutlierFlagger", "TypeCaster",
    )),
)  # fmt: skip

_LOOKUP = (
    "CREATE TABLE {table} (code varchar(32) NOT NULL, description varchar(200) NOT NULL, sort_order smallint NOT NULL, "
    "CONSTRAINT pk_{name} PRIMARY KEY (code))"
)


def _lookup_statements() -> list[str]:
    statements = []
    for table, codes in LOOKUPS:
        statements.append(_LOOKUP.format(table=table, name=table.split(".")[1]))
        # The codes name themselves (crypto-domain section 1 defines them); the description repeats the code.
        rows = ", ".join(f"('{code}', '{code}', {position})" for position, code in enumerate(codes, start=1))
        statements.append(f"INSERT INTO {table} (code, description, sort_order) VALUES {rows}")
    return statements


_KEY = "CHECK ({column} ~ '^[0-9a-f]{{64}}$')"

DDL = (
    "CREATE TABLE prep.project_snapshot ("
    "project_key char(64) NOT NULL, origin varchar(32) NOT NULL, is_outlier_project boolean NOT NULL, "
    "CONSTRAINT pk_project_snapshot PRIMARY KEY (project_key), "
    "CONSTRAINT fk_project_snapshot_origin FOREIGN KEY (origin) REFERENCES prep.project_origin (code) ON DELETE RESTRICT, "
    f"CONSTRAINT ck_project_snapshot_key {_KEY.format(column='project_key')})",
    # A runtime belongs to an analysis unit (a service directory of a multi-build repository, or the root '.').
    "CREATE TABLE prep.analysis_unit ("
    "project_key char(64) NOT NULL, unit_path varchar(300) NOT NULL, "
    "java_version varchar(32), spring_boot_version varchar(32), "
    "CONSTRAINT pk_analysis_unit PRIMARY KEY (project_key, unit_path), "
    "CONSTRAINT fk_analysis_unit_project FOREIGN KEY (project_key) "
    "REFERENCES prep.project_snapshot (project_key) ON DELETE CASCADE, "
    "CONSTRAINT ck_analysis_unit_path CHECK (btrim(unit_path) <> ''))",
    "CREATE TABLE prep.finding ("
    "id uuid NOT NULL, project_key char(64) NOT NULL, unit_path varchar(300) NOT NULL, source_event_id uuid NOT NULL, "
    "file_path varchar(1024), line_start integer, line_end integer, "
    "algorithm_family varchar(32) NOT NULL, usage_context varchar(32) NOT NULL, location_kind varchar(32) NOT NULL, "
    "priority varchar(32) NOT NULL, key_size_bits integer, "
    # D-308c: derived from key_size_bits by the database (the one 3NF exception of prep, prep-erd.md).
    "key_size_known boolean GENERATED ALWAYS AS (key_size_bits IS NOT NULL) STORED, "
    "mode varchar(64), padding varchar(64), hash varchar(64), library varchar(64), "
    "confidence numeric(4,3) NOT NULL, in_test_code boolean NOT NULL, "
    "CONSTRAINT pk_finding PRIMARY KEY (id), "
    "CONSTRAINT fk_finding_unit FOREIGN KEY (project_key, unit_path) "
    "REFERENCES prep.analysis_unit (project_key, unit_path) ON DELETE CASCADE, "
    "CONSTRAINT fk_finding_algorithm_family FOREIGN KEY (algorithm_family) "
    "REFERENCES prep.algorithm_family (code) ON DELETE RESTRICT, "
    "CONSTRAINT fk_finding_usage_context FOREIGN KEY (usage_context) "
    "REFERENCES prep.usage_context (code) ON DELETE RESTRICT, "
    "CONSTRAINT fk_finding_location_kind FOREIGN KEY (location_kind) "
    "REFERENCES prep.location_kind (code) ON DELETE RESTRICT, "
    "CONSTRAINT fk_finding_priority FOREIGN KEY (priority) REFERENCES prep.priority (code) ON DELETE RESTRICT, "
    "CONSTRAINT ck_finding_line_start CHECK (line_start IS NULL OR line_start > 0), "
    "CONSTRAINT ck_finding_line_end CHECK (line_end IS NULL OR (line_start IS NOT NULL AND line_end >= line_start)), "
    "CONSTRAINT ck_finding_key_size CHECK (key_size_bits IS NULL OR key_size_bits > 0), "
    "CONSTRAINT ck_finding_confidence CHECK (confidence BETWEEN 0 AND 1))",
    "CREATE INDEX ix_finding_unit ON prep.finding (project_key, unit_path)",
    "CREATE TABLE prep.topology_summary ("
    "project_key char(64) NOT NULL, unit_path varchar(300) NOT NULL, source_event_id uuid NOT NULL, "
    "node_count integer NOT NULL, edge_count integer NOT NULL, tls_edge_count integer, mtls_edge_count integer, "
    "CONSTRAINT pk_topology_summary PRIMARY KEY (project_key, unit_path), "
    "CONSTRAINT fk_topology_summary_unit FOREIGN KEY (project_key, unit_path) "
    "REFERENCES prep.analysis_unit (project_key, unit_path) ON DELETE CASCADE, "
    "CONSTRAINT ck_topology_summary_counts CHECK (node_count >= 0 AND edge_count >= 0), "
    "CONSTRAINT ck_topology_summary_tls CHECK (tls_edge_count IS NULL OR tls_edge_count BETWEEN 0 AND edge_count), "
    "CONSTRAINT ck_topology_summary_mtls CHECK (mtls_edge_count IS NULL OR mtls_edge_count >= 0))",
    "CREATE TABLE prep.service_link ("
    "project_key char(64) NOT NULL, unit_path varchar(300) NOT NULL, ordinal integer NOT NULL, "
    "protocol varchar(32) NOT NULL, tls boolean NOT NULL, mtls boolean NOT NULL, "
    "CONSTRAINT pk_service_link PRIMARY KEY (project_key, unit_path, ordinal), "
    "CONSTRAINT fk_service_link_topology FOREIGN KEY (project_key, unit_path) "
    "REFERENCES prep.topology_summary (project_key, unit_path) ON DELETE CASCADE, "
    "CONSTRAINT fk_service_link_protocol FOREIGN KEY (protocol) REFERENCES prep.protocol (code) ON DELETE RESTRICT, "
    "CONSTRAINT ck_service_link_ordinal CHECK (ordinal >= 0), "
    "CONSTRAINT ck_service_link_mtls CHECK (tls OR NOT mtls))",
    "CREATE TABLE prep.scope_decision ("
    "event_id uuid NOT NULL, project_key char(64) NOT NULL, occurred_at timestamptz NOT NULL, "
    "decision varchar(32) NOT NULL, confidence numeric(5,4), deciding_ring varchar(32) NOT NULL, "
    "latency_ms integer NOT NULL, language varchar(32) NOT NULL, "
    "CONSTRAINT pk_scope_decision PRIMARY KEY (event_id), "
    "CONSTRAINT fk_scope_decision_project FOREIGN KEY (project_key) "
    "REFERENCES prep.project_snapshot (project_key) ON DELETE CASCADE, "
    "CONSTRAINT fk_scope_decision_decision FOREIGN KEY (decision) REFERENCES prep.decision (code) ON DELETE RESTRICT, "
    "CONSTRAINT fk_scope_decision_ring FOREIGN KEY (deciding_ring) "
    "REFERENCES prep.deciding_ring (code) ON DELETE RESTRICT, "
    "CONSTRAINT fk_scope_decision_language FOREIGN KEY (language) REFERENCES prep.language (code) ON DELETE RESTRICT, "
    "CONSTRAINT ck_scope_decision_confidence CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1), "
    "CONSTRAINT ck_scope_decision_latency CHECK (latency_ms >= 0))",
    "CREATE INDEX ix_scope_decision_project ON prep.scope_decision (project_key)",
    "CREATE TABLE prep.benchmark_label ("
    "benchmark varchar(40) NOT NULL, case_id varchar(256) NOT NULL, file_path varchar(1024), category varchar(128), "
    "cwe integer, expected_vulnerable boolean NOT NULL, "
    "CONSTRAINT pk_prep_benchmark_label PRIMARY KEY (benchmark, case_id), "
    "CONSTRAINT fk_prep_benchmark_label_benchmark FOREIGN KEY (benchmark) "
    "REFERENCES ingest.benchmark (code) ON DELETE RESTRICT, "
    "CONSTRAINT ck_prep_benchmark_label_cwe CHECK (cwe IS NULL OR cwe > 0))",
    # The records the pipeline set aside: which event (or benchmark label), which filter, why. The record itself stays in
    # raw: nothing is copied here. project_key is NULL for a benchmark label (labels belong to no project).
    "CREATE TABLE quarantine.prep_record ("
    "id uuid NOT NULL, project_key char(64), raw_event_id uuid, benchmark varchar(40), case_id varchar(256), "
    "filter_code varchar(32) NOT NULL, error_code varchar(32) NOT NULL, error_message varchar(500) NOT NULL, "
    "rows_set_aside integer NOT NULL, quarantined_at timestamptz NOT NULL, "
    "CONSTRAINT pk_prep_record PRIMARY KEY (id), "
    "CONSTRAINT fk_prep_record_filter FOREIGN KEY (filter_code) "
    "REFERENCES quarantine.prep_filter (code) ON DELETE RESTRICT, "
    "CONSTRAINT fk_prep_record_error_code FOREIGN KEY (error_code) "
    "REFERENCES quarantine.error_code (code) ON DELETE RESTRICT, "
    "CONSTRAINT ck_prep_record_key CHECK (project_key IS NULL OR project_key ~ '^[0-9a-f]{64}$'), "
    "CONSTRAINT ck_prep_record_subject CHECK ((project_key IS NOT NULL) <> (benchmark IS NOT NULL AND case_id IS NOT NULL)), "
    "CONSTRAINT ck_prep_record_rows CHECK (rows_set_aside >= 0))",
    "CREATE INDEX ix_prep_record_project_key ON quarantine.prep_record (project_key) WHERE project_key IS NOT NULL",
    "INSERT INTO quarantine.error_code (code, description, sort_order) VALUES "
    "('type-mismatch', 'A value does not fit the type, code list or range of its prep column', 4), "
    "('identifier-leak', 'A raw identifier (absolute path, address, at sign) would reach prep', 5), "
    "('secret-match', 'A redaction rule matches a value that would reach prep', 6)",
    "INSERT INTO ingest.project_key_table (code, description, sort_order) VALUES "
    "('prep.service_link', 'Links of a project topology (prep)', 3), "
    "('prep.topology_summary', 'Topology counts of an analysis unit (prep)', 4), "
    "('prep.finding', 'Clean findings (prep)', 5), "
    "('prep.analysis_unit', 'Analysis units and their runtime (prep)', 6), "
    "('prep.scope_decision', 'Scope decisions (prep)', 7), "
    "('prep.project_snapshot', 'Clean project snapshot (prep)', 8), "
    "('quarantine.prep_record', 'Records the preprocessing pipeline set aside', 9)",
)

PREP_TABLES = (
    "prep.project_snapshot, prep.analysis_unit, prep.finding, prep.topology_summary, prep.service_link, "
    "prep.scope_decision, prep.benchmark_label, quarantine.prep_record"
)

GRANTS = (
    f"GRANT USAGE ON SCHEMA prep TO {APP_ROLE}",
    "GRANT SELECT ON " + ", ".join(table for table, _ in LOOKUPS) + f" TO {APP_ROLE}",
    # Written by the pipeline (delete and rewrite per project) and erased on consent_revoked; never updated.
    f"GRANT SELECT, INSERT, DELETE ON {PREP_TABLES} TO {APP_ROLE}",
)


def upgrade() -> None:
    connection = op.get_bind()
    connection.exec_driver_sql("CREATE SCHEMA prep")
    for statement in (*_lookup_statements(), *DDL, *GRANTS):
        connection.exec_driver_sql(statement)


def downgrade() -> None:
    raise NotImplementedError(
        "Migrations are forward-only (acid-3nf-database section 4); fix forward with a new revision."
    )

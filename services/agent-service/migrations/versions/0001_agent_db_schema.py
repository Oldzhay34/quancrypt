"""agent_db schema (P4.2, D-225 ... D-233): 17 lookup tables with their data and 14 entity tables.

Generated from the approved design (docs/data/agent_db-draft.sql, G-AGENT-DB) and kept as plain SQL so the database is the
single source of the constraints (CHECK, UNIQUE, foreign keys). The `vector` extension is not created here: the superuser init
script does (infra/postgres/init/20-agent-db-vector.sh); the migrator role cannot.

Revision ID: 0001
Revises:
"""

from __future__ import annotations

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

APP_ROLE = "agent_db_app"

LOOKUP_TABLES = (
    "message_role",
    "evidence_kind",
    "language",
    "run_trigger",
    "run_status",
    "step_name",
    "step_status",
    "agent",
    "tool",
    "tool_call_status",
    "scope_verdict",
    "scope_ring",
    "kb_source_type",
    "applicability_component",
    "event_type",
    "operation",
    "audit_action",
)

CREATE_LOOKUP = (
    "CREATE TABLE {table} (code varchar(32) NOT NULL, description varchar(200) NOT NULL, sort_order smallint NOT NULL, "
    "CONSTRAINT pk_{table} PRIMARY KEY (code), CONSTRAINT uq_{table}_sort UNIQUE (sort_order))"
)

LOOKUP_DATA = (
    "INSERT INTO message_role VALUES ('USER', 'Kullanıcı mesajı', 1), ('ASSISTANT', 'Asistan yanıtı', 2)",
    "INSERT INTO evidence_kind VALUES\n  ('CODE_LOCATION', 'Dosya:satır kanıtı', 1), ('TOOL_CALL', 'Araç çağrısı kanıtı (tool_call.id)', 2),\n  ('KNOWLEDGE_BASE', 'Bilgi tabanı kaynağı', 3)",
    "INSERT INTO language VALUES ('tr', 'Türkçe', 1), ('en', 'İngilizce', 2)",
    "INSERT INTO run_trigger VALUES\n  ('MESSAGE', 'Sohbet mesajı', 1), ('INITIAL_SCAN', 'İlk tarama', 2), ('PLAN', 'Plan isteği', 3)",
    "INSERT INTO run_status VALUES\n  ('RUNNING', 'Sürüyor', 1), ('COMPLETED', 'Tamamlandı', 2), ('FAILED', 'Hata', 3), ('STOPPED', 'Durduruldu', 4),\n  ('BUDGET_EXCEEDED', 'Bütçe aşıldı', 5)",
    "INSERT INTO step_name VALUES\n  ('INPUT_GUARD', 'Giriş bekçisi (iş akışı düğümü)', 1), ('ROUTE', 'Niyet yönlendirme (iş akışı düğümü)', 2),\n  ('GATHER_CONTEXT', 'Bağlam toplama', 3), ('PLAN', 'Plan', 4), ('ACT', 'Araç çağrıları', 5),\n  ('VERIFY', 'Doğrulama', 6), ('REPORT', 'Rapor', 7), ('ANSWER', 'Yanıt düğümü', 8),\n  ('OUTPUT_GUARD', 'Çıkış denetimi (iş akışı düğümü)', 9)",
    "INSERT INTO step_status VALUES\n  ('SUCCEEDED', 'Başarılı', 1), ('FAILED', 'Hata', 2), ('STOPPED', 'Durduruldu', 3),\n  ('BUDGET_EXCEEDED', 'Bütçe aşıldı', 4)",
    "INSERT INTO agent VALUES\n  ('SUPERVISOR', 'Supervisor', 1), ('DISCOVERY', 'Keşif agent''ı', 2), ('TOPOLOGY', 'Topoloji agent''ı', 3),\n  ('PLANNER', 'Planlama agent''ı', 4)",
    "INSERT INTO tool VALUES\n  ('ANALYZER', 'analyzer_tool', 1), ('CORE', 'core_tool', 2), ('KB_SEARCH', 'kb_search_tool', 3),\n  ('RISK_MODEL', 'risk_model_tool', 4), ('UNKNOWN', 'Kayıtlı olmayan araç adı (yalnız DENIED çağrılar için)', 5)",
    "INSERT INTO tool_call_status VALUES\n  ('SUCCEEDED', 'Başarılı', 1), ('FAILED', 'Hata', 2), ('DENIED', 'İzin listesi dışı, reddedildi', 3),\n  ('TIMED_OUT', 'Zaman aşımı', 4)",
    "INSERT INTO scope_verdict VALUES ('ALLOW', 'Kapsam içi', 1), ('DENY', 'Kapsam dışı veya belirsiz (fail-closed)', 2)",
    "INSERT INTO scope_ring VALUES\n  ('RULE_FILTER', '1. halka: kural filtresi', 1), ('SCOPE_CLASSIFIER', '2. halka: kapsam sınıflandırıcısı', 2),\n  ('LLM_SELF_CHECK', '3. halka: LLM öz-denetimi', 3), ('FAIL_CLOSED', 'Hiçbir halka karar vermedi, ret', 4)",
    "INSERT INTO kb_source_type VALUES\n  ('STANDARD', 'Standart (NIST FIPS, IR)', 1), ('JEP', 'OpenJDK JEP', 2), ('VENDOR_DOC', 'Üretici belgesi', 3),\n  ('SPECIFICATION', 'Teknik şartname (ETSI)', 4), ('GOVERNMENT_GUIDANCE', 'Kurum görüşü (NSA)', 5),\n  ('INTERNAL', 'Quancrypt kendi notu (strateji tablosu)', 6)",
    "INSERT INTO applicability_component VALUES ('JAVA', 'Java ana sürümü', 1), ('SPRING_BOOT', 'Spring Boot ana.yan sürümü', 2)",
    "INSERT INTO event_type VALUES ('scope_decision', 'Kapsam kararı (fact_scope_decision)', 1)",
    "INSERT INTO operation VALUES\n  ('CREATE_SESSION', 'Oturum açma', 1), ('ANSWER_CLARIFICATIONS', 'Netleştirme yanıtlarını kaydetme', 2)",
    "INSERT INTO audit_action VALUES\n  ('SESSION_DELETED', 'Sohbet oturumu silindi (DeleteSession)', 1),\n  ('PROJECT_DATA_DELETED', 'Projenin agent verisi silindi (DeleteProjectData)', 2)",
)

ENTITY_DDL = (
    "CREATE TABLE project_ref (\n  project_id  uuid        NOT NULL,\n  project_key char(64)    NOT NULL,\n  created_at  timestamptz NOT NULL,\n  CONSTRAINT pk_project_ref PRIMARY KEY (project_id),\n  CONSTRAINT ck_project_ref_key CHECK (project_key ~ '^[0-9a-f]{64}$')\n)",
    "CREATE INDEX ix_project_ref_key ON project_ref (project_key)",
    "CREATE TABLE chat_session (\n  id         uuid        NOT NULL,\n  project_id uuid        NOT NULL,\n  language   varchar(32) NOT NULL,\n  created_at timestamptz NOT NULL,\n  CONSTRAINT pk_chat_session PRIMARY KEY (id),\n  CONSTRAINT fk_chat_session_project FOREIGN KEY (project_id) REFERENCES project_ref (project_id) ON DELETE RESTRICT,\n  CONSTRAINT fk_chat_session_language FOREIGN KEY (language) REFERENCES language (code) ON DELETE RESTRICT\n)",
    "CREATE INDEX ix_chat_session_project ON chat_session (project_id)",
    "CREATE TABLE chat_message (\n  id         uuid        NOT NULL,\n  session_id uuid        NOT NULL,\n  ordinal    integer     NOT NULL,\n  role       varchar(32) NOT NULL,\n  content    text        NOT NULL,\n  created_at timestamptz NOT NULL,\n  CONSTRAINT pk_chat_message PRIMARY KEY (id),\n  CONSTRAINT uq_chat_message_order UNIQUE (session_id, ordinal),\n  CONSTRAINT fk_chat_message_session FOREIGN KEY (session_id) REFERENCES chat_session (id) ON DELETE CASCADE,\n  CONSTRAINT fk_chat_message_role FOREIGN KEY (role) REFERENCES message_role (code) ON DELETE RESTRICT,\n  CONSTRAINT ck_chat_message_ordinal CHECK (ordinal > 0),\n  CONSTRAINT ck_chat_message_content CHECK (length(content) > 0)\n)",
    "CREATE TABLE message_evidence (\n  message_id     uuid          NOT NULL,\n  ordinal        integer       NOT NULL,\n  kind           varchar(32)   NOT NULL,\n  reference      varchar(1024) NOT NULL,\n  source_version varchar(64),\n  CONSTRAINT pk_message_evidence PRIMARY KEY (message_id, ordinal),\n  CONSTRAINT fk_message_evidence_message FOREIGN KEY (message_id) REFERENCES chat_message (id) ON DELETE CASCADE,\n  CONSTRAINT fk_message_evidence_kind FOREIGN KEY (kind) REFERENCES evidence_kind (code) ON DELETE RESTRICT,\n  CONSTRAINT ck_message_evidence_ordinal CHECK (ordinal > 0),\n  CONSTRAINT ck_message_evidence_reference CHECK (length(reference) > 0),\n  CONSTRAINT ck_message_evidence_version CHECK (kind = 'KNOWLEDGE_BASE' OR source_version IS NULL)\n)",
    "CREATE TABLE agent_run (\n  id          uuid         NOT NULL,\n  session_id  uuid,\n  run_trigger varchar(32)  NOT NULL,\n  trace_id    char(32)     NOT NULL,\n  status      varchar(32)  NOT NULL,\n  started_at  timestamptz  NOT NULL,\n  finished_at timestamptz,\n  CONSTRAINT pk_agent_run PRIMARY KEY (id),\n  CONSTRAINT fk_agent_run_session FOREIGN KEY (session_id) REFERENCES chat_session (id) ON DELETE SET NULL,\n  CONSTRAINT fk_agent_run_trigger FOREIGN KEY (run_trigger) REFERENCES run_trigger (code) ON DELETE RESTRICT,\n  CONSTRAINT fk_agent_run_status FOREIGN KEY (status) REFERENCES run_status (code) ON DELETE RESTRICT,\n  CONSTRAINT ck_agent_run_trace CHECK (trace_id ~ '^[0-9a-f]{32}$'),\n  CONSTRAINT ck_agent_run_finished CHECK ((status = 'RUNNING') = (finished_at IS NULL)),\n  CONSTRAINT ck_agent_run_order CHECK (finished_at IS NULL OR finished_at >= started_at)\n)",
    "CREATE INDEX ix_agent_run_session ON agent_run (session_id)",
    "CREATE INDEX ix_agent_run_trace ON agent_run (trace_id)",
    "CREATE TABLE agent_step (\n  id                uuid        NOT NULL,\n  run_id            uuid        NOT NULL,\n  ordinal           integer     NOT NULL,\n  step_name         varchar(32) NOT NULL,\n  agent_code        varchar(32),\n  status            varchar(32) NOT NULL,\n  duration_ms       integer     NOT NULL,\n  prompt_tokens     integer     NOT NULL,\n  completion_tokens integer     NOT NULL,\n  started_at        timestamptz NOT NULL,\n  CONSTRAINT pk_agent_step PRIMARY KEY (id),\n  CONSTRAINT uq_agent_step_order UNIQUE (run_id, ordinal),\n  CONSTRAINT fk_agent_step_run FOREIGN KEY (run_id) REFERENCES agent_run (id) ON DELETE CASCADE,\n  CONSTRAINT fk_agent_step_name FOREIGN KEY (step_name) REFERENCES step_name (code) ON DELETE RESTRICT,\n  CONSTRAINT fk_agent_step_agent FOREIGN KEY (agent_code) REFERENCES agent (code) ON DELETE RESTRICT,\n  CONSTRAINT fk_agent_step_status FOREIGN KEY (status) REFERENCES step_status (code) ON DELETE RESTRICT,\n  CONSTRAINT ck_agent_step_ordinal CHECK (ordinal > 0),\n  CONSTRAINT ck_agent_step_duration CHECK (duration_ms >= 0),\n  CONSTRAINT ck_agent_step_tokens CHECK (prompt_tokens >= 0 AND completion_tokens >= 0),\n  CONSTRAINT ck_agent_step_workflow_node CHECK ((step_name IN ('INPUT_GUARD', 'ROUTE', 'ANSWER', 'OUTPUT_GUARD')) = (agent_code IS NULL))\n)",
    "CREATE TABLE tool_call (\n  id          uuid        NOT NULL,\n  step_id     uuid        NOT NULL,\n  tool_code   varchar(32) NOT NULL,\n  status      varchar(32) NOT NULL,\n  duration_ms integer     NOT NULL,\n  called_at   timestamptz NOT NULL,\n  CONSTRAINT pk_tool_call PRIMARY KEY (id),\n  CONSTRAINT fk_tool_call_step FOREIGN KEY (step_id) REFERENCES agent_step (id) ON DELETE CASCADE,\n  CONSTRAINT fk_tool_call_tool FOREIGN KEY (tool_code) REFERENCES tool (code) ON DELETE RESTRICT,\n  CONSTRAINT fk_tool_call_status FOREIGN KEY (status) REFERENCES tool_call_status (code) ON DELETE RESTRICT,\n  CONSTRAINT ck_tool_call_duration CHECK (duration_ms >= 0),\n  CONSTRAINT ck_tool_call_unknown_denied CHECK (tool_code <> 'UNKNOWN' OR status = 'DENIED')\n)",
    "CREATE INDEX ix_tool_call_step ON tool_call (step_id)",
    "CREATE TABLE scope_decision (\n  id            uuid          NOT NULL,\n  session_id    uuid,\n  decision      varchar(32)   NOT NULL,\n  confidence    numeric(5, 4),\n  deciding_ring varchar(32)   NOT NULL,\n  latency_ms    integer       NOT NULL,\n  language      varchar(32)   NOT NULL,\n  decided_at    timestamptz   NOT NULL,\n  CONSTRAINT pk_scope_decision PRIMARY KEY (id),\n  CONSTRAINT fk_scope_decision_session FOREIGN KEY (session_id) REFERENCES chat_session (id) ON DELETE SET NULL,\n  CONSTRAINT fk_scope_decision_decision FOREIGN KEY (decision) REFERENCES scope_verdict (code) ON DELETE RESTRICT,\n  CONSTRAINT fk_scope_decision_ring FOREIGN KEY (deciding_ring) REFERENCES scope_ring (code) ON DELETE RESTRICT,\n  CONSTRAINT fk_scope_decision_language FOREIGN KEY (language) REFERENCES language (code) ON DELETE RESTRICT,\n  CONSTRAINT ck_scope_decision_confidence CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),\n  CONSTRAINT ck_scope_decision_latency CHECK (latency_ms >= 0),\n  CONSTRAINT ck_scope_decision_fail_closed CHECK (deciding_ring <> 'FAIL_CLOSED' OR decision = 'DENY'),\n  CONSTRAINT ck_scope_decision_score CHECK ((deciding_ring = 'SCOPE_CLASSIFIER') = (confidence IS NOT NULL))\n)",
    "CREATE INDEX ix_scope_decision_session ON scope_decision (session_id)",
    "CREATE INDEX ix_scope_decision_time ON scope_decision (decided_at)",
    "CREATE TABLE kb_document (\n  id             uuid          NOT NULL,\n  doc_key        varchar(64)   NOT NULL,\n  title          varchar(300)  NOT NULL,\n  source_url     varchar(1024),\n  source_type    varchar(32)   NOT NULL,\n  version_tag    varchar(64)   NOT NULL,\n  language       varchar(32)   NOT NULL,\n  content_sha256 char(64)      NOT NULL,\n  embedding_model varchar(128) NOT NULL,\n  chunk_chars    integer       NOT NULL,\n  chunk_overlap  integer       NOT NULL,\n  indexed_at     timestamptz   NOT NULL,\n  CONSTRAINT pk_kb_document PRIMARY KEY (id),\n  CONSTRAINT uq_kb_document_key UNIQUE (doc_key),\n  CONSTRAINT fk_kb_document_source_type FOREIGN KEY (source_type) REFERENCES kb_source_type (code) ON DELETE RESTRICT,\n  CONSTRAINT fk_kb_document_language FOREIGN KEY (language) REFERENCES language (code) ON DELETE RESTRICT,\n  CONSTRAINT ck_kb_document_key CHECK (doc_key ~ '^[a-z0-9][a-z0-9._-]{0,63}$'),\n  CONSTRAINT ck_kb_document_title CHECK (length(title) > 0),\n  CONSTRAINT ck_kb_document_url CHECK (source_url IS NULL OR source_url ~ '^https://[^\\s[:cntrl:]]+$'),\n  CONSTRAINT ck_kb_document_url_internal CHECK (source_url IS NOT NULL OR source_type = 'INTERNAL'),\n  CONSTRAINT ck_kb_document_chunking CHECK (chunk_chars > 0 AND chunk_overlap >= 0 AND chunk_overlap < chunk_chars),\n  CONSTRAINT ck_kb_document_version CHECK (length(version_tag) > 0),\n  CONSTRAINT ck_kb_document_sha CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),\n  CONSTRAINT ck_kb_document_model CHECK (length(embedding_model) > 0)\n)",
    "CREATE TABLE kb_document_applicability (\n  document_id uuid        NOT NULL,\n  component   varchar(32) NOT NULL,\n  min_major   smallint,\n  min_minor   smallint,\n  max_major   smallint,\n  max_minor   smallint,\n  CONSTRAINT pk_kb_document_applicability PRIMARY KEY (document_id, component),\n  CONSTRAINT fk_kb_applicability_document FOREIGN KEY (document_id) REFERENCES kb_document (id) ON DELETE CASCADE,\n  CONSTRAINT fk_kb_applicability_component FOREIGN KEY (component) REFERENCES applicability_component (code) ON DELETE RESTRICT,\n  CONSTRAINT ck_kb_applicability_min_pair CHECK ((min_major IS NULL) = (min_minor IS NULL)),\n  CONSTRAINT ck_kb_applicability_max_pair CHECK ((max_major IS NULL) = (max_minor IS NULL)),\n  CONSTRAINT ck_kb_applicability_bound CHECK (min_major IS NOT NULL OR max_major IS NOT NULL),\n  CONSTRAINT ck_kb_applicability_positive CHECK (\n    coalesce(min_major, 0) >= 0 AND coalesce(min_minor, 0) >= 0 AND coalesce(max_major, 0) >= 0 AND coalesce(max_minor, 0) >= 0),\n  CONSTRAINT ck_kb_applicability_java_minor CHECK (component <> 'JAVA' OR (coalesce(min_minor, 0) = 0 AND coalesce(max_minor, 0) = 0)),\n  CONSTRAINT ck_kb_applicability_range CHECK (\n    min_major IS NULL OR max_major IS NULL OR (min_major, min_minor) <= (max_major, max_minor))\n)",
    "CREATE TABLE kb_chunk (\n  id              uuid         NOT NULL,\n  document_id     uuid         NOT NULL,\n  ordinal         integer      NOT NULL,\n  text            text         NOT NULL,\n  embedding       vector(768)  NOT NULL,\n  CONSTRAINT pk_kb_chunk PRIMARY KEY (id),\n  CONSTRAINT uq_kb_chunk_order UNIQUE (document_id, ordinal),\n  CONSTRAINT fk_kb_chunk_document FOREIGN KEY (document_id) REFERENCES kb_document (id) ON DELETE CASCADE,\n  CONSTRAINT ck_kb_chunk_ordinal CHECK (ordinal > 0),\n  CONSTRAINT ck_kb_chunk_text CHECK (length(text) > 0),\n  CONSTRAINT ck_kb_chunk_norm CHECK (vector_norm(embedding) > 0)\n)",
    "CREATE TABLE outbox_event (\n  id             uuid        NOT NULL,\n  event_type     varchar(32) NOT NULL,\n  schema_version integer     NOT NULL,\n  project_key    char(64)    NOT NULL,\n  occurred_at    timestamptz NOT NULL,\n  payload        jsonb       NOT NULL,\n  published_at   timestamptz,\n  CONSTRAINT pk_outbox_event PRIMARY KEY (id),\n  CONSTRAINT fk_outbox_event_type FOREIGN KEY (event_type) REFERENCES event_type (code) ON DELETE RESTRICT,\n  CONSTRAINT ck_outbox_event_version CHECK (schema_version > 0),\n  CONSTRAINT ck_outbox_event_key CHECK (project_key ~ '^[0-9a-f]{64}$'),\n  CONSTRAINT ck_outbox_event_payload CHECK (jsonb_typeof(payload) = 'object'),\n  CONSTRAINT ck_outbox_event_published_after_occurred CHECK (published_at IS NULL OR published_at >= occurred_at)\n)",
    "CREATE INDEX ix_outbox_event_project_key ON outbox_event (project_key)",
    "CREATE INDEX ix_outbox_event_pending ON outbox_event (occurred_at, id) WHERE published_at IS NULL",
    "CREATE TABLE idempotency_record (\n  idempotency_key varchar(128) NOT NULL,\n  operation       varchar(32)  NOT NULL,\n  request_sha256  char(64)     NOT NULL,\n  status_code     smallint     NOT NULL,\n  resource_id     uuid,\n  created_at      timestamptz  NOT NULL,\n  CONSTRAINT pk_idempotency_record PRIMARY KEY (idempotency_key, operation),\n  CONSTRAINT fk_idempotency_operation FOREIGN KEY (operation) REFERENCES operation (code) ON DELETE RESTRICT,\n  CONSTRAINT ck_idempotency_key CHECK (length(btrim(idempotency_key)) > 0 AND length(idempotency_key) <= 128),\n  CONSTRAINT ck_idempotency_sha CHECK (request_sha256 ~ '^[0-9a-f]{64}$'),\n  CONSTRAINT ck_idempotency_status CHECK (status_code BETWEEN 100 AND 599)\n)",
    "CREATE INDEX ix_idempotency_record_created ON idempotency_record (created_at)",
    "CREATE TABLE audit_log (\n  id          uuid        NOT NULL,\n  occurred_at timestamptz NOT NULL,\n  action_code varchar(32) NOT NULL,\n  project_key char(64)    NOT NULL,\n  CONSTRAINT pk_audit_log PRIMARY KEY (id),\n  CONSTRAINT fk_audit_log_action FOREIGN KEY (action_code) REFERENCES audit_action (code) ON DELETE RESTRICT,\n  CONSTRAINT ck_audit_log_key CHECK (project_key ~ '^[0-9a-f]{64}$')\n)",
    "CREATE INDEX ix_audit_log_time ON audit_log (occurred_at)",
)


def upgrade() -> None:
    connection = op.get_bind()
    for table in LOOKUP_TABLES:
        connection.exec_driver_sql(CREATE_LOOKUP.format(table=table))
    for statement in LOOKUP_DATA:
        connection.exec_driver_sql(statement)
    for statement in ENTITY_DDL:
        connection.exec_driver_sql(statement)
    # The application role may read the code lists but never change them (least privilege; the init script's default
    # privileges would have given it DML on every table the migrator creates, D-54).
    tables = ", ".join(LOOKUP_TABLES)
    connection.exec_driver_sql(
        "DO $$ BEGIN IF EXISTS (SELECT FROM pg_roles WHERE rolname = '" + APP_ROLE + "') THEN "
        "EXECUTE 'REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON " + tables + " FROM " + APP_ROLE + "'; END IF; END $$"
    )


def downgrade() -> None:
    raise NotImplementedError(
        "Migrations are forward-only (acid-3nf-database section 4); fix forward with a new revision."
    )

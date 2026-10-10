-- core_db schema (G-CORE-DB, approved 2026-10-09): 43 tables, indexes and 3 views. Copied verbatim from the approved draft DDL.
CREATE TABLE quantum_status (
    code varchar(32) NOT NULL,
    description varchar(200) NOT NULL,
    sort_order int NOT NULL,
    CONSTRAINT pk_quantum_status PRIMARY KEY (code),
    CONSTRAINT ck_quantum_status_sort_order_positive CHECK (sort_order > 0)
);

CREATE TABLE algorithm_family (
    code varchar(32) NOT NULL,
    description varchar(200) NOT NULL,
    sort_order int NOT NULL,
    quantum_status varchar(32),
    CONSTRAINT pk_algorithm_family PRIMARY KEY (code),
    CONSTRAINT ck_algorithm_family_sort_order_positive CHECK (sort_order > 0),
    CONSTRAINT fk_algorithm_family_quantum_status FOREIGN KEY (quantum_status) REFERENCES quantum_status (code) ON DELETE RESTRICT
);

CREATE TABLE usage_context (
    code varchar(32) NOT NULL,
    description varchar(200) NOT NULL,
    sort_order int NOT NULL,
    CONSTRAINT pk_usage_context PRIMARY KEY (code),
    CONSTRAINT ck_usage_context_sort_order_positive CHECK (sort_order > 0)
);

CREATE TABLE location_kind (
    code varchar(32) NOT NULL,
    description varchar(200) NOT NULL,
    sort_order int NOT NULL,
    CONSTRAINT pk_location_kind PRIMARY KEY (code),
    CONSTRAINT ck_location_kind_sort_order_positive CHECK (sort_order > 0)
);

CREATE TABLE priority (
    code varchar(32) NOT NULL,
    description varchar(200) NOT NULL,
    sort_order int NOT NULL,
    CONSTRAINT pk_priority PRIMARY KEY (code),
    CONSTRAINT ck_priority_sort_order_positive CHECK (sort_order > 0)
);

CREATE TABLE effort_level (
    code varchar(32) NOT NULL,
    description varchar(200) NOT NULL,
    sort_order int NOT NULL,
    CONSTRAINT pk_effort_level PRIMARY KEY (code),
    CONSTRAINT ck_effort_level_sort_order_positive CHECK (sort_order > 0)
);

CREATE TABLE strategy (
    code varchar(32) NOT NULL,
    description varchar(200) NOT NULL,
    sort_order int NOT NULL,
    base_effort varchar(32) NOT NULL,
    CONSTRAINT pk_strategy PRIMARY KEY (code),
    CONSTRAINT ck_strategy_sort_order_positive CHECK (sort_order > 0),
    CONSTRAINT fk_strategy_base_effort FOREIGN KEY (base_effort) REFERENCES effort_level (code) ON DELETE RESTRICT
);

CREATE TABLE risk_class (
    code varchar(32) NOT NULL,
    description varchar(200) NOT NULL,
    sort_order int NOT NULL,
    CONSTRAINT pk_risk_class PRIMARY KEY (code),
    CONSTRAINT ck_risk_class_sort_order_positive CHECK (sort_order > 0)
);

CREATE TABLE risk_class_threshold (
    risk_class varchar(32) NOT NULL,
    min_score numeric(5,4) NOT NULL,
    CONSTRAINT pk_risk_class_threshold PRIMARY KEY (risk_class),
    CONSTRAINT uq_risk_class_threshold_min_score UNIQUE (min_score),
    CONSTRAINT ck_risk_class_threshold_min_score_range CHECK (min_score BETWEEN 0 AND 1),
    CONSTRAINT fk_risk_class_threshold_risk_class FOREIGN KEY (risk_class) REFERENCES risk_class (code) ON DELETE RESTRICT
);

CREATE TABLE plan_item_state (
    code varchar(32) NOT NULL,
    description varchar(200) NOT NULL,
    sort_order int NOT NULL,
    CONSTRAINT pk_plan_item_state PRIMARY KEY (code),
    CONSTRAINT ck_plan_item_state_sort_order_positive CHECK (sort_order > 0)
);

CREATE TABLE allowed_transition (
    from_state varchar(32) NOT NULL,
    to_state varchar(32) NOT NULL,
    CONSTRAINT pk_allowed_transition PRIMARY KEY (from_state, to_state),
    CONSTRAINT ck_allowed_transition_states_differ CHECK (from_state <> to_state),
    CONSTRAINT fk_allowed_transition_from_state FOREIGN KEY (from_state) REFERENCES plan_item_state (code) ON DELETE RESTRICT,
    CONSTRAINT fk_allowed_transition_to_state FOREIGN KEY (to_state) REFERENCES plan_item_state (code) ON DELETE RESTRICT
);

CREATE TABLE scan_status (
    code varchar(32) NOT NULL,
    description varchar(200) NOT NULL,
    sort_order int NOT NULL,
    CONSTRAINT pk_scan_status PRIMARY KEY (code),
    CONSTRAINT ck_scan_status_sort_order_positive CHECK (sort_order > 0)
);

CREATE TABLE node_kind (
    code varchar(32) NOT NULL,
    description varchar(200) NOT NULL,
    sort_order int NOT NULL,
    CONSTRAINT pk_node_kind PRIMARY KEY (code),
    CONSTRAINT ck_node_kind_sort_order_positive CHECK (sort_order > 0)
);

CREATE TABLE protocol (
    code varchar(32) NOT NULL,
    description varchar(200) NOT NULL,
    sort_order int NOT NULL,
    CONSTRAINT pk_protocol PRIMARY KEY (code),
    CONSTRAINT ck_protocol_sort_order_positive CHECK (sort_order > 0)
);

CREATE TABLE consent_type (
    code varchar(32) NOT NULL,
    description varchar(200) NOT NULL,
    sort_order int NOT NULL,
    CONSTRAINT pk_consent_type PRIMARY KEY (code),
    CONSTRAINT ck_consent_type_sort_order_positive CHECK (sort_order > 0)
);

CREATE TABLE classified_by (
    code varchar(32) NOT NULL,
    description varchar(200) NOT NULL,
    sort_order int NOT NULL,
    CONSTRAINT pk_classified_by PRIMARY KEY (code),
    CONSTRAINT ck_classified_by_sort_order_positive CHECK (sort_order > 0)
);

CREATE TABLE caller_kind (
    code varchar(32) NOT NULL,
    description varchar(200) NOT NULL,
    sort_order int NOT NULL,
    CONSTRAINT pk_caller_kind PRIMARY KEY (code),
    CONSTRAINT ck_caller_kind_sort_order_positive CHECK (sort_order > 0)
);

CREATE TABLE answer_kind (
    code varchar(32) NOT NULL,
    description varchar(200) NOT NULL,
    sort_order int NOT NULL,
    CONSTRAINT pk_answer_kind PRIMARY KEY (code),
    CONSTRAINT ck_answer_kind_sort_order_positive CHECK (sort_order > 0)
);

CREATE TABLE event_type (
    code varchar(32) NOT NULL,
    description varchar(200) NOT NULL,
    sort_order int NOT NULL,
    CONSTRAINT pk_event_type PRIMARY KEY (code),
    CONSTRAINT ck_event_type_sort_order_positive CHECK (sort_order > 0)
);

CREATE TABLE audit_action (
    code varchar(32) NOT NULL,
    description varchar(200) NOT NULL,
    sort_order int NOT NULL,
    CONSTRAINT pk_audit_action PRIMARY KEY (code),
    CONSTRAINT ck_audit_action_sort_order_positive CHECK (sort_order > 0)
);

CREATE TABLE clarification_question (
    code varchar(32) NOT NULL,
    text_tr varchar(300) NOT NULL,
    text_en varchar(300) NOT NULL,
    answer_kind varchar(32) NOT NULL,
    sort_order int NOT NULL,
    CONSTRAINT pk_clarification_question PRIMARY KEY (code),
    CONSTRAINT uq_clarification_question_sort_order UNIQUE (sort_order),
    CONSTRAINT fk_clarification_question_answer_kind FOREIGN KEY (answer_kind) REFERENCES answer_kind (code) ON DELETE RESTRICT
);

CREATE TABLE clarification_option (
    question_code varchar(32) NOT NULL,
    option_code varchar(32) NOT NULL,
    text_tr varchar(100) NOT NULL,
    text_en varchar(100) NOT NULL,
    sort_order int NOT NULL,
    CONSTRAINT pk_clarification_option PRIMARY KEY (question_code, option_code),
    CONSTRAINT uq_clarification_option_question_sort UNIQUE (question_code, sort_order),
    CONSTRAINT fk_clarification_option_question_code FOREIGN KEY (question_code) REFERENCES clarification_question (code) ON DELETE CASCADE
);

CREATE TABLE project (
    id uuid NOT NULL,
    project_key char(64) NOT NULL,
    display_name varchar(200) NOT NULL,
    created_at timestamptz NOT NULL,
    CONSTRAINT pk_project PRIMARY KEY (id),
    CONSTRAINT uq_project_project_key UNIQUE (project_key),
    CONSTRAINT ck_project_project_key_hex CHECK (project_key ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_project_display_name_not_blank CHECK (length(btrim(display_name)) > 0)
);

CREATE TABLE project_runtime_profile (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    sequence_no int NOT NULL,
    java_version varchar(32) NOT NULL,
    spring_boot_version varchar(32),
    recorded_at timestamptz NOT NULL,
    CONSTRAINT pk_project_runtime_profile PRIMARY KEY (id),
    CONSTRAINT uq_project_runtime_profile_project_sequence UNIQUE (project_id, sequence_no),
    CONSTRAINT ck_project_runtime_profile_sequence_positive CHECK (sequence_no > 0),
    CONSTRAINT fk_project_runtime_profile_project_id FOREIGN KEY (project_id) REFERENCES project (id) ON DELETE CASCADE
);

CREATE TABLE privacy_notice (
    id uuid NOT NULL,
    version int NOT NULL,
    text_tr text NOT NULL,
    text_en text NOT NULL,
    published_at timestamptz NOT NULL,
    CONSTRAINT pk_privacy_notice PRIMARY KEY (id),
    CONSTRAINT uq_privacy_notice_version UNIQUE (version),
    CONSTRAINT ck_privacy_notice_version_positive CHECK (version > 0)
);

CREATE TABLE consent (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    consent_type varchar(32) NOT NULL,
    privacy_notice_id uuid NOT NULL,
    granted_at timestamptz NOT NULL,
    revoked_at timestamptz,
    version int NOT NULL,
    CONSTRAINT pk_consent PRIMARY KEY (id),
    CONSTRAINT uq_consent_project_type UNIQUE (project_id, consent_type),
    CONSTRAINT ck_consent_revoked_after_granted CHECK (revoked_at IS NULL OR revoked_at >= granted_at),
    CONSTRAINT ck_consent_version_non_negative CHECK (version >= 0),
    CONSTRAINT fk_consent_project_id FOREIGN KEY (project_id) REFERENCES project (id) ON DELETE CASCADE,
    CONSTRAINT fk_consent_consent_type FOREIGN KEY (consent_type) REFERENCES consent_type (code) ON DELETE RESTRICT,
    CONSTRAINT fk_consent_privacy_notice_id FOREIGN KEY (privacy_notice_id) REFERENCES privacy_notice (id) ON DELETE RESTRICT
);
CREATE INDEX ix_consent_privacy_notice_id ON consent (privacy_notice_id);

CREATE TABLE clarification_answer (
    project_id uuid NOT NULL,
    question_code varchar(32) NOT NULL,
    option_code varchar(32),
    free_text varchar(500),
    answered_at timestamptz NOT NULL,
    CONSTRAINT pk_clarification_answer PRIMARY KEY (project_id, question_code),
    CONSTRAINT ck_clarification_answer_answer_present CHECK (option_code IS NOT NULL OR free_text IS NOT NULL),
    CONSTRAINT ck_clarification_answer_free_text_not_blank CHECK (free_text IS NULL OR length(btrim(free_text)) > 0),
    CONSTRAINT fk_clarification_answer_project_id FOREIGN KEY (project_id) REFERENCES project (id) ON DELETE CASCADE,
    CONSTRAINT fk_clarification_answer_question_code_option_code FOREIGN KEY (question_code, option_code) REFERENCES clarification_option (question_code, option_code) ON DELETE RESTRICT,
    CONSTRAINT fk_clarification_answer_question_code FOREIGN KEY (question_code) REFERENCES clarification_question (code) ON DELETE RESTRICT
);

CREATE TABLE scan (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    runtime_profile_sequence_no int,
    status varchar(32) NOT NULL,
    started_at timestamptz NOT NULL,
    completed_at timestamptz,
    CONSTRAINT pk_scan PRIMARY KEY (id),
    CONSTRAINT ck_scan_completed_matches_status CHECK ((status = 'RUNNING') = (completed_at IS NULL)),
    CONSTRAINT ck_scan_completed_after_started CHECK (completed_at IS NULL OR completed_at >= started_at),
    CONSTRAINT fk_scan_project_id FOREIGN KEY (project_id) REFERENCES project (id) ON DELETE CASCADE,
    CONSTRAINT fk_scan_project_id_runtime_profile_sequence_no FOREIGN KEY (project_id, runtime_profile_sequence_no) REFERENCES project_runtime_profile (project_id, sequence_no) ON DELETE CASCADE,
    CONSTRAINT fk_scan_status FOREIGN KEY (status) REFERENCES scan_status (code) ON DELETE RESTRICT
);
CREATE INDEX ix_scan_project_id_runtime_profile_sequence_no ON scan (project_id, runtime_profile_sequence_no);
CREATE UNIQUE INDEX uq_scan_one_running_per_project ON scan (project_id) WHERE status = 'RUNNING';

CREATE TABLE source_file (
    id uuid NOT NULL,
    scan_id uuid NOT NULL,
    path varchar(1024) NOT NULL,
    location_kind varchar(32) NOT NULL,
    CONSTRAINT pk_source_file PRIMARY KEY (id),
    CONSTRAINT uq_source_file_scan_path UNIQUE (scan_id, path),
    CONSTRAINT ck_source_file_path_not_blank CHECK (length(btrim(path)) > 0),
    CONSTRAINT fk_source_file_scan_id FOREIGN KEY (scan_id) REFERENCES scan (id) ON DELETE CASCADE,
    CONSTRAINT fk_source_file_location_kind FOREIGN KEY (location_kind) REFERENCES location_kind (code) ON DELETE RESTRICT
);

CREATE TABLE finding (
    id uuid NOT NULL,
    source_file_id uuid NOT NULL,
    symbol varchar(512) NOT NULL,
    algorithm_family varchar(32) NOT NULL,
    usage_context varchar(32) NOT NULL,
    priority varchar(32) NOT NULL,
    key_size_bits int,
    line_start int,
    line_end int,
    confidence numeric(4,3) NOT NULL,
    classified_by varchar(32) NOT NULL,
    CONSTRAINT pk_finding PRIMARY KEY (id),
    CONSTRAINT uq_finding_location UNIQUE NULLS NOT DISTINCT (source_file_id, symbol, algorithm_family, usage_context, line_start),
    CONSTRAINT ck_finding_key_size_positive CHECK (key_size_bits IS NULL OR key_size_bits > 0),
    CONSTRAINT ck_finding_lines_together CHECK ((line_start IS NULL) = (line_end IS NULL)),
    CONSTRAINT ck_finding_line_start_positive CHECK (line_start IS NULL OR line_start > 0),
    CONSTRAINT ck_finding_line_order CHECK (line_end IS NULL OR line_end >= line_start),
    CONSTRAINT ck_finding_confidence_range CHECK (confidence BETWEEN 0 AND 1),
    CONSTRAINT ck_finding_symbol_not_blank CHECK (length(btrim(symbol)) > 0),
    CONSTRAINT fk_finding_source_file_id FOREIGN KEY (source_file_id) REFERENCES source_file (id) ON DELETE CASCADE,
    CONSTRAINT fk_finding_algorithm_family FOREIGN KEY (algorithm_family) REFERENCES algorithm_family (code) ON DELETE RESTRICT,
    CONSTRAINT fk_finding_usage_context FOREIGN KEY (usage_context) REFERENCES usage_context (code) ON DELETE RESTRICT,
    CONSTRAINT fk_finding_priority FOREIGN KEY (priority) REFERENCES priority (code) ON DELETE RESTRICT,
    CONSTRAINT fk_finding_classified_by FOREIGN KEY (classified_by) REFERENCES classified_by (code) ON DELETE RESTRICT
);

CREATE TABLE scan_artifact (
    id uuid NOT NULL,
    scan_id uuid NOT NULL,
    content bytea NOT NULL,
    content_type varchar(100) NOT NULL,
    sha256 char(64) NOT NULL,
    created_at timestamptz NOT NULL,
    CONSTRAINT pk_scan_artifact PRIMARY KEY (id),
    CONSTRAINT uq_scan_artifact_scan UNIQUE (scan_id),
    CONSTRAINT ck_scan_artifact_sha256_hex CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_scan_artifact_content_type_not_blank CHECK (length(btrim(content_type)) > 0),
    CONSTRAINT fk_scan_artifact_scan_id FOREIGN KEY (scan_id) REFERENCES scan (id) ON DELETE CASCADE
);

CREATE TABLE topology (
    id uuid NOT NULL,
    scan_id uuid NOT NULL,
    recorded_at timestamptz NOT NULL,
    CONSTRAINT pk_topology PRIMARY KEY (id),
    CONSTRAINT uq_topology_scan UNIQUE (scan_id),
    CONSTRAINT fk_topology_scan_id FOREIGN KEY (scan_id) REFERENCES scan (id) ON DELETE CASCADE
);

CREATE TABLE service_node (
    id uuid NOT NULL,
    topology_id uuid NOT NULL,
    name varchar(200) NOT NULL,
    node_kind varchar(32) NOT NULL,
    CONSTRAINT pk_service_node PRIMARY KEY (id),
    CONSTRAINT uq_service_node_topology_name UNIQUE (topology_id, name),
    CONSTRAINT ck_service_node_name_not_blank CHECK (length(btrim(name)) > 0),
    CONSTRAINT fk_service_node_topology_id FOREIGN KEY (topology_id) REFERENCES topology (id) ON DELETE CASCADE,
    CONSTRAINT fk_service_node_node_kind FOREIGN KEY (node_kind) REFERENCES node_kind (code) ON DELETE RESTRICT
);

CREATE TABLE service_link (
    id uuid NOT NULL,
    source_node_id uuid NOT NULL,
    target_node_id uuid NOT NULL,
    protocol varchar(32) NOT NULL,
    tls boolean NOT NULL,
    mtls boolean NOT NULL,
    CONSTRAINT pk_service_link PRIMARY KEY (id),
    CONSTRAINT uq_service_link_edge UNIQUE (source_node_id, target_node_id, protocol),
    CONSTRAINT ck_service_link_no_self_link CHECK (source_node_id <> target_node_id),
    CONSTRAINT ck_service_link_mtls_needs_tls CHECK (NOT mtls OR tls),
    CONSTRAINT fk_service_link_source_node_id FOREIGN KEY (source_node_id) REFERENCES service_node (id) ON DELETE CASCADE,
    CONSTRAINT fk_service_link_target_node_id FOREIGN KEY (target_node_id) REFERENCES service_node (id) ON DELETE CASCADE,
    CONSTRAINT fk_service_link_protocol FOREIGN KEY (protocol) REFERENCES protocol (code) ON DELETE RESTRICT
);
CREATE INDEX ix_service_link_target_node_id ON service_link (target_node_id);

CREATE TABLE link_call_site (
    id uuid NOT NULL,
    link_id uuid NOT NULL,
    source_file_id uuid NOT NULL,
    line_start int NOT NULL,
    line_end int NOT NULL,
    CONSTRAINT pk_link_call_site PRIMARY KEY (id),
    CONSTRAINT uq_link_call_site_site UNIQUE (link_id, source_file_id, line_start),
    CONSTRAINT ck_link_call_site_line_start_positive CHECK (line_start > 0),
    CONSTRAINT ck_link_call_site_line_order CHECK (line_end >= line_start),
    CONSTRAINT fk_link_call_site_link_id FOREIGN KEY (link_id) REFERENCES service_link (id) ON DELETE CASCADE,
    CONSTRAINT fk_link_call_site_source_file_id FOREIGN KEY (source_file_id) REFERENCES source_file (id) ON DELETE CASCADE
);
CREATE INDEX ix_link_call_site_source_file_id ON link_call_site (source_file_id);

CREATE TABLE link_finding (
    link_id uuid NOT NULL,
    finding_id uuid NOT NULL,
    CONSTRAINT pk_link_finding PRIMARY KEY (link_id, finding_id),
    CONSTRAINT fk_link_finding_link_id FOREIGN KEY (link_id) REFERENCES service_link (id) ON DELETE CASCADE,
    CONSTRAINT fk_link_finding_finding_id FOREIGN KEY (finding_id) REFERENCES finding (id) ON DELETE CASCADE
);
CREATE INDEX ix_link_finding_finding_id ON link_finding (finding_id);

CREATE TABLE plan (
    id uuid NOT NULL,
    scan_id uuid NOT NULL,
    created_at timestamptz NOT NULL,
    CONSTRAINT pk_plan PRIMARY KEY (id),
    CONSTRAINT uq_plan_scan UNIQUE (scan_id),
    CONSTRAINT fk_plan_scan_id FOREIGN KEY (scan_id) REFERENCES scan (id) ON DELETE CASCADE
);

CREATE TABLE plan_item (
    id uuid NOT NULL,
    plan_id uuid NOT NULL,
    finding_id uuid NOT NULL,
    strategy varchar(32) NOT NULL,
    effort varchar(32) NOT NULL,
    risk_score numeric(5,4) NOT NULL,
    state varchar(32) NOT NULL,
    version int NOT NULL,
    CONSTRAINT pk_plan_item PRIMARY KEY (id),
    CONSTRAINT uq_plan_item_finding UNIQUE (finding_id),
    CONSTRAINT ck_plan_item_risk_score_range CHECK (risk_score BETWEEN 0 AND 1),
    CONSTRAINT ck_plan_item_version_non_negative CHECK (version >= 0),
    CONSTRAINT fk_plan_item_plan_id FOREIGN KEY (plan_id) REFERENCES plan (id) ON DELETE CASCADE,
    CONSTRAINT fk_plan_item_finding_id FOREIGN KEY (finding_id) REFERENCES finding (id) ON DELETE CASCADE,
    CONSTRAINT fk_plan_item_strategy FOREIGN KEY (strategy) REFERENCES strategy (code) ON DELETE RESTRICT,
    CONSTRAINT fk_plan_item_effort FOREIGN KEY (effort) REFERENCES effort_level (code) ON DELETE RESTRICT,
    CONSTRAINT fk_plan_item_state FOREIGN KEY (state) REFERENCES plan_item_state (code) ON DELETE RESTRICT
);
CREATE INDEX ix_plan_item_plan_id_state ON plan_item (plan_id, state);

CREATE TABLE plan_item_risk_factor (
    plan_item_id uuid NOT NULL,
    rank_no int NOT NULL,
    feature_name varchar(100) NOT NULL,
    shap_value numeric(9,6) NOT NULL,
    CONSTRAINT pk_plan_item_risk_factor PRIMARY KEY (plan_item_id, rank_no),
    CONSTRAINT uq_plan_item_risk_factor_item_feature UNIQUE (plan_item_id, feature_name),
    CONSTRAINT ck_plan_item_risk_factor_rank_positive CHECK (rank_no > 0),
    CONSTRAINT ck_plan_item_risk_factor_feature_name_pattern CHECK (feature_name ~ '^[a-z][a-z0-9_]{0,99}$'),
    CONSTRAINT fk_plan_item_risk_factor_plan_item_id FOREIGN KEY (plan_item_id) REFERENCES plan_item (id) ON DELETE CASCADE
);

CREATE TABLE plan_item_state_transition (
    id uuid NOT NULL,
    plan_item_id uuid NOT NULL,
    from_state varchar(32) NOT NULL,
    to_state varchar(32) NOT NULL,
    transitioned_at timestamptz NOT NULL,
    caller_kind varchar(32) NOT NULL,
    CONSTRAINT pk_plan_item_state_transition PRIMARY KEY (id),
    CONSTRAINT ck_plan_item_state_transition_states_differ CHECK (from_state <> to_state),
    CONSTRAINT fk_plan_item_state_transition_plan_item_id FOREIGN KEY (plan_item_id) REFERENCES plan_item (id) ON DELETE CASCADE,
    CONSTRAINT fk_plan_item_state_transition_from_state_to_state FOREIGN KEY (from_state, to_state) REFERENCES allowed_transition (from_state, to_state) ON DELETE RESTRICT,
    CONSTRAINT fk_plan_item_state_transition_caller_kind FOREIGN KEY (caller_kind) REFERENCES caller_kind (code) ON DELETE RESTRICT
);
CREATE INDEX ix_plan_item_state_transition_plan_item_id_transitioned_at ON plan_item_state_transition (plan_item_id, transitioned_at);

CREATE TABLE audit_log (
    id uuid NOT NULL,
    occurred_at timestamptz NOT NULL,
    action_code varchar(32) NOT NULL,
    project_key char(64),
    subject_id uuid,
    caller_kind varchar(32) NOT NULL,
    CONSTRAINT pk_audit_log PRIMARY KEY (id),
    CONSTRAINT ck_audit_log_project_key_hex CHECK (project_key IS NULL OR project_key ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_audit_log_project_key_required CHECK (project_key IS NOT NULL OR action_code = 'OUTBOX_EVENTS_RELAYED'),
    CONSTRAINT fk_audit_log_action_code FOREIGN KEY (action_code) REFERENCES audit_action (code) ON DELETE RESTRICT,
    CONSTRAINT fk_audit_log_caller_kind FOREIGN KEY (caller_kind) REFERENCES caller_kind (code) ON DELETE RESTRICT
);
CREATE INDEX ix_audit_log_project_key_occurred_at ON audit_log (project_key, occurred_at);

CREATE TABLE outbox_event (
    id uuid NOT NULL,
    event_type varchar(32) NOT NULL,
    schema_version int NOT NULL,
    project_key char(64) NOT NULL,
    occurred_at timestamptz NOT NULL,
    payload jsonb NOT NULL,
    published_at timestamptz,
    CONSTRAINT pk_outbox_event PRIMARY KEY (id),
    CONSTRAINT ck_outbox_event_project_key_hex CHECK (project_key ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_outbox_event_schema_version_positive CHECK (schema_version > 0),
    CONSTRAINT ck_outbox_event_published_after_occurred CHECK (published_at IS NULL OR published_at >= occurred_at),
    CONSTRAINT fk_outbox_event_event_type FOREIGN KEY (event_type) REFERENCES event_type (code) ON DELETE RESTRICT
);
CREATE INDEX ix_outbox_event_project_key ON outbox_event (project_key);
CREATE INDEX ix_outbox_event_pending ON outbox_event (occurred_at) WHERE published_at IS NULL;

CREATE TABLE idempotency_record (
    idempotency_key varchar(128) NOT NULL,
    operation_code varchar(32) NOT NULL,
    request_sha256 char(64) NOT NULL,
    status_code smallint NOT NULL,
    resource_id uuid,
    created_at timestamptz NOT NULL,
    CONSTRAINT pk_idempotency_record PRIMARY KEY (idempotency_key, operation_code),
    CONSTRAINT ck_idempotency_record_request_sha256_hex CHECK (request_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_idempotency_record_status_code_range CHECK (status_code BETWEEN 100 AND 599),
    CONSTRAINT ck_idempotency_record_key_not_blank CHECK (length(btrim(idempotency_key)) > 0),
    CONSTRAINT fk_idempotency_record_operation_code FOREIGN KEY (operation_code) REFERENCES audit_action (code) ON DELETE RESTRICT
);
CREATE INDEX ix_idempotency_record_created_at ON idempotency_record (created_at);

CREATE VIEW v_project_current_runtime AS
SELECT DISTINCT ON (project_id) project_id, sequence_no, java_version, spring_boot_version, recorded_at
FROM project_runtime_profile ORDER BY project_id, sequence_no DESC;

CREATE VIEW v_plan_item_risk AS
SELECT pi.id AS plan_item_id, pi.risk_score,
       (SELECT t.risk_class FROM risk_class_threshold t WHERE t.min_score <= pi.risk_score ORDER BY t.min_score DESC LIMIT 1) AS risk_class
FROM plan_item pi;

CREATE VIEW v_finding_call_site_count AS
SELECT f.id AS finding_id, count(cs.id) AS call_site_count
FROM finding f LEFT JOIN link_finding lf ON lf.finding_id = f.id LEFT JOIN link_call_site cs ON cs.link_id = lf.link_id
GROUP BY f.id;

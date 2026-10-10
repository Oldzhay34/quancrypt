-- One valid row (two where a constraint needs a specific one) in every entity table, so each CHECK, UNIQUE and
-- FOREIGN KEY constraint can be violated by changing or copying a single row (ConstraintCatalogTest).
INSERT INTO project (id, project_key, display_name, created_at)
VALUES ('10000000-0000-4000-8000-000000000001', repeat('a', 64), 'Demo', TIMESTAMPTZ '2026-10-09 10:00:00+00');
INSERT INTO project_runtime_profile (id, project_id, sequence_no, java_version, spring_boot_version, recorded_at) VALUES
    ('10000000-0000-4000-8000-000000000002', '10000000-0000-4000-8000-000000000001', 1, '21', '4.1.1', TIMESTAMPTZ '2026-10-09 10:00:01+00'),
    ('10000000-0000-4000-8000-000000000003', '10000000-0000-4000-8000-000000000001', 2, '25', NULL, TIMESTAMPTZ '2026-10-09 10:00:02+00');
INSERT INTO consent (id, project_id, consent_type, privacy_notice_id, granted_at, revoked_at, version)
SELECT '10000000-0000-4000-8000-000000000004', '10000000-0000-4000-8000-000000000001', 'WAREHOUSE_ANALYTICS', id,
       TIMESTAMPTZ '2026-10-09 10:00:03+00', NULL, 0
FROM privacy_notice WHERE version = 1;
INSERT INTO clarification_answer (project_id, question_code, option_code, free_text, answered_at) VALUES
    ('10000000-0000-4000-8000-000000000001', 'TLS_TERMINATION', 'INGRESS', NULL, TIMESTAMPTZ '2026-10-09 10:00:04+00'),
    ('10000000-0000-4000-8000-000000000001', 'DEVICE_HARDWARE_OPENSSL', NULL, 'PYNQ-Z2', TIMESTAMPTZ '2026-10-09 10:00:04+00');
INSERT INTO scan (id, project_id, runtime_profile_sequence_no, status, started_at, completed_at) VALUES
    ('10000000-0000-4000-8000-000000000005', '10000000-0000-4000-8000-000000000001', NULL, 'COMPLETED',
     TIMESTAMPTZ '2026-10-09 10:01:00+00', TIMESTAMPTZ '2026-10-09 10:02:00+00'),
    ('10000000-0000-4000-8000-000000000006', '10000000-0000-4000-8000-000000000001', 1, 'RUNNING',
     TIMESTAMPTZ '2026-10-09 10:03:00+00', NULL);
INSERT INTO source_file (id, scan_id, path, location_kind)
VALUES ('10000000-0000-4000-8000-000000000007', '10000000-0000-4000-8000-000000000005', 'src/main/java/Tls.java', 'CODE');
INSERT INTO finding (id, source_file_id, symbol, algorithm_family, usage_context, priority, key_size_bits, line_start, line_end,
                     confidence, classified_by)
VALUES ('10000000-0000-4000-8000-000000000008', '10000000-0000-4000-8000-000000000007', 'Tls#handshake', 'RSA', 'TLS_KEY_EXCHANGE',
        'P1', 2048, 10, 12, 0.900, 'STATIC');
INSERT INTO scan_artifact (id, scan_id, content, content_type, sha256, created_at)
VALUES ('10000000-0000-4000-8000-000000000009', '10000000-0000-4000-8000-000000000005', '\x7b7d'::bytea, 'application/json',
        repeat('b', 64), TIMESTAMPTZ '2026-10-09 10:02:00+00');
INSERT INTO topology (id, scan_id, recorded_at)
VALUES ('10000000-0000-4000-8000-000000000010', '10000000-0000-4000-8000-000000000005', TIMESTAMPTZ '2026-10-09 10:02:00+00');
INSERT INTO service_node (id, topology_id, name, node_kind) VALUES
    ('10000000-0000-4000-8000-000000000011', '10000000-0000-4000-8000-000000000010', 'gateway', 'GATEWAY'),
    ('10000000-0000-4000-8000-000000000012', '10000000-0000-4000-8000-000000000010', 'account', 'SERVICE');
INSERT INTO service_link (id, source_node_id, target_node_id, protocol, tls, mtls)
VALUES ('10000000-0000-4000-8000-000000000013', '10000000-0000-4000-8000-000000000011', '10000000-0000-4000-8000-000000000012',
        'HTTP', true, true);
INSERT INTO link_call_site (id, link_id, source_file_id, line_start, line_end)
VALUES ('10000000-0000-4000-8000-000000000014', '10000000-0000-4000-8000-000000000013', '10000000-0000-4000-8000-000000000007', 20, 21);
INSERT INTO link_finding (link_id, finding_id)
VALUES ('10000000-0000-4000-8000-000000000013', '10000000-0000-4000-8000-000000000008');
INSERT INTO plan (id, scan_id, created_at)
VALUES ('10000000-0000-4000-8000-000000000015', '10000000-0000-4000-8000-000000000005', TIMESTAMPTZ '2026-10-09 10:04:00+00');
INSERT INTO plan_item (id, plan_id, finding_id, strategy, effort, risk_score, state, version)
VALUES ('10000000-0000-4000-8000-000000000016', '10000000-0000-4000-8000-000000000015', '10000000-0000-4000-8000-000000000008',
        'HYBRID_TLS_KEX', 'M', 0.5000, 'PLANNED', 1);
INSERT INTO plan_item_risk_factor (plan_item_id, rank_no, feature_name, shap_value)
VALUES ('10000000-0000-4000-8000-000000000016', 1, 'algorithm_weakness', 0.400000);
INSERT INTO plan_item_state_transition (id, plan_item_id, from_state, to_state, transitioned_at, caller_kind)
VALUES ('10000000-0000-4000-8000-000000000017', '10000000-0000-4000-8000-000000000016', 'DISCOVERED', 'PLANNED',
        TIMESTAMPTZ '2026-10-09 10:04:00+00', 'UI');
INSERT INTO audit_log (id, occurred_at, action_code, project_key, subject_id, caller_kind)
VALUES ('10000000-0000-4000-8000-000000000018', TIMESTAMPTZ '2026-10-09 10:00:00+00', 'PROJECT_REGISTERED', repeat('a', 64), NULL, 'UI');
INSERT INTO outbox_event (id, event_type, schema_version, project_key, occurred_at, payload, published_at)
VALUES ('10000000-0000-4000-8000-000000000019', 'scan_completed', 1, repeat('a', 64), TIMESTAMPTZ '2026-10-09 10:02:00+00',
        '{"finding_count": 1}'::jsonb, NULL);
INSERT INTO idempotency_record (idempotency_key, operation_code, request_sha256, status_code, resource_id, created_at)
VALUES ('key-1', 'SCAN_STARTED', repeat('c', 64), 201, '10000000-0000-4000-8000-000000000006', TIMESTAMPTZ '2026-10-09 10:03:00+00');

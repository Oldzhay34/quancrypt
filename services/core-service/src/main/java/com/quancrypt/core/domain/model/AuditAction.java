package com.quancrypt.core.domain.model;

/** Audit action, one per write use case; also the idempotency operation code (D-125). */
public enum AuditAction {
    PROJECT_REGISTERED,
    RUNTIME_PROFILE_RECORDED,
    PROJECT_DELETED,
    CONSENT_GRANTED,
    CONSENT_REVOKED,
    SCAN_STARTED,
    FINDINGS_RECORDED,
    TOPOLOGY_RECORDED,
    SCAN_ARTIFACT_RECORDED,
    SCAN_COMPLETED,
    CLARIFICATION_ANSWERS_SAVED,
    PLAN_CREATED,
    PLAN_ITEM_TRANSITIONED,
    OUTBOX_EVENTS_RELAYED;
}

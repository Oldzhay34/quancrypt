package com.quancrypt.core.domain.model;

/** Domain event types written to the outbox (D-20). */
public enum EventType {
    FINDING_DETECTED("finding_detected"),
    TOPOLOGY_RECORDED("topology_recorded"),
    SCAN_COMPLETED("scan_completed"),
    PLAN_CREATED("plan_created"),
    PLAN_ITEM_TRANSITIONED("plan_item_transitioned"),
    PROJECT_RUNTIME_CHANGED("project_runtime_changed"),
    CONSENT_REVOKED("consent_revoked");

    private final String code;

    EventType(String code) {
        this.code = code;
    }

    /** Wire code used in the event schemas. */
    public String code() {
        return code;
    }
}

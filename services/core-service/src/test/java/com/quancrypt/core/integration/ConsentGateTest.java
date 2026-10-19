package com.quancrypt.core.integration;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.core.integration.support.IntegrationTest;
import com.quancrypt.core.port.inbound.GrantConsentCommand;
import com.quancrypt.core.port.inbound.RecordRuntimeProfileCommand;
import com.quancrypt.core.port.inbound.RevokeConsentCommand;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.Test;

/**
 * D-21: without WAREHOUSE_ANALYTICS consent the analysis runs but writes no event; revoking it drops pending events
 * except earlier revocations (D-132, D-147) and always writes consent_revoked; MODEL_TRAINING alone gates nothing.
 */
class ConsentGateTest extends IntegrationTest {

    private List<String> pendingTypes() {
        return jdbc.sql("SELECT event_type FROM outbox_event WHERE published_at IS NULL ORDER BY occurred_at, id").query(String.class).list();
    }

    @Test
    void noConsentNoEventsButTheAnalysisIsStored() {
        UUID projectId = project("/work/demo");
        grantConsent.execute(new GrantConsentCommand(projectId, "MODEL_TRAINING", 2, Optional.empty(), Optional.empty(), "UI"));
        recordRuntimeProfile.execute(new RecordRuntimeProfileCommand(projectId, "21", Optional.empty(), Optional.empty(), "UI"));
        UUID scanId = runningScan(projectId);
        List<UUID> ids = record(scanId, tlsFinding("src/main/java/Tls.java", "Tls#a")).createdIds();
        complete(scanId);
        plan(scanId, ids);

        assertThat(rows("finding")).isEqualTo(1);
        assertThat(rows("plan_item")).isEqualTo(1);
        assertThat(rows("outbox_event")).isZero();
    }

    @Test
    void withConsentEventsAreWrittenAndRevokingDropsThePendingOnes() {
        UUID projectId = projectWithConsent("/work/demo");
        UUID scanId = runningScan(projectId);
        record(scanId, tlsFinding("src/main/java/Tls.java", "Tls#a"));
        complete(scanId);
        assertThat(pendingTypes()).containsExactly("finding_detected", "scan_completed");

        revokeConsent.execute(new RevokeConsentCommand(projectId, "WAREHOUSE_ANALYTICS", 0, "UI"));
        assertThat(pendingTypes()).containsExactly("consent_revoked");

        grantConsent.execute(new GrantConsentCommand(projectId, "WAREHOUSE_ANALYTICS", 2, Optional.of(1), Optional.empty(), "UI"));
        recordRuntimeProfile.execute(new RecordRuntimeProfileCommand(projectId, "21", Optional.empty(), Optional.empty(), "UI"));
        revokeConsent.execute(new RevokeConsentCommand(projectId, "WAREHOUSE_ANALYTICS", 2, "UI"));
        assertThat(pendingTypes()).containsExactly("consent_revoked", "consent_revoked");
    }
}

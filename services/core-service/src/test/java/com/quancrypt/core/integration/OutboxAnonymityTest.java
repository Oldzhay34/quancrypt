package com.quancrypt.core.integration;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.core.infrastructure.anonymization.RedactionRules;
import com.quancrypt.core.infrastructure.anonymization.Redactor;
import com.quancrypt.core.integration.support.IntegrationTest;
import com.quancrypt.core.port.inbound.CallSiteInput;
import com.quancrypt.core.port.inbound.DeleteProjectCommand;
import com.quancrypt.core.port.inbound.GrantConsentCommand;
import com.quancrypt.core.port.inbound.LinkInput;
import com.quancrypt.core.port.inbound.NodeInput;
import com.quancrypt.core.port.inbound.RecordRuntimeProfileCommand;
import com.quancrypt.core.port.inbound.RecordTopologyCommand;
import com.quancrypt.core.port.inbound.RegisterProjectCommand;
import com.quancrypt.core.port.inbound.TransitionPlanItemCommand;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.junit.jupiter.api.Test;

/**
 * Every event type is produced, then the outbox is checked: no raw project id, no project identity (path or remote),
 * no file path or symbol, no unsalted digest of the identity, nothing the redaction rules would change, and the
 * project key is HMAC-SHA256 of the identity under QUANCRYPT_ANON_SALT (D-20, D-129).
 */
class OutboxAnonymityTest extends IntegrationTest {

    private static final String IDENTITY = "git@example.com:bank/payments.git";

    @Test
    void outboxHoldsNoRawIdentifiersAndNoSecretPatterns() throws Exception {
        UUID projectId = registerProject.execute(new RegisterProjectCommand(IDENTITY, "Payments", Optional.empty(), "UI")).id();
        grantConsent.execute(new GrantConsentCommand(projectId, "WAREHOUSE_ANALYTICS", 1, Optional.empty(),
                Optional.empty(), "UI"));
        recordRuntimeProfile.execute(new RecordRuntimeProfileCommand(projectId, "21", Optional.of("4.1.1"), Optional.empty(), "UI"));
        UUID scanId = runningScan(projectId);
        List<UUID> ids = record(scanId, tlsFinding("src/main/java/com/bank/TlsConfig.java", "TlsConfig#sslContext")).createdIds();
        recordTopology.execute(new RecordTopologyCommand(scanId, List.of(new NodeInput("payment-gateway", "GATEWAY"),
                new NodeInput("ledger", "SERVICE")), List.of(new LinkInput("payment-gateway", "ledger", "HTTP", true, true,
                List.of(new CallSiteInput("src/main/java/com/bank/LedgerClient.java", 5, 6, "CODE")), ids)), "UI"));
        complete(scanId);
        plan(scanId, ids);
        UUID itemId = jdbc.sql("SELECT id FROM plan_item").query(UUID.class).single();
        transitionPlanItem.execute(new TransitionPlanItemCommand(itemId, "APPROVED", 1, Optional.empty(), "UI"));
        String projectKey = jdbc.sql("SELECT project_key FROM project").query(String.class).single();
        deleteProject.execute(new DeleteProjectCommand(projectId, "UI"));
        // DeleteProject dropped the pending events; produce them again on a second project and keep it.
        UUID kept = registerProject.execute(new RegisterProjectCommand(IDENTITY + "-2", "Payments 2", Optional.empty(), "UI")).id();
        grantConsent.execute(new GrantConsentCommand(kept, "WAREHOUSE_ANALYTICS", 1, Optional.empty(),
                Optional.empty(), "UI"));
        recordRuntimeProfile.execute(new RecordRuntimeProfileCommand(kept, "21", Optional.empty(), Optional.empty(), "UI"));
        UUID scan2 = runningScan(kept);
        List<UUID> ids2 = record(scan2, tlsFinding("src/main/java/com/bank/TlsConfig.java", "TlsConfig#sslContext")).createdIds();
        recordTopology.execute(new RecordTopologyCommand(scan2, List.of(new NodeInput("payment-gateway", "GATEWAY"),
                new NodeInput("ledger", "SERVICE")), List.of(new LinkInput("payment-gateway", "ledger", "HTTP", true, true, List.of(), ids2)), "UI"));
        complete(scan2);
        plan(scan2, ids2);

        List<String> payloads = jdbc.sql("SELECT payload::text FROM outbox_event").query(String.class).list();
        List<String> types = jdbc.sql("SELECT DISTINCT event_type FROM outbox_event ORDER BY 1").query(String.class).list();
        assertThat(types).containsExactly("consent_revoked", "finding_detected", "plan_created", "project_runtime_changed", "scan_completed",
                "topology_recorded");
        assertThat(jdbc.sql("SELECT count(*) FROM outbox_event WHERE event_type = 'plan_item_transitioned'").query(Integer.class).single())
                .isZero();

        String sha256OfIdentity = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(IDENTITY.getBytes(StandardCharsets.UTF_8)));
        Redactor redactor = new Redactor(RedactionRules.fromClasspath());
        for (String payload : payloads) {
            assertThat(payload).doesNotContain(projectId.toString(), kept.toString(), scanId.toString(), scan2.toString(), itemId.toString())
                    .doesNotContain(IDENTITY, "bank/payments", "TlsConfig", "src/main", "LedgerClient", "payment-gateway", "ledger")
                    .doesNotContain(sha256OfIdentity, projectKey);
            assertThat(redactor.redact(payload)).as("redaction must not change an outbox payload").isEqualTo(payload);
        }
        assertThat(projectKey).isEqualTo(hmac(IDENTITY));
        assertThat(jdbc.sql("SELECT DISTINCT project_key FROM outbox_event ORDER BY 1").query(String.class).list())
                .containsExactlyInAnyOrder(projectKey, hmac(IDENTITY + "-2"));
    }

    @Test
    void transitionEventsCarryOnlyCodes() {
        UUID itemId = plannedItem("/work/demo");
        transitionPlanItem.execute(new TransitionPlanItemCommand(itemId, "APPROVED", 1, Optional.empty(), "UI"));

        String payload = jdbc.sql("SELECT payload::text FROM outbox_event WHERE event_type = 'plan_item_transitioned'").query(String.class).single();

        assertThat(payload).doesNotContain(itemId.toString()).contains("\"from_state\": \"PLANNED\"", "\"to_state\": \"APPROVED\"");
    }

    private static String hmac(String identity) throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(SALT.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
        return HexFormat.of().formatHex(mac.doFinal(identity.getBytes(StandardCharsets.UTF_8)));
    }
}

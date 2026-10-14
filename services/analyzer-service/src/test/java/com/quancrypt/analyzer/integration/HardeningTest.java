package com.quancrypt.analyzer.integration;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.analyzer.api.BodyLimitFilter;
import com.quancrypt.analyzer.integration.support.ApiClient.Reply;
import com.quancrypt.analyzer.integration.support.IntegrationTest;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.health.contributor.Status;
import org.springframework.boot.health.contributor.HealthIndicator;

/**
 * What the P3.3 security review asked for (D-205): bodies above the limit are refused, the trace id cannot carry header
 * injections, requests the firewall refuses and bad percent encoding get the problem of the contract, and there is no
 * generated user.
 */
class HardeningTest extends IntegrationTest {

    @Autowired
    private HealthIndicator analyzerHealthIndicator;

    @Test
    void aBodyAboveTheLimitIsRefusedWithTheValidationProblem() {
        String padding = " ".repeat(BodyLimitFilter.MAX_BODY_BYTES + 1);
        Reply reply = api().post("/api/v1/analyses").internal(INTERNAL_TOKEN)
                .body(("{\"root\":\"" + REFERENCE + "\"}" + padding).getBytes(java.nio.charset.StandardCharsets.UTF_8), "application/json").send();

        assertThat(reply.status()).isEqualTo(400);
        assertThat(reply.json().get("type").asString()).isEqualTo("https://quancrypt.local/problems/validation-failed");
        assertThat(reply.header("x-trace-id")).isNotBlank();
    }

    @Test
    void aBodyWithinTheLimitStillWorks() {
        Reply reply = api().post("/api/v1/analyses").internal(INTERNAL_TOKEN).json(Map.of("root", "/etc")).send();

        assertThat(reply.status()).isEqualTo(400);
        assertThat(reply.json().get("type").asString()).isEqualTo("https://quancrypt.local/problems/path-not-allowed");
    }

    @Test
    void aMaliciousTraceIdIsReplacedAndNeverEchoed() {
        for (String evil : new String[] {"a b", "x;y", "<script>", "a".repeat(200), "ok-id_1.2"}) {
            Reply reply = api().get("/health/liveness").header("X-Trace-Id", evil).send();

            String echoed = reply.header("x-trace-id");
            assertThat(echoed).matches("[A-Za-z0-9._-]{1,128}");
            if (!evil.equals("ok-id_1.2")) {
                assertThat(echoed).isNotEqualTo(evil);
            } else {
                assertThat(echoed).isEqualTo(evil);
            }
        }
    }

    @Test
    void aRequestTheFirewallRefusesGetsTheProblemOfTheContract() {
        Reply reply = api().get("/api/v1/plugins;x=1").internal(INTERNAL_TOKEN).send();

        assertThat(reply.status()).isEqualTo(400);
        assertThat(reply.header("content-type")).startsWith("application/problem+json");
        assertThat(reply.json().get("type").asString()).isEqualTo("https://quancrypt.local/problems/validation-failed");
    }

    @Test
    void badPercentEncodingIsABadRequestAndNotAnInternalError() {
        Reply reply = api().get("/api/v1/snippets?root=%ff%fe&path=a&line=1").internal(INTERNAL_TOKEN).send();

        assertThat(reply.status()).isEqualTo(400);
        assertThat(reply.text()).doesNotContain("%ff");
    }

    @Test
    void readinessIsUpWhileAProjectDirectoryIsMounted() {
        assertThat(analyzerHealthIndicator.health().getStatus()).isEqualTo(Status.UP);
    }
}

package com.quancrypt.analyzer.integration;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.quancrypt.analyzer.infrastructure.security.InternalTokenFilter;
import com.quancrypt.analyzer.integration.support.ApiClient.Call;
import com.quancrypt.analyzer.integration.support.ApiClient.Reply;
import com.quancrypt.analyzer.integration.support.IntegrationTest;
import com.quancrypt.analyzer.integration.support.OpenApiContract;
import com.quancrypt.analyzer.integration.support.OpenApiContract.Operation;
import java.util.Map;
import org.junit.jupiter.api.Test;

/**
 * Token security of every operation (guardrails-security section 6): without the service token, or with a wrong one or
 * the token in the wrong header, the answer is 401 problem+json with an X-Trace-Id; only the two health paths are open;
 * a weak token stops the service at start-up.
 */
class SecurityTest extends IntegrationTest {

    private static final OpenApiContract CONTRACT = new OpenApiContract();

    private Call request(Operation op) {
        Call call = api().call(op.method(), op.path());
        return "POST".equals(op.method()) ? call.json(Map.of("root", REFERENCE.toString())) : call;
    }

    private static void assertUnauthorized(Reply reply) {
        assertThat(reply.status()).isEqualTo(401);
        assertThat(reply.header("content-type")).startsWith("application/problem+json");
        assertThat(reply.json().get("type").asString()).isEqualTo("https://quancrypt.local/problems/unauthorized");
        assertThat(reply.header("x-trace-id")).isNotBlank();
        assertThat(reply.text()).doesNotContain(INTERNAL_TOKEN);
    }

    @Test
    void everyOperationNeedsTheServiceToken() {
        for (Operation op : CONTRACT.operations()) {
            assertUnauthorized(request(op).send());
            assertUnauthorized(request(op).internal("wrong-" + INTERNAL_TOKEN).send());
            assertUnauthorized(request(op).internal("").send());
            assertUnauthorized(request(op).bearer(INTERNAL_TOKEN).send());
            assertUnauthorized(request(op).header("X-Internal-Token", INTERNAL_TOKEN.substring(1)).send());
            assertThat(request(op).internal(INTERNAL_TOKEN).send().status()).isNotEqualTo(401);
        }
    }

    @Test
    void anUnknownPathIsNotAnOpenDoor() {
        assertUnauthorized(api().get("/api/v1/nothing").send());
        assertUnauthorized(api().get("/actuator/env").send());
        assertThat(api().get("/api/v1/nothing").internal(INTERNAL_TOKEN).send().status()).isEqualTo(404);
    }

    @Test
    void onlyTheHealthPathsAreOpen() {
        Reply liveness = api().get("/health/liveness").send();
        Reply readiness = api().get("/health/readiness").send();

        assertThat(liveness.status()).isEqualTo(200);
        assertThat(liveness.json().get("status").asString()).isEqualTo("UP");
        assertThat(readiness.status()).isEqualTo(200);
        assertThat(api().get("/health").send().status()).isEqualTo(401);
        assertThat(api().get("/health/liveness/extra").send().status()).isEqualTo(401);
    }

    @Test
    void aWeakOrPlaceholderTokenStopsTheService() {
        assertThatThrownBy(() -> new InternalTokenFilter(null)).isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(() -> new InternalTokenFilter("")).isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(() -> new InternalTokenFilter("short")).isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(() -> new InternalTokenFilter("CHANGE_ME" + "x".repeat(40))).isInstanceOf(IllegalStateException.class);
        new InternalTokenFilter("x".repeat(32));
    }
}

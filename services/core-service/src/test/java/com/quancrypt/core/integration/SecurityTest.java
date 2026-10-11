package com.quancrypt.core.integration;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.core.integration.support.ApiClient;
import com.quancrypt.core.integration.support.ApiClient.Reply;
import com.quancrypt.core.integration.support.IntegrationTest;
import com.quancrypt.core.integration.support.OpenApiContract;
import com.quancrypt.core.integration.support.OpenApiContract.Operation;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.Test;

/**
 * Token security of every operation (guardrails-security section 6): without a token 401, a wrong or wrongly used token
 * 401, the UI token on the internal relay 403, correct tokens pass; CORS answers only the UI origins; only the two health
 * paths are open.
 */
class SecurityTest extends IntegrationTest {

    private static final OpenApiContract CONTRACT = new OpenApiContract();
    private static final String UI_ORIGIN = "http://127.0.0.1:8080";

    private static String concretePath(Operation op) {
        return op.path().replaceAll("\\{consentType}", "WAREHOUSE_ANALYTICS").replaceAll("\\{[A-Za-z]+}", UUID.randomUUID().toString());
    }

    private ApiClient.Call request(Operation op) {
        ApiClient.Call call = api().call(op.method(), concretePath(op));
        return "POST".equals(op.method()) || "PUT".equals(op.method()) ? call.json(Map.of()) : call;
    }

    private static void assertProblem(Reply reply, int status, String code) {
        assertThat(reply.status()).isEqualTo(status);
        assertThat(reply.header("content-type")).startsWith("application/problem+json");
        assertThat(reply.json().get("type").asString()).isEqualTo("https://quancrypt.local/problems/" + code);
        assertThat(reply.header("x-trace-id")).isNotBlank();
    }

    @Test
    void everyOperationNeedsACredential() {
        for (Operation op : CONTRACT.operations()) {
            assertProblem(request(op).send(), 401, "unauthorized");
            assertProblem(request(op).bearer("wrong-" + SESSION_TOKEN).send(), 401, "unauthorized");
            assertProblem(request(op).internal("wrong-" + INTERNAL_TOKEN).send(), 401, "unauthorized");
            assertProblem(request(op).header("Authorization", SESSION_TOKEN).send(), 401, "unauthorized");
            assertProblem(request(op).bearer(INTERNAL_TOKEN).send(), 401, "unauthorized");
            assertProblem(request(op).internal(SESSION_TOKEN).send(), 401, "unauthorized");
            // An Authorization header that is present but wrong is never rescued by a correct internal token.
            assertProblem(request(op).bearer("wrong-" + SESSION_TOKEN).internal(INTERNAL_TOKEN).send(), 401, "unauthorized");
        }
    }

    @Test
    void eachOperationAcceptsExactlyTheSchemesOfTheContract() {
        for (Operation op : CONTRACT.operations()) {
            boolean bearer = op.securitySchemes().contains("bearerAuth");
            boolean internal = op.securitySchemes().contains("internalToken");
            Reply withUi = request(op).bearer(SESSION_TOKEN).send();
            Reply withInternal = request(op).internal(INTERNAL_TOKEN).send();
            if (bearer) {
                assertThat(withUi.status()).as(op.id() + " with the UI token").isNotIn(401, 403);
            } else {
                assertProblem(withUi, 403, "forbidden");
            }
            if (internal) {
                assertThat(withInternal.status()).as(op.id() + " with the service token").isNotIn(401, 403);
            } else {
                assertProblem(withInternal, 401, "unauthorized");
            }
        }
    }

    @Test
    void theCallerKindFollowsTheCredential() {
        UUID projectId = UUID.fromString(api().post("/api/v1/projects").bearer(SESSION_TOKEN)
                .json(Map.of("identity", "/work/audit", "displayName", "Audit")).send().json().get("id").asString());
        String projectKey = api().get("/api/v1/projects/" + projectId).bearer(SESSION_TOKEN).send().json().get("project").get("projectKey").asString();
        api().post("/api/v1/projects/" + projectId + "/scans").internal(INTERNAL_TOKEN).send();

        Reply audit = api().get("/api/v1/audit-entries?projectKey=" + projectKey).bearer(SESSION_TOKEN).send();

        assertThat(audit.status()).isEqualTo(200);
        assertThat(audit.json().get("items").get(0).get("action").asString()).isEqualTo("SCAN_STARTED");
        assertThat(audit.json().get("items").get(0).get("callerKind").asString()).isEqualTo("INTERNAL");
        assertThat(audit.json().get("items").get(1).get("callerKind").asString()).isEqualTo("UI");
    }

    @Test
    void corsAnswersOnlyTheUiOrigins() {
        for (String origin : new String[] {UI_ORIGIN, "http://localhost:8080"}) {
            Reply preflight = api().options("/api/v1/projects").header("Origin", origin).header("Access-Control-Request-Method", "POST")
                    .header("Access-Control-Request-Headers", "authorization,content-type,idempotency-key").send();
            assertThat(preflight.status()).isEqualTo(200);
            assertThat(preflight.header("access-control-allow-origin")).isEqualTo(origin);
            assertThat(preflight.header("access-control-allow-credentials")).isNull();
            Reply actual = api().get("/api/v1/projects").bearer(SESSION_TOKEN).header("Origin", origin).send();
            assertThat(actual.status()).isEqualTo(200);
            assertThat(actual.header("access-control-allow-origin")).isEqualTo(origin);
            assertThat(actual.header("access-control-expose-headers")).contains("X-Trace-Id");
        }
        for (String origin : new String[] {"http://evil.example", "http://127.0.0.1:8081", "https://127.0.0.1:8080", "null", "http://localhost:8080.evil.example"}) {
            Reply preflight = api().options("/api/v1/projects").header("Origin", origin).header("Access-Control-Request-Method", "GET").send();
            assertThat(preflight.status()).as("preflight from " + origin).isEqualTo(403);
            assertThat(preflight.header("access-control-allow-origin")).isNull();
            Reply actual = api().get("/api/v1/projects").bearer(SESSION_TOKEN).header("Origin", origin).send();
            assertThat(actual.status()).as("request from " + origin).isEqualTo(403);
            assertThat(actual.header("access-control-allow-origin")).isNull();
        }
    }

    @Test
    void onlyTheTwoHealthPathsAreOpen() {
        Reply liveness = api().get("/health/liveness").send();
        Reply readiness = api().get("/health/readiness").send();

        assertThat(liveness.status()).isEqualTo(200);
        assertThat(readiness.status()).isEqualTo(200);
        assertThat(liveness.text()).doesNotContain("jdbc").doesNotContain("password");
        assertThat(readiness.text()).doesNotContain("jdbc").doesNotContain("password");
        assertThat(api().get("/health").send().status()).isEqualTo(401);
        assertThat(api().get("/health/db").send().status()).isEqualTo(401);
        assertThat(api().get("/actuator/env").send().status()).isEqualTo(401);
        assertThat(api().get("/v3/api-docs").send().status()).isEqualTo(401);
    }

    @Test
    void noResponseEchoesACredential() {
        for (Reply reply : new Reply[] {
            api().get("/api/v1/projects").bearer("wrong-" + SESSION_TOKEN).send(),
            api().get("/api/v1/projects").bearer(SESSION_TOKEN).send(),
            api().post("/api/v1/internal/outbox/relay").bearer(SESSION_TOKEN).send()}) {
            assertThat(reply.text()).doesNotContain(SESSION_TOKEN).doesNotContain(INTERNAL_TOKEN);
            reply.headers().values().forEach(v -> assertThat(v).doesNotContain(SESSION_TOKEN).doesNotContain(INTERNAL_TOKEN));
        }
    }
}

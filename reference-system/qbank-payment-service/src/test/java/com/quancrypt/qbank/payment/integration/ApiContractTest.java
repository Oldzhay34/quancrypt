package com.quancrypt.qbank.payment.integration;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.qbank.payment.support.ContractSchemas;
import com.quancrypt.qbank.payment.support.ServiceClient;
import com.quancrypt.qbank.payment.support.TokenFactory;
import java.nio.file.Path;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeSet;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.web.method.HandlerMethod;
import org.springframework.web.servlet.mvc.method.RequestMappingInfo;
import org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/** The running service conforms to reference-system/contracts/qbank-payment.openapi.yaml. */
class ApiContractTest extends ServiceIntegrationTest {

    private static final Path CONTRACT = Path.of(System.getProperty("qbank.contracts.dir"))
            .resolve("qbank-payment.openapi.yaml");
    private static final String BODY =
            "{\"accountId\":\"acc-001\",\"amount\":\"12.50\",\"currency\":\"TRY\",\"cardNumber\":\"4111111111111111\"}";

    private final ContractSchemas contract = ContractSchemas.load(CONTRACT);
    private final TokenFactory tokens = new TokenFactory();
    private final JsonMapper json = JsonMapper.builder().build();

    @Autowired
    private ApplicationContext context;

    private void assertConforms(ServiceClient.Response response, int status, String schema) {
        assertThat(response.status()).isEqualTo(status);
        assertThat(response.traceId()).as("X-Trace-Id response header").isNotBlank();
        assertThat(contract.validate(schema, response.body())).as("%s body %s", schema, response.body()).isEmpty();
    }

    private void assertProblem(ServiceClient.Response response, int status, String code) {
        assertConforms(response, status, "Problem");
        assertThat(response.contentType()).startsWith("application/problem+json");
        JsonNode body = json.readTree(response.body());
        assertThat(body.get("type").asString()).isEqualTo("https://quancrypt.local/problems/" + code);
        assertThat(body.get("status").asInt()).isEqualTo(status);
    }

    private ServiceClient.Response create(String token, Map<String, String> headers, String body) throws Exception {
        return gatewayClient().postJson("/api/v1/payments", token, headers, body);
    }

    @Test
    void theServiceExposesExactlyTheOperationsOfTheContract() {
        RequestMappingHandlerMapping mapping = context.getBean(RequestMappingHandlerMapping.class);
        Set<String> implemented = new TreeSet<>();
        for (var entry : mapping.getHandlerMethods().entrySet()) {
            HandlerMethod handler = entry.getValue();
            if (!handler.getBeanType().getPackageName().equals("com.quancrypt.qbank.payment.api.controller")) {
                continue;
            }
            RequestMappingInfo info = entry.getKey();
            var patterns = Objects.requireNonNull(info.getPathPatternsCondition(), "path patterns").getPatternValues();
            for (var method : info.getMethodsCondition().getMethods()) {
                for (String pattern : patterns) {
                    implemented.add(method.name() + " " + pattern);
                }
            }
        }

        assertThat(implemented).isEqualTo(contract.operations());
        assertThat(contract.operations()).containsExactly(
                "GET /api/v1/payments/{paymentId}", "POST /api/v1/payments", "POST /api/v1/payments/{paymentId}/receipt");
    }

    @Test
    void createPaymentResponsesConformIncludingEveryDocumentedError() throws Exception {
        String token = tokens.valid("demo1");

        assertConforms(create(token, Map.of(), BODY), 201, "Payment");
        assertProblem(create(token, Map.of(), "{}"), 400, "validation-failed");
        assertProblem(create(null, Map.of(), BODY), 401, "unauthorized");
        assertProblem(create(token, Map.of(), BODY.replace("acc-001", "acc-002")), 403, "forbidden");
        assertProblem(create(token, Map.of(), BODY.replace("acc-001", "acc-999")), 404, "not-found");
        String key = "contract-key-" + System.nanoTime();
        assertConforms(create(token, Map.of("Idempotency-Key", key), BODY), 201, "Payment");
        assertProblem(create(token, Map.of("Idempotency-Key", key), BODY.replace("12.50", "13.50")), 409, "idempotency-conflict");
        assertProblem(create(token, Map.of(), BODY.replace("acc-001", "acc-500")), 503, "upstream-unavailable");
        assertThat(contract.responseCodes("post", "/api/v1/payments"))
                .containsExactlyInAnyOrder("201", "400", "401", "403", "404", "409", "503");
    }

    @Test
    void getPaymentResponsesConform() throws Exception {
        String token = tokens.valid("demo1");
        String id = json.readTree(create(token, Map.of(), BODY).body()).get("paymentId").asString();

        assertConforms(gatewayClient().get("/api/v1/payments/" + id, token), 200, "Payment");
        assertProblem(gatewayClient().get("/api/v1/payments/" + id, null), 401, "unauthorized");
        assertProblem(gatewayClient().get("/api/v1/payments/" + new UUID(0, 42), token), 404, "not-found");
        assertThat(contract.responseCodes("get", "/api/v1/payments/{paymentId}"))
                .containsExactlyInAnyOrder("200", "401", "404");
    }

    @Test
    void receiptResponsesConformIncludingEveryDocumentedError() throws Exception {
        String token = tokens.valid("demo1");
        String first = json.readTree(create(token, Map.of(), BODY).body()).get("paymentId").asString();
        String second = json.readTree(create(token, Map.of(), BODY).body()).get("paymentId").asString();
        String key = "receipt-contract-" + System.nanoTime();

        assertConforms(gatewayClient().postEmpty("/api/v1/payments/" + first + "/receipt", token, Map.of()), 200, "SignedReceipt");
        assertProblem(gatewayClient().postEmpty("/api/v1/payments/" + first + "/receipt", null, Map.of()), 401, "unauthorized");
        assertProblem(gatewayClient().postEmpty("/api/v1/payments/" + new UUID(0, 42) + "/receipt", token, Map.of()),
                404, "not-found");
        assertConforms(gatewayClient().postEmpty(
                "/api/v1/payments/" + first + "/receipt", token, Map.of("Idempotency-Key", key)), 200, "SignedReceipt");
        assertProblem(gatewayClient().postEmpty(
                "/api/v1/payments/" + second + "/receipt", token, Map.of("Idempotency-Key", key)), 409, "idempotency-conflict");
        assertProblem(gatewayClient().postEmpty(
                "/api/v1/payments/" + first + "/receipt", token, Map.of("Idempotency-Key", "k".repeat(129))),
                400, "validation-failed");
        assertThat(contract.responseCodes("post", "/api/v1/payments/{paymentId}/receipt"))
                .containsExactlyInAnyOrder("200", "400", "401", "404", "409");
    }

    @Test
    void theTraceIdIsEchoedWhenSafeAndReplacedWhenNot() throws Exception {
        String token = tokens.valid("demo1");

        assertThat(gatewayClient().send("GET", "/api/v1/payments/" + new UUID(0, 1), token, Map.of("X-Trace-Id", "my-trace-1"), null)
                .traceId()).isEqualTo("my-trace-1");
        assertThat(gatewayClient().send("GET", "/api/v1/payments/" + new UUID(0, 1), token, Map.of("X-Trace-Id", "bad value!"), null)
                .traceId()).isNotEqualTo("bad value!").hasSize(36);
    }

    @Test
    void errorsNeverReflectRequestValues() throws Exception {
        ServiceClient.Response response = create(tokens.valid("demo1"), Map.of(), BODY.replace("4111111111111111", "<script>alert-1"));

        assertThat(response.status()).isEqualTo(400);
        assertThat(response.body()).doesNotContain("script").doesNotContain("alert-1").doesNotContain("4111");
    }

    @Test
    void unmappedPathsAndMethodsAreProblemDetailsToo() throws Exception {
        String token = tokens.valid("demo1");

        assertProblem(gatewayClient().get("/no/such/path", token), 404, "not-found");
        assertProblem(gatewayClient().get("/api/v1/payments", token), 405, "method-not-allowed");
    }
}

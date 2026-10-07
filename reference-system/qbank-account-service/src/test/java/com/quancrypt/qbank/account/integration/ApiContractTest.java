package com.quancrypt.qbank.account.integration;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.qbank.account.support.ContractSchemas;
import com.quancrypt.qbank.account.support.ServiceClient;
import com.quancrypt.qbank.account.support.TokenFactory;
import java.nio.file.Path;
import java.util.Objects;
import java.util.Set;
import java.util.TreeSet;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.web.method.HandlerMethod;
import org.springframework.web.servlet.mvc.method.RequestMappingInfo;
import org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping;
import tools.jackson.databind.json.JsonMapper;

/** The running service conforms to reference-system/contracts/qbank-account.openapi.yaml. */
class ApiContractTest extends ServiceIntegrationTest {

    private static final Path CONTRACT = Path.of(System.getProperty("qbank.contracts.dir"))
            .resolve("qbank-account.openapi.yaml");
    private static final String PROBLEM_JSON = "application/problem+json";

    private final ContractSchemas contract = ContractSchemas.load(CONTRACT);
    private final TokenFactory tokens = new TokenFactory(TokenFactory.realKeys());

    @Autowired
    private ApplicationContext context;

    private void assertConforms(ServiceClient.Response response, int status, String schema) {
        assertThat(response.status()).isEqualTo(status);
        assertThat(response.traceId()).as("X-Trace-Id response header").isNotBlank();
        assertThat(contract.validate(schema, response.body()))
                .as("%s body %s", schema, response.body()).isEmpty();
    }

    private void assertProblem(ServiceClient.Response response, int status, String code) {
        assertConforms(response, status, "Problem");
        assertThat(response.contentType()).startsWith(PROBLEM_JSON);
        var body = JsonMapper.builder().build().readTree(response.body());
        assertThat(body.get("type").asString()).isEqualTo("https://quancrypt.local/problems/" + code);
        assertThat(body.get("status").asInt()).isEqualTo(status);
    }

    @Test
    void theServiceExposesExactlyTheOperationsOfTheContract() {
        RequestMappingHandlerMapping mapping = context.getBean(RequestMappingHandlerMapping.class);
        Set<String> implemented = new TreeSet<>();
        for (var entry : mapping.getHandlerMethods().entrySet()) {
            HandlerMethod handler = entry.getValue();
            if (!handler.getBeanType().getPackageName().equals("com.quancrypt.qbank.account.api.controller")) {
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
    }

    @Test
    void loginResponsesConformIncludingTheDocumentedErrors() throws Exception {
        ServiceClient client = gatewayClient();

        assertConforms(client.postJson("/api/v1/auth/login", LOGIN_BODY_DEMO1), 200, "LoginResponse");
        assertProblem(client.postJson("/api/v1/auth/login",
                "{\"username\":\"demo1\",\"password\":\"nope\"}"), 401, "unauthorized");
        assertProblem(client.postJson("/api/v1/auth/login", "{\"username\":\"demo1\"}"), 400, "validation-failed");
        assertProblem(client.postJson("/api/v1/auth/login", "{\"username\":\"\",\"password\":\"x\"}"),
                400, "validation-failed");
        assertProblem(client.postJson("/api/v1/auth/login", "not json"), 400, "validation-failed");
        assertThat(contract.responseCodes("post", "/api/v1/auth/login")).containsExactlyInAnyOrder("200", "400", "401");
    }

    @Test
    void loginRejectsUnknownPropertiesAsTheContractDemands() throws Exception {
        // contract: LoginRequest has additionalProperties: false
        assertProblem(gatewayClient().postJson("/api/v1/auth/login",
                "{\"username\":\"demo1\",\"password\":\"demo1-demo-pass\",\"role\":\"admin\"}"), 400, "validation-failed");
    }

    @Test
    void jwksResponseConforms() throws Exception {
        assertConforms(gatewayClient().get("/.well-known/jwks.json", null), 200, "Jwks");
        assertThat(contract.responseCodes("get", "/.well-known/jwks.json")).containsExactly("200");
    }

    @Test
    void accountResponsesConformIncludingTheDocumentedErrors() throws Exception {
        ServiceClient client = gatewayClient();
        String token = tokens.valid("demo2");

        assertConforms(client.get("/api/v1/accounts/acc-002", token), 200, "Account");
        assertProblem(client.get("/api/v1/accounts/acc-002", null), 401, "unauthorized");
        assertProblem(client.get("/api/v1/accounts/acc-001", token), 403, "forbidden");
        assertProblem(client.get("/api/v1/accounts/acc-999", token), 404, "not-found");
        assertProblem(client.get("/api/v1/accounts/" + "a".repeat(65), token), 400, "validation-failed");
        assertProblem(client.get("/api/v1/accounts/acc$001", token), 400, "validation-failed");
        assertThat(contract.responseCodes("get", "/api/v1/accounts/{accountId}"))
                .containsExactlyInAnyOrder("200", "400", "401", "403", "404");
    }

    @Test
    void theTraceIdIsEchoedWhenSafeAndReplacedWhenNot() throws Exception {
        ServiceClient client = gatewayClient();

        assertThat(client.get("/.well-known/jwks.json", null, "my-trace-1").traceId()).isEqualTo("my-trace-1");
        assertThat(client.get("/.well-known/jwks.json", null, "bad value!").traceId())
                .isNotEqualTo("bad value!").hasSize(36);
        assertThat(client.get("/.well-known/jwks.json", null).traceId()).hasSize(36);
    }

    @Test
    void errorsNeverReflectRequestValues() throws Exception {
        ServiceClient.Response response = gatewayClient()
                .get("/api/v1/accounts/%3Cscript%3Ealert-1%3C%2Fscript%3E", tokens.valid("demo1"));

        assertThat(response.body()).doesNotContain("script").doesNotContain("alert-1");
    }

    @Test
    void unmappedPathsAndMethodsAreProblemDetailsToo() throws Exception {
        ServiceClient client = gatewayClient();

        assertProblem(client.get("/no/such/path", null), 404, "not-found");
        assertProblem(client.get("/api/v1/auth/login", null), 405, "method-not-allowed");
    }

    @Test
    void theContractListsTheThreeDocumentedOperations() {
        assertThat(contract.operations()).containsExactly(
                "GET /.well-known/jwks.json", "GET /api/v1/accounts/{accountId}", "POST /api/v1/auth/login");
    }
}

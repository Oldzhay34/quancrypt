package com.quancrypt.analyzer.integration;

import static org.assertj.core.api.Assertions.assertThat;

import com.networknt.schema.Error;
import com.quancrypt.analyzer.integration.support.ApiClient.Reply;
import com.quancrypt.analyzer.integration.support.IntegrationTest;
import com.quancrypt.analyzer.integration.support.OpenApiContract;
import com.quancrypt.analyzer.integration.support.OpenApiContract.Operation;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.web.servlet.mvc.method.RequestMappingInfo;
import org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping;
import tools.jackson.databind.JsonNode;

/**
 * The REST surface against contracts/openapi/analyzer-service.yaml (D-17): the application maps exactly the four
 * operations of the contract, every answer has a status the contract declares for the operation, a body that validates
 * against the declared schema (the findings and the topology against contracts/schemas) and an X-Trace-Id header, and
 * failures are RFC 9457 problem details with the problem types of the contract.
 */
class ContractConformanceTest extends IntegrationTest {

    private static final OpenApiContract CONTRACT = new OpenApiContract();
    private static final String PROBLEM_BASE = "https://quancrypt.local/problems/";

    @Autowired
    @Qualifier("requestMappingHandlerMapping")
    private RequestMappingHandlerMapping handlerMapping;

    private Reply send(String operationId, int status, String pathAndQuery, Object body) {
        Operation op = CONTRACT.operation(operationId);
        var call = api().call(op.method(), pathAndQuery).internal(INTERNAL_TOKEN);
        if (body != null) {
            call = call.json(body);
        }
        Reply reply = call.send();
        assertThat(reply.status()).as(operationId + " answered " + reply.text()).isEqualTo(status);
        conforms(op, reply);
        return reply;
    }

    private void conforms(Operation op, Reply reply) {
        assertThat(CONTRACT.declares(op, reply.status())).as(op.id() + " does not declare " + reply.status()).isTrue();
        assertThat(reply.header("x-trace-id")).as("X-Trace-Id of " + op.id()).isNotBlank();
        String mediaType = reply.header("content-type").split(";")[0].strip();
        assertThat(CONTRACT.declaresBody(op, reply.status(), mediaType)).as(op.id() + " declares no " + mediaType + " for " + reply.status())
                .isTrue();
        List<Error> errors = CONTRACT.validate(op, reply.status(), mediaType, reply.text());
        assertThat(errors).as(op.id() + " " + reply.status() + " body " + reply.text()).isEmpty();
    }

    private static String query(String... kv) {
        StringBuilder sb = new StringBuilder("/api/v1/snippets?");
        for (int i = 0; i < kv.length; i += 2) {
            sb.append(i == 0 ? "" : "&").append(kv[i]).append('=').append(URLEncoder.encode(kv[i + 1], StandardCharsets.UTF_8));
        }
        return sb.toString();
    }

    private static void assertProblem(Reply reply, String code) {
        assertThat(reply.header("content-type")).startsWith("application/problem+json");
        assertThat(reply.json().get("type").asString()).isEqualTo(PROBLEM_BASE + code);
    }

    @Test
    void theApplicationMapsExactlyTheOperationsOfTheContract() {
        Set<String> mapped = new TreeSet<>();
        for (RequestMappingInfo info : handlerMapping.getHandlerMethods().keySet()) {
            var paths = info.getPathPatternsCondition();
            if (paths == null) {
                continue;
            }
            for (var pattern : paths.getPatterns()) {
                if (pattern.getPatternString().startsWith("/api/v1")) {
                    info.getMethodsCondition().getMethods().forEach(m -> mapped.add(m.name() + " " + pattern.getPatternString()));
                }
            }
        }
        assertThat(mapped).isEqualTo(CONTRACT.operationKeys());
    }

    @Test
    void everyOperationAnswersAsTheContractSays() {
        Reply plugins = send("ListPlugins", 200, "/api/v1/plugins", null);
        assertThat(plugins.json().get("plugins").get(0).get("id").asString()).isEqualTo("java-spring");

        // The QBank services are independent builds side by side, so one service is the project to analyze (D-203).
        String project = REFERENCE.resolve("qbank-payment-service").toString();
        Reply analysis = send("AnalyzeCrypto", 200, "/api/v1/analyses", Map.of("root", project, "include_tests", true));
        JsonNode result = analysis.json();
        assertThat(result.get("project_type").asString()).isIn("MAVEN", "GRADLE");
        assertThat(result.get("findings").size()).isPositive();
        assertThat(result.get("stats").get("findings_total").asInt()).isEqualTo(result.get("findings").size());
        JsonNode cbom = result.get("cbom");
        assertThat(cbom.get("bomFormat").asString()).isEqualTo("CycloneDX");
        assertThat(cbom.get("specVersion").asString()).isEqualTo("1.6");
        assertThat(cbom.get("components").size()).isPositive();

        send("BuildTopology", 200, "/api/v1/topologies", Map.of("root", project));

        JsonNode codeFinding = null;
        for (JsonNode finding : result.get("findings")) {
            if ("CODE".equals(finding.get("location_kind").asString()) && !finding.get("line_start").isNull()) {
                codeFinding = finding;
                break;
            }
        }
        assertThat(codeFinding).isNotNull();
        Reply snippet = send("GetSnippet", 200, query("root", project, "path", codeFinding.get("file").asString(), "line",
                codeFinding.get("line_start").asString(), "context", "2"), null);
        assertThat(snippet.json().get("lines").size()).isBetween(1, 5);
    }

    @Test
    void failuresAreProblemDetailsWithTheTypesOfTheContract() throws Exception {
        assertProblem(send("AnalyzeCrypto", 400, "/api/v1/analyses", Map.of("root", "/etc")), "path-not-allowed");
        assertProblem(send("AnalyzeCrypto", 400, "/api/v1/analyses", Map.of("include_tests", true)), "validation-failed");
        assertProblem(send("AnalyzeCrypto", 400, "/api/v1/analyses", Map.of("root", REFERENCE.toString(), "surprise", 1)), "validation-failed");
        assertProblem(send("BuildTopology", 400, "/api/v1/topologies", Map.of()), "validation-failed");
        assertProblem(send("GetSnippet", 400, "/api/v1/snippets?root=" + URLEncoder.encode(REFERENCE.toString(), StandardCharsets.UTF_8), null),
                "validation-failed");
        assertProblem(send("GetSnippet", 404, query("root", REFERENCE.toString(), "path", "no/such/file.txt", "line", "1"), null), "not-found");
        assertProblem(send("GetSnippet", 400, query("root", REFERENCE.toString(), "path", "../outside.txt", "line", "1"), null),
                "path-not-allowed");
        // A root without a build file of its own cannot be typed (D-178h): the QBank root holds independent services.
        assertProblem(send("AnalyzeCrypto", 422, "/api/v1/analyses", Map.of("root", REFERENCE.toString())), "unsupported-project");

        Path empty = Files.createDirectory(SCRATCH.resolve("empty-project"));
        assertProblem(send("AnalyzeCrypto", 422, "/api/v1/analyses", Map.of("root", empty.toString())), "unsupported-project");
        assertProblem(send("BuildTopology", 422, "/api/v1/topologies", Map.of("root", empty.toString())), "unsupported-project");
    }
}

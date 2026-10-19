package com.quancrypt.core.integration;

import static org.assertj.core.api.Assertions.assertThat;

import com.networknt.schema.Error;
import com.networknt.schema.InputFormat;
import com.networknt.schema.Schema;
import com.quancrypt.core.integration.support.ApiClient;
import com.quancrypt.core.integration.support.ApiClient.Reply;
import com.quancrypt.core.integration.support.IntegrationTest;
import com.quancrypt.core.integration.support.OpenApiContract;
import com.quancrypt.core.integration.support.OpenApiContract.Operation;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;
import java.util.UUID;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.web.method.HandlerMethod;
import org.springframework.web.servlet.mvc.method.RequestMappingInfo;
import org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping;

/**
 * The REST surface against contracts/openapi/core-service.yaml (D-17): the application maps exactly the 28 operations of
 * the contract; one walk through a real project (real PostgreSQL, real HTTP) calls every operation, and each answer has
 * a status the contract declares for it, a body that validates against the declared schema, and an X-Trace-Id header.
 * Failures are RFC 9457 problem details with the problem types of the contract.
 */
class ContractConformanceTest extends IntegrationTest {

    private static final OpenApiContract CONTRACT = new OpenApiContract();

    @Autowired
    @Qualifier("requestMappingHandlerMapping")
    private RequestMappingHandlerMapping handlerMapping;

    private final Set<String> exercised = new TreeSet<>();

    // ------------------------------------------------------------------ helpers

    /** A call to the contract operation with its path parameters filled in; kv are name, value pairs ("query" appends a query string). */
    private ApiClient.Call call(String operationId, String... kv) {
        Operation op = CONTRACT.operation(operationId);
        String path = op.path();
        for (int i = 0; i < kv.length; i += 2) {
            path = "query".equals(kv[i]) ? path + "?" + kv[i + 1] : path.replace("{" + kv[i] + "}", kv[i + 1]);
        }
        exercised.add(op.id());
        return api().call(op.method(), path);
    }

    /** Sends the call, checks the answer against the contract and returns it. */
    private Reply expect(String operationId, int status, ApiClient.Call call) {
        Reply reply = call.send();
        assertThat(reply.status()).as(operationId + " answered " + reply.text()).isEqualTo(status);
        conforms(CONTRACT.operation(operationId), reply);
        return reply;
    }

    private void conforms(Operation op, Reply reply) {
        assertThat(CONTRACT.declares(op, reply.status())).as(op.id() + " does not declare " + reply.status()).isTrue();
        assertThat(reply.header("x-trace-id")).as("X-Trace-Id of " + op.id()).isNotBlank();
        if (reply.status() < 300 && java.util.Set.of("grantConsent", "revokeConsent", "transitionPlanItem").contains(op.id())) {
            assertThat(reply.header("etag")).as("ETag of " + op.id()).matches("\"[0-9]+\"");
        }
        String contentType = reply.header("content-type");
        if (reply.status() == 204 || contentType == null) {
            return;
        }
        String mediaType = contentType.split(";")[0].strip();
        Map<String, Object> declared = CONTRACT.responseSchema(op, reply.status(), mediaType);
        assertThat(declared).as(op.id() + " declares no " + mediaType + " body for " + reply.status()).isNotNull();
        // `type: string, format: binary` describes a raw file (the CBOM), not a JSON value: nothing to validate.
        boolean rawFile = "string".equals(declared.get("type")) && "binary".equals(declared.get("format"));
        if (mediaType.endsWith("json") && !rawFile) {
            Schema schema = CONTRACT.validatorFor(declared);
            List<Error> errors = schema.validate(reply.text(), InputFormat.JSON);
            assertThat(errors).as(op.id() + " " + reply.status() + " body " + reply.text()).isEmpty();
        }
    }

    private ApiClient.Call ui(ApiClient.Call call) {
        return call.bearer(SESSION_TOKEN);
    }

    private static Map<String, Object> finding() {
        Map<String, Object> f = new LinkedHashMap<>();
        f.put("path", "src/main/java/Tls.java");
        f.put("symbol", "Tls#handshake");
        f.put("algorithmFamily", "RSA");
        f.put("usageContext", "TLS_KEY_EXCHANGE");
        f.put("locationKind", "CODE");
        f.put("priority", "P1");
        f.put("keySizeBits", 2048);
        f.put("lineStart", 10);
        f.put("lineEnd", 12);
        f.put("confidence", 0.9);
        f.put("classifiedBy", "STATIC");
        return f;
    }

    // ------------------------------------------------------------------ tests

    @Test
    void theApplicationMapsExactlyTheOperationsOfTheContract() {
        Set<String> mapped = new TreeSet<>();
        for (Map.Entry<RequestMappingInfo, HandlerMethod> entry : handlerMapping.getHandlerMethods().entrySet()) {
            var patterns = entry.getKey().getPathPatternsCondition();
            if (patterns == null || !entry.getValue().getBeanType().getPackageName().startsWith("com.quancrypt.core.api")) {
                continue;
            }
            for (var method : entry.getKey().getMethodsCondition().getMethods()) {
                patterns.getPatternValues().forEach(p -> mapped.add(method.name() + " " + p));
            }
        }

        assertThat(CONTRACT.operations()).hasSize(28);
        assertThat(mapped).isEqualTo(CONTRACT.operationKeys());
    }

    @Test
    void everyOperationAnswersAsTheContractDeclares() {
        // privacy notice and project
        Reply notice = expect("GetPrivacyNotice", 200, ui(call("GetPrivacyNotice")));
        assertThat(notice.json().get("version").asInt()).isEqualTo(2);
        Map<String, Object> registration = Map.of("identity", "git@example.com:bank/payments.git", "displayName", "Payments");
        Reply registered = expect("RegisterProject", 201, ui(call("RegisterProject")).header("Idempotency-Key", "reg-1").json(registration));
        String projectId = registered.json().get("id").asString();
        String projectKey = registered.json().get("projectKey").asString();
        // A replay of the same key answers as the first call did (D-144); the same identity without a key is the 200 of the contract.
        expect("RegisterProject", 201, ui(call("RegisterProject")).header("Idempotency-Key", "reg-1").json(registration));
        expect("RegisterProject", 200, ui(call("RegisterProject")).json(registration));
        expect("ListProjects", 200, ui(call("ListProjects")));
        expect("GetProject", 200, ui(call("GetProject", "projectId", projectId)));
        expect("RecordRuntimeProfile", 201, ui(call("RecordRuntimeProfile", "projectId", projectId))
                .json(Map.of("javaVersion", "21", "springBootVersion", "3.5.0")));
        expect("RecordRuntimeProfile", 200, ui(call("RecordRuntimeProfile", "projectId", projectId))
                .json(Map.of("javaVersion", "21", "springBootVersion", "3.5.0")));
        expect("SaveClarificationAnswers", 200, ui(call("SaveClarificationAnswers", "projectId", projectId))
                .json(Map.of("answers", List.of(Map.of("questionCode", "TLS_TERMINATION", "optionCode", "INGRESS"),
                        Map.of("questionCode", "DEVICE_HARDWARE_OPENSSL", "freeText", "PYNQ-Z2, OpenSSL 3.0")))));
        expect("GetProjectProfile", 200, ui(call("GetProjectProfile", "projectId", projectId)));

        // consent (UI token only)
        Reply consent = expect("GrantConsent", 201, ui(call("GrantConsent", "projectId", projectId))
                .json(Map.of("consentType", "WAREHOUSE_ANALYTICS", "privacyNoticeVersion", 2)));
        // Only the latest notice version is accepted: version 1 is superseded by version 2 (D-135, D-284).
        expect("GrantConsent", 400, ui(call("GrantConsent", "projectId", projectId))
                .json(Map.of("consentType", "MODEL_TRAINING", "privacyNoticeVersion", 1)));
        expect("GetConsents", 200, ui(call("GetConsents", "projectId", projectId)));

        // scan, findings, topology, artifact
        Reply scan = expect("StartScan", 201, ui(call("StartScan", "projectId", projectId)));
        String scanId = scan.json().get("id").asString();
        expect("ListScans", 200, ui(call("ListScans", "projectId", projectId)));
        Reply findings = expect("RecordFindings", 201, ui(call("RecordFindings", "scanId", scanId)).json(Map.of("findings", List.of(finding()))));
        String findingId = findings.json().get("createdIds").get(0).asString();
        expect("ListFindings", 200, ui(call("ListFindings", "scanId", scanId)));
        expect("GetFinding", 200, ui(call("GetFinding", "findingId", findingId)));
        Map<String, Object> topology = Map.of(
                "nodes", List.of(Map.of("name", "gateway", "nodeKind", "GATEWAY"), Map.of("name", "ledger", "nodeKind", "SERVICE")),
                "links", List.of(Map.of("source", "gateway", "target", "ledger", "protocol", "HTTP", "tls", true, "mtls", true,
                        "callSites", List.of(Map.of("path", "src/main/java/Client.java", "lineStart", 5, "lineEnd", 6, "locationKind", "CODE")),
                        "findingIds", List.of(findingId))));
        expect("RecordTopology", 200, ui(call("RecordTopology", "scanId", scanId)).json(topology));
        expect("GetTopology", 200, ui(call("GetTopology", "scanId", scanId)));
        byte[] cbom = "{\"bomFormat\":\"CycloneDX\",\"specVersion\":\"1.6\"}".getBytes(StandardCharsets.UTF_8);
        Reply stored = expect("RecordScanArtifact", 200, ui(call("RecordScanArtifact", "scanId", scanId)).body(cbom, "application/json"));
        Reply artifact = expect("GetScanArtifact", 200, ui(call("GetScanArtifact", "scanId", scanId)));
        assertThat(artifact.body()).isEqualTo(cbom);
        assertThat(artifact.header("etag")).isEqualTo("\"" + stored.json().get("sha256").asString() + "\"");
        expect("CompleteScan", 200, ui(call("CompleteScan", "scanId", scanId)).json(Map.of("outcome", "COMPLETED")));
        expect("GetScanSummary", 200, ui(call("GetScanSummary", "scanId", scanId)));

        // plan, transition, report, audit
        Map<String, Object> plan = Map.of("items", List.of(Map.of("findingId", findingId, "riskScore", 0.7,
                "riskFactors", List.of(Map.of("featureName", "algorithm_weakness", "shapValue", 0.4)))));
        expect("CreatePlan", 201, ui(call("CreatePlan", "scanId", scanId)).json(plan));
        Reply page = expect("GetPlan", 200, ui(call("GetPlan", "scanId", scanId)));
        String itemId = page.json().get("items").get(0).get("id").asString();
        expect("TransitionPlanItem", 200, ui(call("TransitionPlanItem", "itemId", itemId)).header("If-Match", "\"1\"")
                .json(Map.of("toState", "APPROVED")));
        Reply report = expect("GetPlanReport", 200, ui(call("GetPlanReport", "scanId", scanId)));
        assertThat(report.header("content-type")).startsWith("text/markdown");
        expect("GetAuditLog", 200, ui(call("GetAuditLog", "query", "projectKey=" + projectKey)));
        expect("RelayOutboxEvents", 200, call("RelayOutboxEvents").internal(INTERNAL_TOKEN).json(Map.of("batchSize", 10)));

        // revoke and delete
        int version = consent.json().get("version").asInt();
        expect("RevokeConsent", 200, ui(call("RevokeConsent", "projectId", projectId, "consentType", "WAREHOUSE_ANALYTICS"))
                .header("If-Match", "\"" + version + "\""));
        expect("DeleteProject", 204, ui(call("DeleteProject", "projectId", projectId)));

        assertThat(projectKey).matches("[0-9a-f]{64}");
        assertThat(exercised).isEqualTo(CONTRACT.operations().stream().map(Operation::id).collect(Collectors.toCollection(TreeSet::new)));
    }

    private static String problemType(Reply reply) {
        return reply.json().get("type").asString().replace("https://quancrypt.local/problems/", "");
    }

    private void problem(String operationId, int status, String code, ApiClient.Call call) {
        Reply reply = call.send();
        assertThat(reply.status()).as(reply.text()).isEqualTo(status);
        assertThat(reply.header("content-type")).startsWith("application/problem+json");
        assertThat(problemType(reply)).isEqualTo(code);
        conforms(CONTRACT.operation(operationId), reply);
        assertThat(reply.text()).doesNotContain("Exception").doesNotContain("at com.quancrypt");
    }

    @Test
    void failuresArePrivacyPreservingProblemDetails() {
        UUID unknown = UUID.randomUUID();
        UUID project = UUID.fromString(ui(api().post("/api/v1/projects")).json(Map.of("identity", "/work/demo", "displayName", "Demo"))
                .send().json().get("id").asString());

        problem("RegisterProject", 400, "validation-failed", ui(api().post("/api/v1/projects")).json(Map.of()));
        problem("RegisterProject", 400, "validation-failed",
                ui(api().post("/api/v1/projects")).json(Map.of("identity", "x", "displayName", "y", "extra", "field")));
        problem("RegisterProject", 400, "validation-failed", ui(api().post("/api/v1/projects")).body("{not json".getBytes(StandardCharsets.UTF_8),
                "application/json"));
        problem("RegisterProject", 400, "validation-failed", ui(api().post("/api/v1/projects")).body("x".getBytes(StandardCharsets.UTF_8), "text/plain"));
        problem("GetProject", 404, "not-found", ui(api().get("/api/v1/projects/" + unknown)));
        problem("GetProject", 404, "not-found", ui(api().get("/api/v1/projects/not-a-uuid")));
        problem("ListProjects", 400, "validation-failed", ui(api().get("/api/v1/projects?size=0")));
        problem("ListProjects", 400, "validation-failed", ui(api().get("/api/v1/projects?size=201")));
        problem("ListProjects", 400, "validation-failed", ui(api().get("/api/v1/projects?page=-1")));
        problem("StartScan", 404, "not-found", ui(api().post("/api/v1/projects/" + unknown + "/scans")));
        assertThat(ui(api().post("/api/v1/projects/" + project + "/scans")).send().status()).isEqualTo(201);
        problem("StartScan", 409, "scan-already-running", ui(api().post("/api/v1/projects/" + project + "/scans")));
        problem("RevokeConsent", 428, "precondition-required", ui(api().delete("/api/v1/projects/" + project + "/consents/WAREHOUSE_ANALYTICS")));
        problem("RevokeConsent", 428, "precondition-required",
                ui(api().delete("/api/v1/projects/" + project + "/consents/WAREHOUSE_ANALYTICS")).header("If-Match", "3"));
        assertThat(ui(api().post("/api/v1/projects")).header("Idempotency-Key", "k1").json(Map.of("identity", "/work/one", "displayName", "One"))
                .send().status()).isEqualTo(201);
        problem("RegisterProject", 409, "idempotency-conflict", ui(api().post("/api/v1/projects")).header("Idempotency-Key", "k1")
                .json(Map.of("identity", "/work/two", "displayName", "Two")));
        problem("RelayOutboxEvents", 400, "validation-failed", api().post("/api/v1/internal/outbox/relay").internal(INTERNAL_TOKEN)
                .json(Map.of("batchSize", 0)));
    }

    @Test
    void artifactLimitsAndTypesAreEnforced() {
        UUID project = UUID.fromString(ui(api().post("/api/v1/projects")).json(Map.of("identity", "/work/cbom", "displayName", "Cbom"))
                .send().json().get("id").asString());
        UUID scan = UUID.fromString(ui(api().post("/api/v1/projects/" + project + "/scans")).send().json().get("id").asString());
        String path = "/api/v1/scans/" + scan + "/artifact";

        problem("RecordScanArtifact", 415, "unsupported-media-type", ui(api().put(path)).body("x".getBytes(StandardCharsets.UTF_8), "text/plain"));
        problem("RecordScanArtifact", 413, "payload-too-large", ui(api().put(path)).body(new byte[20 * 1024 * 1024 + 1], "application/json"));
        problem("RecordScanArtifact", 404, "not-found", ui(api().put("/api/v1/scans/" + UUID.randomUUID() + "/artifact"))
                .body("{}".getBytes(StandardCharsets.UTF_8), "application/json"));
        assertThat(ui(api().put(path)).body("{}".getBytes(StandardCharsets.UTF_8), "application/vnd.cyclonedx+json; charset=utf-8")
                .send().status()).isEqualTo(200);
    }
}

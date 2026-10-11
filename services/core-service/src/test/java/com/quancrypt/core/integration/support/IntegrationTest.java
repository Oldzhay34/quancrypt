package com.quancrypt.core.integration.support;

import com.quancrypt.core.CoreServiceApplication;
import com.quancrypt.core.infrastructure.persistence.audit.JdbcAuditLogWriter;
import com.quancrypt.core.infrastructure.transaction.SpringTransactionRunner;
import com.quancrypt.core.port.inbound.CompleteScanCommand;
import com.quancrypt.core.port.inbound.CompleteScanUseCase;
import com.quancrypt.core.port.inbound.CreatePlanCommand;
import com.quancrypt.core.port.inbound.CreatePlanUseCase;
import com.quancrypt.core.port.inbound.DeleteProjectUseCase;
import com.quancrypt.core.port.inbound.FindingInput;
import com.quancrypt.core.port.inbound.GrantConsentCommand;
import com.quancrypt.core.port.inbound.GrantConsentUseCase;
import com.quancrypt.core.port.inbound.Idempotency;
import com.quancrypt.core.port.inbound.PlanItemInput;
import com.quancrypt.core.port.inbound.RecordFindingsCommand;
import com.quancrypt.core.port.inbound.RecordFindingsUseCase;
import com.quancrypt.core.port.inbound.RecordRuntimeProfileUseCase;
import com.quancrypt.core.port.inbound.RecordScanArtifactUseCase;
import com.quancrypt.core.port.inbound.RecordTopologyUseCase;
import com.quancrypt.core.port.inbound.RegisterProjectCommand;
import com.quancrypt.core.port.inbound.RegisterProjectUseCase;
import com.quancrypt.core.port.inbound.RelayOutboxEventsUseCase;
import com.quancrypt.core.port.inbound.RevokeConsentUseCase;
import com.quancrypt.core.port.inbound.RiskFactorInput;
import com.quancrypt.core.port.inbound.SaveClarificationAnswersUseCase;
import com.quancrypt.core.port.inbound.StartScanCommand;
import com.quancrypt.core.port.inbound.StartScanUseCase;
import com.quancrypt.core.port.inbound.TransitionPlanItemUseCase;
import com.quancrypt.core.port.inbound.view.PlanView;
import com.quancrypt.core.port.inbound.view.RecordFindingsResult;
import com.quancrypt.core.port.outbound.TransactionRunner;
import java.math.BigDecimal;
import java.security.SecureRandom;
import java.util.HexFormat;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.transaction.PlatformTransactionManager;

/**
 * Base of the Spring integration tests: the real composition root (infrastructure/config) on the Testcontainers
 * PostgreSQL, connected as core_db_app, with the relay scheduler off as in production (D-155) and the publisher pointed
 * at a loopback ingest-api stub. Every test starts from an empty database.
 */
@SpringBootTest(classes = {CoreServiceApplication.class, IntegrationTest.TestDoubles.class},
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
public abstract class IntegrationTest {

    protected static final IngestApiStub INGEST = new IngestApiStub();
    private static final SecureRandom RANDOM = new SecureRandom();
    protected static final String SALT = randomSalt();
    protected static final String SESSION_TOKEN = randomSalt();
    protected static final String INTERNAL_TOKEN = randomSalt();

    @Value("${local.server.port}") protected int port;
    @Autowired protected ArmedAuditLogWriter auditFailure;
    @Autowired protected RetryLog retries;
    @Autowired protected JdbcClient jdbc;
    @Autowired protected RegisterProjectUseCase registerProject;
    @Autowired protected RecordRuntimeProfileUseCase recordRuntimeProfile;
    @Autowired protected DeleteProjectUseCase deleteProject;
    @Autowired protected GrantConsentUseCase grantConsent;
    @Autowired protected RevokeConsentUseCase revokeConsent;
    @Autowired protected StartScanUseCase startScan;
    @Autowired protected RecordFindingsUseCase recordFindings;
    @Autowired protected RecordTopologyUseCase recordTopology;
    @Autowired protected RecordScanArtifactUseCase recordScanArtifact;
    @Autowired protected CompleteScanUseCase completeScan;
    @Autowired protected SaveClarificationAnswersUseCase saveClarificationAnswers;
    @Autowired protected CreatePlanUseCase createPlan;
    @Autowired protected TransitionPlanItemUseCase transitionPlanItem;
    @Autowired protected RelayOutboxEventsUseCase relayOutboxEvents;

    @DynamicPropertySource
    static void database(DynamicPropertyRegistry registry) {
        PostgresTestDatabase database = PostgresTestDatabase.get();
        registry.add("spring.datasource.url", database::url);
        registry.add("spring.datasource.password", database::appPassword);
        registry.add("quancrypt.migration.password", database::migratorPassword);
        registry.add("quancrypt.anon-salt", () -> SALT);
        registry.add("quancrypt.session-token", () -> SESSION_TOKEN);
        registry.add("quancrypt.internal-token", () -> INTERNAL_TOKEN);
        registry.add("quancrypt.outbox.ingest-url", INGEST::url);
        registry.add("quancrypt.outbox.relay.enabled", () -> "false");
    }

    @BeforeEach
    void emptyDatabase() {
        PostgresTestDatabase.get().truncate();
        auditFailure.disarm();
        retries.clear();
        INGEST.reset();
    }

    private static String randomSalt() {
        byte[] bytes = new byte[32];
        RANDOM.nextBytes(bytes);
        return HexFormat.of().formatHex(bytes);
    }

    protected ApiClient api() {
        return new ApiClient(port);
    }

    /** Row count of a table, read as the migrator so the check does not depend on the app role's grants. */
    protected static long rows(String table) {
        return JdbcClient.create(PostgresTestDatabase.get().migrator()).sql("SELECT count(*) FROM " + table).query(Long.class).single();
    }

    protected static Optional<Idempotency> idem(String key, String digest) {
        return Optional.of(new Idempotency(key, digest));
    }

    // ------------------------------------------------------------------ scenario helpers

    protected UUID project(String identity) {
        return registerProject.execute(new RegisterProjectCommand(identity, "Demo", Optional.empty(), "UI")).id();
    }

    protected UUID projectWithConsent(String identity) {
        UUID projectId = project(identity);
        grantConsent.execute(new GrantConsentCommand(projectId, "WAREHOUSE_ANALYTICS", 1, Optional.empty(), Optional.empty(), "UI"));
        return projectId;
    }

    protected UUID runningScan(UUID projectId) {
        return startScan.execute(new StartScanCommand(projectId, Optional.empty(), "UI")).id();
    }

    protected static FindingInput tlsFinding(String path, String symbol) {
        return new FindingInput(path, symbol, "RSA", "TLS_KEY_EXCHANGE", "CODE", "P1", Optional.of(2048), Optional.of(10), Optional.of(12),
                0.9, "STATIC");
    }

    protected RecordFindingsResult record(UUID scanId, FindingInput... findings) {
        return recordFindings.execute(new RecordFindingsCommand(scanId, List.of(findings), Optional.empty(), "UI"));
    }

    protected void complete(UUID scanId) {
        completeScan.execute(new CompleteScanCommand(scanId, "COMPLETED", Optional.empty(), "UI"));
    }

    protected List<PlanItemInput> assessAll(List<UUID> findingIds) {
        return findingIds.stream()
                .map(id -> new PlanItemInput(id, 0.7, List.of(new RiskFactorInput("algorithm_weakness", new BigDecimal("0.4")))))
                .toList();
    }

    protected PlanView plan(UUID scanId, List<UUID> findingIds) {
        return createPlan.execute(new CreatePlanCommand(scanId, assessAll(findingIds), Optional.empty(), "UI"));
    }

    /** A project with warehouse consent, a completed scan with one finding and a plan; returns the plan item id. */
    protected UUID plannedItem(String identity) {
        UUID projectId = projectWithConsent(identity);
        UUID scanId = runningScan(projectId);
        List<UUID> ids = record(scanId, tlsFinding("src/main/java/Tls.java", "Tls#handshake")).createdIds();
        complete(scanId);
        plan(scanId, ids);
        return jdbc.sql("SELECT pi.id FROM plan_item pi JOIN plan p ON p.id = pi.plan_id WHERE p.scan_id = :scanId")
                .param("scanId", scanId).query(UUID.class).single();
    }

    /**
     * Test doubles of the composition root: the JDBC audit writer behind a switch that can fail the next append, and the
     * real transaction runner reporting its retries to a log the tests read.
     */
    @TestConfiguration(proxyBeanMethods = false)
    static class TestDoubles {

        @Bean
        RetryLog retryLog() {
            return new RetryLog();
        }

        @Bean
        @Primary
        TransactionRunner observedTransactionRunner(PlatformTransactionManager transactionManager, RetryLog retryLog) {
            return new SpringTransactionRunner(transactionManager, retryLog);
        }

        @Bean
        @Primary
        ArmedAuditLogWriter armedAuditLogWriter(JdbcClient jdbc) {
            return new ArmedAuditLogWriter(new JdbcAuditLogWriter(jdbc));
        }
    }
}

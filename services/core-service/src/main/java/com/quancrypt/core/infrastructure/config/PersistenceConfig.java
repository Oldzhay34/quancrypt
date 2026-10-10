package com.quancrypt.core.infrastructure.config;

import com.quancrypt.core.infrastructure.outbox.JdbcOutboxRelayRepository;
import com.quancrypt.core.infrastructure.outbox.JdbcOutboxWriter;
import com.quancrypt.core.infrastructure.outbox.OutboxJson;
import com.quancrypt.core.infrastructure.persistence.FlywayMigrator;
import com.quancrypt.core.infrastructure.persistence.audit.JdbcAuditLogReader;
import com.quancrypt.core.infrastructure.persistence.audit.JdbcAuditLogWriter;
import com.quancrypt.core.infrastructure.persistence.clarification.JdbcClarificationReader;
import com.quancrypt.core.infrastructure.persistence.clarification.JdbcClarificationWriter;
import com.quancrypt.core.infrastructure.persistence.consent.JdbcConsentLock;
import com.quancrypt.core.infrastructure.persistence.consent.JdbcConsentReader;
import com.quancrypt.core.infrastructure.persistence.consent.JdbcConsentWriter;
import com.quancrypt.core.infrastructure.persistence.consent.JdbcPrivacyNoticeReader;
import com.quancrypt.core.infrastructure.persistence.finding.JdbcFindingReader;
import com.quancrypt.core.infrastructure.persistence.finding.JdbcFindingWriter;
import com.quancrypt.core.infrastructure.persistence.finding.JdbcPlanningContextReader;
import com.quancrypt.core.infrastructure.persistence.finding.JdbcSourceFileReader;
import com.quancrypt.core.infrastructure.persistence.finding.JdbcSourceFileWriter;
import com.quancrypt.core.infrastructure.persistence.idempotency.JdbcIdempotencyStore;
import com.quancrypt.core.infrastructure.persistence.lookup.JdbcRiskThresholdReader;
import com.quancrypt.core.infrastructure.persistence.plan.JdbcPlanReader;
import com.quancrypt.core.infrastructure.persistence.plan.JdbcPlanWriter;
import com.quancrypt.core.infrastructure.persistence.profile.JdbcRuntimeProfileReader;
import com.quancrypt.core.infrastructure.persistence.profile.JdbcRuntimeProfileWriter;
import com.quancrypt.core.infrastructure.persistence.project.JdbcProjectLock;
import com.quancrypt.core.infrastructure.persistence.project.JdbcProjectReader;
import com.quancrypt.core.infrastructure.persistence.project.JdbcProjectWriter;
import com.quancrypt.core.infrastructure.persistence.scan.JdbcScanArtifactReader;
import com.quancrypt.core.infrastructure.persistence.scan.JdbcScanArtifactWriter;
import com.quancrypt.core.infrastructure.persistence.scan.JdbcScanLock;
import com.quancrypt.core.infrastructure.persistence.scan.JdbcScanReader;
import com.quancrypt.core.infrastructure.persistence.scan.JdbcScanWriter;
import com.quancrypt.core.infrastructure.persistence.topology.JdbcTopologyReader;
import com.quancrypt.core.infrastructure.persistence.topology.JdbcTopologyWriter;
import com.quancrypt.core.infrastructure.transaction.SpringTransactionRunner;
import com.quancrypt.core.port.outbound.AuditLogReader;
import com.quancrypt.core.port.outbound.AuditLogWriter;
import com.quancrypt.core.port.outbound.ClarificationReader;
import com.quancrypt.core.port.outbound.ClarificationWriter;
import com.quancrypt.core.port.outbound.ConsentLock;
import com.quancrypt.core.port.outbound.ConsentReader;
import com.quancrypt.core.port.outbound.ConsentWriter;
import com.quancrypt.core.port.outbound.FindingReader;
import com.quancrypt.core.port.outbound.FindingWriter;
import com.quancrypt.core.port.outbound.IdGenerator;
import com.quancrypt.core.port.outbound.IdempotencyStore;
import com.quancrypt.core.port.outbound.OutboxRelayRepository;
import com.quancrypt.core.port.outbound.OutboxWriter;
import com.quancrypt.core.port.outbound.PlanReader;
import com.quancrypt.core.port.outbound.PlanWriter;
import com.quancrypt.core.port.outbound.PlanningContextReader;
import com.quancrypt.core.port.outbound.PrivacyNoticeReader;
import com.quancrypt.core.port.outbound.ProjectLock;
import com.quancrypt.core.port.outbound.ProjectReader;
import com.quancrypt.core.port.outbound.ProjectWriter;
import com.quancrypt.core.port.outbound.RiskThresholdReader;
import com.quancrypt.core.port.outbound.RuntimeProfileReader;
import com.quancrypt.core.port.outbound.RuntimeProfileWriter;
import com.quancrypt.core.port.outbound.ScanArtifactReader;
import com.quancrypt.core.port.outbound.ScanArtifactWriter;
import com.quancrypt.core.port.outbound.ScanLock;
import com.quancrypt.core.port.outbound.ScanReader;
import com.quancrypt.core.port.outbound.ScanWriter;
import com.quancrypt.core.port.outbound.SourceFileReader;
import com.quancrypt.core.port.outbound.SourceFileWriter;
import com.quancrypt.core.port.outbound.TopologyReader;
import com.quancrypt.core.port.outbound.TopologyWriter;
import com.quancrypt.core.port.outbound.TransactionRunner;
import javax.sql.DataSource;
import org.flywaydb.core.api.output.MigrateResult;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcOperations;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.PlatformTransactionManager;

/**
 * Composition root of the JDBC adapters; migrations run (as the migrator role) before any adapter can reach the database.
 * The class is longer than the usual 200 lines (solid-checklist S) because each outbound persistence port has its own
 * one-line bean method; it holds no logic and changes only when an adapter is added.
 */
@Configuration(proxyBeanMethods = false)
public class PersistenceConfig {

    @Bean
    MigrateResult coreDbMigration(
            @Value("${spring.datasource.url}") String url,
            @Value("${quancrypt.migration.username}") String user,
            @Value("${quancrypt.migration.password}") String password) {
        return new FlywayMigrator(url, user, password).migrate();
    }

    @Bean
    NamedParameterJdbcOperations namedParameterJdbcOperations(DataSource dataSource, MigrateResult coreDbMigration) {
        return new NamedParameterJdbcTemplate(dataSource);
    }

    @Bean
    JdbcClient jdbcClient(NamedParameterJdbcOperations operations) {
        return JdbcClient.create(operations);
    }

    @Bean
    TransactionRunner transactionRunner(PlatformTransactionManager transactionManager) {
        Logger log = LoggerFactory.getLogger(SpringTransactionRunner.class);
        return new SpringTransactionRunner(transactionManager,
                (isolation, sqlState, attempt) -> log.warn("transaction retried: SQLSTATE {} under {}, retry {}", sqlState, isolation, attempt));
    }

    @Bean
    ProjectReader projectReader(JdbcClient jdbc) {
        return new JdbcProjectReader(jdbc);
    }

    @Bean
    ProjectWriter projectWriter(JdbcClient jdbc) {
        return new JdbcProjectWriter(jdbc);
    }

    @Bean
    ProjectLock projectLock(JdbcClient jdbc) {
        return new JdbcProjectLock(jdbc);
    }

    @Bean
    ConsentReader consentReader(JdbcClient jdbc) {
        return new JdbcConsentReader(jdbc);
    }

    @Bean
    ConsentWriter consentWriter(JdbcClient jdbc) {
        return new JdbcConsentWriter(jdbc);
    }

    @Bean
    ConsentLock consentLock(JdbcClient jdbc) {
        return new JdbcConsentLock(jdbc);
    }

    @Bean
    PrivacyNoticeReader privacyNoticeReader(JdbcClient jdbc) {
        return new JdbcPrivacyNoticeReader(jdbc);
    }

    @Bean
    RuntimeProfileReader runtimeProfileReader(JdbcClient jdbc) {
        return new JdbcRuntimeProfileReader(jdbc);
    }

    @Bean
    RuntimeProfileWriter runtimeProfileWriter(JdbcClient jdbc, IdGenerator ids) {
        return new JdbcRuntimeProfileWriter(jdbc, ids);
    }

    @Bean
    ScanReader scanReader(JdbcClient jdbc) {
        return new JdbcScanReader(jdbc);
    }

    @Bean
    ScanWriter scanWriter(JdbcClient jdbc) {
        return new JdbcScanWriter(jdbc);
    }

    @Bean
    ScanLock scanLock(JdbcClient jdbc) {
        return new JdbcScanLock(jdbc);
    }

    @Bean
    ScanArtifactReader scanArtifactReader(JdbcClient jdbc) {
        return new JdbcScanArtifactReader(jdbc);
    }

    @Bean
    ScanArtifactWriter scanArtifactWriter(JdbcClient jdbc, IdGenerator ids) {
        return new JdbcScanArtifactWriter(jdbc, ids);
    }

    @Bean
    SourceFileReader sourceFileReader(JdbcClient jdbc) {
        return new JdbcSourceFileReader(jdbc);
    }

    @Bean
    SourceFileWriter sourceFileWriter(JdbcClient jdbc, NamedParameterJdbcOperations batch) {
        return new JdbcSourceFileWriter(jdbc, batch);
    }

    @Bean
    FindingReader findingReader(JdbcClient jdbc) {
        return new JdbcFindingReader(jdbc);
    }

    @Bean
    FindingWriter findingWriter(NamedParameterJdbcOperations batch) {
        return new JdbcFindingWriter(batch);
    }

    @Bean
    PlanningContextReader planningContextReader(JdbcClient jdbc) {
        return new JdbcPlanningContextReader(jdbc);
    }

    @Bean
    TopologyReader topologyReader(JdbcClient jdbc) {
        return new JdbcTopologyReader(jdbc);
    }

    @Bean
    TopologyWriter topologyWriter(JdbcClient jdbc, NamedParameterJdbcOperations batch, IdGenerator ids) {
        return new JdbcTopologyWriter(jdbc, batch, ids);
    }

    @Bean
    PlanReader planReader(JdbcClient jdbc) {
        return new JdbcPlanReader(jdbc);
    }

    @Bean
    PlanWriter planWriter(JdbcClient jdbc, NamedParameterJdbcOperations batch) {
        return new JdbcPlanWriter(jdbc, batch);
    }

    @Bean
    RiskThresholdReader riskThresholdReader(JdbcClient jdbc) {
        return new JdbcRiskThresholdReader(jdbc);
    }

    @Bean
    ClarificationReader clarificationReader(JdbcClient jdbc) {
        return new JdbcClarificationReader(jdbc);
    }

    @Bean
    ClarificationWriter clarificationWriter(NamedParameterJdbcOperations batch) {
        return new JdbcClarificationWriter(batch);
    }

    @Bean
    AuditLogWriter auditLogWriter(JdbcClient jdbc) {
        return new JdbcAuditLogWriter(jdbc);
    }

    @Bean
    AuditLogReader auditLogReader(JdbcClient jdbc) {
        return new JdbcAuditLogReader(jdbc);
    }

    @Bean
    IdempotencyStore idempotencyStore(JdbcClient jdbc) {
        return new JdbcIdempotencyStore(jdbc);
    }

    @Bean
    OutboxWriter outboxWriter(JdbcClient jdbc, OutboxJson json) {
        return new JdbcOutboxWriter(jdbc, json);
    }

    @Bean
    OutboxRelayRepository outboxRelayRepository(JdbcClient jdbc, OutboxJson json) {
        return new JdbcOutboxRelayRepository(jdbc, json);
    }
}

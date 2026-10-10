package com.quancrypt.core.integration.support;

import com.quancrypt.core.contract.PortSet;
import com.quancrypt.core.infrastructure.outbox.JdbcOutboxRelayRepository;
import com.quancrypt.core.infrastructure.outbox.JdbcOutboxWriter;
import com.quancrypt.core.infrastructure.outbox.OutboxJson;
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
import com.quancrypt.core.infrastructure.id.RandomIdGenerator;
import com.quancrypt.core.port.outbound.IdGenerator;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.core.simple.JdbcClient;

/** The JDBC adapters on an emptied test database, connected as core_db_app (autocommit per statement). */
public final class JdbcPortSet {

    private JdbcPortSet() {
    }

    public static PortSet fresh() {
        PostgresTestDatabase database = PostgresTestDatabase.get();
        database.truncate();
        NamedParameterJdbcTemplate batch = new NamedParameterJdbcTemplate(database.app());
        JdbcClient jdbc = JdbcClient.create(batch);
        IdGenerator ids = new RandomIdGenerator();
        OutboxJson json = new OutboxJson();
        JdbcProjectReader projectReader = new JdbcProjectReader(jdbc);
        return new PortSet(
                projectReader, new JdbcProjectWriter(jdbc), new JdbcProjectLock(jdbc),
                new JdbcConsentReader(jdbc), new JdbcConsentWriter(jdbc), new JdbcConsentLock(jdbc), new JdbcPrivacyNoticeReader(jdbc),
                new JdbcRuntimeProfileReader(jdbc), new JdbcRuntimeProfileWriter(jdbc, ids),
                new JdbcScanReader(jdbc), new JdbcScanWriter(jdbc), new JdbcScanLock(jdbc), new JdbcScanArtifactReader(jdbc),
                new JdbcScanArtifactWriter(jdbc, ids),
                new JdbcSourceFileReader(jdbc), new JdbcSourceFileWriter(jdbc, batch), new JdbcFindingReader(jdbc), new JdbcFindingWriter(batch),
                new JdbcPlanningContextReader(jdbc), new JdbcTopologyReader(jdbc), new JdbcTopologyWriter(jdbc, batch, ids),
                new JdbcPlanReader(jdbc), new JdbcPlanWriter(jdbc, batch), new JdbcRiskThresholdReader(jdbc),
                new JdbcClarificationReader(jdbc), new JdbcClarificationWriter(batch),
                new JdbcAuditLogReader(jdbc), new JdbcAuditLogWriter(jdbc),
                new JdbcIdempotencyStore(jdbc), new JdbcOutboxWriter(jdbc, json), new JdbcOutboxRelayRepository(jdbc, json));
    }
}

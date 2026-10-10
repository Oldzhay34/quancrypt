package com.quancrypt.core.contract;

import com.quancrypt.core.domain.model.PrivacyNotice;
import com.quancrypt.core.fake.FakeArtifacts;
import com.quancrypt.core.fake.FakeAuditLog;
import com.quancrypt.core.fake.FakeClarifications;
import com.quancrypt.core.fake.FakeConsents;
import com.quancrypt.core.fake.FakeFindings;
import com.quancrypt.core.fake.FakeIdempotency;
import com.quancrypt.core.fake.FakeNotices;
import com.quancrypt.core.fake.FakeOutbox;
import com.quancrypt.core.fake.FakePlans;
import com.quancrypt.core.fake.FakeProfiles;
import com.quancrypt.core.fake.FakeProjects;
import com.quancrypt.core.fake.FakeScans;
import com.quancrypt.core.fake.FakeSourceFiles;
import com.quancrypt.core.fake.FakeTopologies;
import com.quancrypt.core.fake.InMemoryDatabase;
import com.quancrypt.core.port.outbound.AuditLogReader;
import com.quancrypt.core.port.outbound.AuditLogWriter;
import com.quancrypt.core.port.outbound.ClarificationReader;
import com.quancrypt.core.port.outbound.ClarificationWriter;
import com.quancrypt.core.port.outbound.ConsentLock;
import com.quancrypt.core.port.outbound.ConsentReader;
import com.quancrypt.core.port.outbound.ConsentWriter;
import com.quancrypt.core.port.outbound.FindingReader;
import com.quancrypt.core.port.outbound.FindingWriter;
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
import java.time.Instant;
import java.util.UUID;

/** Every outbound persistence port, from one implementation family (in-memory fakes or JDBC adapters). */
public record PortSet(
        ProjectReader projectReader, ProjectWriter projectWriter, ProjectLock projectLock,
        ConsentReader consentReader, ConsentWriter consentWriter, ConsentLock consentLock, PrivacyNoticeReader privacyNotices,
        RuntimeProfileReader profileReader, RuntimeProfileWriter profileWriter,
        ScanReader scanReader, ScanWriter scanWriter, ScanLock scanLock, ScanArtifactReader artifactReader, ScanArtifactWriter artifactWriter,
        SourceFileReader sourceFileReader, SourceFileWriter sourceFileWriter, FindingReader findingReader, FindingWriter findingWriter,
        PlanningContextReader planningContext, TopologyReader topologyReader, TopologyWriter topologyWriter,
        PlanReader planReader, PlanWriter planWriter, RiskThresholdReader riskThresholds,
        ClarificationReader clarificationReader, ClarificationWriter clarificationWriter,
        AuditLogReader auditReader, AuditLogWriter auditWriter,
        IdempotencyStore idempotency, OutboxWriter outboxWriter, OutboxRelayRepository outboxRelay) {

    /** The in-memory fakes of the unit tests, with privacy notice version 1 as the migration seeds it. */
    public static PortSet fake() {
        InMemoryDatabase db = new InMemoryDatabase();
        db.notices.add(new PrivacyNotice(UUID.randomUUID(), 1, "metin", "text", Instant.parse("2026-10-09T00:00:00Z")));
        FakeProjects projects = new FakeProjects(db);
        FakeConsents consents = new FakeConsents(db);
        FakeProfiles profiles = new FakeProfiles(db);
        FakeScans scans = new FakeScans(db);
        FakeArtifacts artifacts = new FakeArtifacts(db);
        FakeSourceFiles files = new FakeSourceFiles(db);
        FakeFindings findings = new FakeFindings(db);
        FakeTopologies topologies = new FakeTopologies(db);
        FakePlans plans = new FakePlans(db);
        FakeClarifications clarifications = new FakeClarifications(db);
        FakeAuditLog audit = new FakeAuditLog(db);
        FakeOutbox outbox = new FakeOutbox(db);
        return new PortSet(projects, projects, projects, consents, consents, consents, new FakeNotices(db), profiles, profiles,
                scans, scans, scans, artifacts, artifacts, files, files, findings, findings, findings, topologies, topologies,
                plans, plans, plans, clarifications, clarifications, audit, audit, new FakeIdempotency(db), outbox, outbox);
    }
}

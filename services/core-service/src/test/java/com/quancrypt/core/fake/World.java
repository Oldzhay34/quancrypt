package com.quancrypt.core.fake;

import com.quancrypt.core.domain.model.AuditAction;
import com.quancrypt.core.domain.model.AuditEntry;
import com.quancrypt.core.domain.model.EventType;
import com.quancrypt.core.domain.model.OutboxRecord;
import com.quancrypt.core.domain.model.PrivacyNotice;
import com.quancrypt.core.domain.policy.EffortPolicy;
import com.quancrypt.core.domain.policy.JdkRequirementPolicy;
import com.quancrypt.core.domain.policy.PriorityClassifier;
import com.quancrypt.core.domain.policy.PriorityPolicy;
import com.quancrypt.core.domain.service.StrategyPlanner;
import com.quancrypt.core.domain.service.StrategyRegistry;
import com.quancrypt.core.domain.service.strategy.DeviceHybridTlsStrategy;
import com.quancrypt.core.domain.service.strategy.FixWeakClassicStrategy;
import com.quancrypt.core.domain.service.strategy.HybridKexClassicCertStrategy;
import com.quancrypt.core.domain.service.strategy.HybridTlsKexStrategy;
import com.quancrypt.core.domain.service.strategy.JdkUpgradeStrategy;
import com.quancrypt.core.domain.service.strategy.KeepShortLivedTokenStrategy;
import com.quancrypt.core.domain.service.strategy.KemDemEncryptionStrategy;
import com.quancrypt.core.domain.service.strategy.PqSignatureStrategy;
import com.quancrypt.core.port.inbound.CompleteScanCommand;
import com.quancrypt.core.port.inbound.CreatePlanCommand;
import com.quancrypt.core.port.inbound.FindingInput;
import com.quancrypt.core.port.inbound.GrantConsentCommand;
import com.quancrypt.core.port.inbound.Idempotency;
import com.quancrypt.core.port.inbound.PlanItemInput;
import com.quancrypt.core.port.inbound.RecordFindingsCommand;
import com.quancrypt.core.port.inbound.RegisterProjectCommand;
import com.quancrypt.core.port.inbound.RiskFactorInput;
import com.quancrypt.core.port.inbound.StartScanCommand;
import com.quancrypt.core.port.inbound.view.PlanView;
import com.quancrypt.core.port.inbound.view.RecordFindingsResult;
import com.quancrypt.core.port.inbound.view.ScanView;
import com.quancrypt.core.usecase.AuditRecorder;
import com.quancrypt.core.usecase.CompleteScanService;
import com.quancrypt.core.usecase.ConsentGate;
import com.quancrypt.core.usecase.CreatePlanService;
import com.quancrypt.core.usecase.DeleteProjectService;
import com.quancrypt.core.usecase.EventRecorder;
import com.quancrypt.core.usecase.FindingValidator;
import com.quancrypt.core.usecase.GetAuditLogService;
import com.quancrypt.core.usecase.GetConsentsService;
import com.quancrypt.core.usecase.GetFindingService;
import com.quancrypt.core.usecase.GetPlanReportService;
import com.quancrypt.core.usecase.GetPlanService;
import com.quancrypt.core.usecase.GetPrivacyNoticeService;
import com.quancrypt.core.usecase.GetProjectProfileService;
import com.quancrypt.core.usecase.GetProjectService;
import com.quancrypt.core.usecase.GetScanArtifactService;
import com.quancrypt.core.usecase.GetScanSummaryService;
import com.quancrypt.core.usecase.GetTopologyService;
import com.quancrypt.core.usecase.GrantConsentService;
import com.quancrypt.core.usecase.IdempotentExecutor;
import com.quancrypt.core.usecase.ListFindingsService;
import com.quancrypt.core.usecase.ListProjectsService;
import com.quancrypt.core.usecase.ListScansService;
import com.quancrypt.core.usecase.RecordFindingsService;
import com.quancrypt.core.usecase.RecordRuntimeProfileService;
import com.quancrypt.core.usecase.RecordScanArtifactService;
import com.quancrypt.core.usecase.RecordTopologyService;
import com.quancrypt.core.usecase.RegisterProjectService;
import com.quancrypt.core.usecase.RelayOutboxEventsService;
import com.quancrypt.core.usecase.RevokeConsentService;
import com.quancrypt.core.usecase.SaveClarificationAnswersService;
import com.quancrypt.core.usecase.ScanAccess;
import com.quancrypt.core.usecase.SourceFileResolver;
import com.quancrypt.core.usecase.StartScanService;
import com.quancrypt.core.usecase.TransitionPlanItemService;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

/** Wires the 28 use cases to the in-memory ports; the fixture every use case test starts from. */
public final class World {

    public final InMemoryDatabase db = new InMemoryDatabase();
    public final FixedClock clock = new FixedClock(Instant.parse("2026-10-09T10:00:00Z"));
    public final SequentialIdGenerator ids = new SequentialIdGenerator();
    public final FakeTransactionRunner tx = new FakeTransactionRunner(db);
    public final FakeAuditLog auditLog = new FakeAuditLog(db);
    public final RecordingPublisher publisher = new RecordingPublisher();

    public final RegisterProjectService registerProject;
    public final GetProjectService getProject;
    public final ListProjectsService listProjects;
    public final RecordRuntimeProfileService recordRuntimeProfile;
    public final DeleteProjectService deleteProject;
    public final GetPrivacyNoticeService getPrivacyNotice;
    public final GrantConsentService grantConsent;
    public final RevokeConsentService revokeConsent;
    public final GetConsentsService getConsents;
    public final StartScanService startScan;
    public final ListScansService listScans;
    public final RecordFindingsService recordFindings;
    public final RecordTopologyService recordTopology;
    public final RecordScanArtifactService recordScanArtifact;
    public final GetScanArtifactService getScanArtifact;
    public final CompleteScanService completeScan;
    public final GetScanSummaryService getScanSummary;
    public final ListFindingsService listFindings;
    public final GetFindingService getFinding;
    public final GetTopologyService getTopology;
    public final SaveClarificationAnswersService saveClarificationAnswers;
    public final GetProjectProfileService getProjectProfile;
    public final CreatePlanService createPlan;
    public final GetPlanService getPlan;
    public final TransitionPlanItemService transitionPlanItem;
    public final GetPlanReportService getPlanReport;
    public final GetAuditLogService getAuditLog;
    public final RelayOutboxEventsService relayOutboxEvents;

    public World() {
        db.notices.add(new PrivacyNotice(ids.next(), 1, "metin", "text", clock.now()));
        FakeProjects projects = new FakeProjects(db);
        FakeConsents consents = new FakeConsents(db);
        FakeNotices notices = new FakeNotices(db);
        FakeProfiles profiles = new FakeProfiles(db);
        FakeScans scans = new FakeScans(db);
        FakeSourceFiles sourceFiles = new FakeSourceFiles(db);
        FakeFindings findings = new FakeFindings(db);
        FakeTopologies topologies = new FakeTopologies(db);
        FakeArtifacts artifacts = new FakeArtifacts(db);
        FakeClarifications clarifications = new FakeClarifications(db);
        FakePlans plans = new FakePlans(db);
        FakeOutbox outbox = new FakeOutbox(db);
        FakeIdempotency idempotencyStore = new FakeIdempotency(db);

        AuditRecorder audit = new AuditRecorder(auditLog, clock, ids);
        EventRecorder events = new EventRecorder(outbox, new PassThroughAnonymizer(), clock, ids);
        ConsentGate gate = new ConsentGate(consents);
        IdempotentExecutor idempotency = new IdempotentExecutor(idempotencyStore, clock);
        ScanAccess access = new ScanAccess(scans, projects, scans, gate);
        SourceFileResolver resolver = new SourceFileResolver(sourceFiles, sourceFiles, ids);
        StrategyRegistry registry = new StrategyRegistry(List.of(
                new FixWeakClassicStrategy(), new HybridTlsKexStrategy(), new DeviceHybridTlsStrategy(), new KemDemEncryptionStrategy(),
                new PqSignatureStrategy(), new KeepShortLivedTokenStrategy(), new HybridKexClassicCertStrategy(), new JdkUpgradeStrategy()));
        StrategyPlanner planner = new StrategyPlanner(registry, new JdkRequirementPolicy(), new EffortPolicy());
        FindingValidator validator = new FindingValidator(new PriorityPolicy(new PriorityClassifier()), registry);

        registerProject = new RegisterProjectService(tx, new Sha256ProjectKeyHasher(), projects, projects, idempotency, audit, clock, ids);
        getProject = new GetProjectService(tx, projects, profiles);
        listProjects = new ListProjectsService(projects);
        recordRuntimeProfile = new RecordRuntimeProfileService(tx, projects, gate, profiles, profiles, events, idempotency, audit, clock);
        deleteProject = new DeleteProjectService(tx, projects, consents, projects, outbox, events, audit);
        getPrivacyNotice = new GetPrivacyNoticeService(notices);
        grantConsent = new GrantConsentService(tx, projects, consents, consents, notices, idempotency, audit, clock, ids);
        revokeConsent = new RevokeConsentService(tx, projects, consents, consents, outbox, events, audit, clock);
        getConsents = new GetConsentsService(tx, projects, consents);
        startScan = new StartScanService(tx, projects, profiles, scans, scans, idempotency, audit, clock, ids);
        listScans = new ListScansService(tx, projects, scans);
        recordFindings = new RecordFindingsService(tx, access, resolver, findings, findings, validator, events, idempotency, audit, ids);
        recordTopology = new RecordTopologyService(
                tx, access, resolver, sourceFiles, findings, topologies, topologies, events, audit, clock, ids);
        recordScanArtifact = new RecordScanArtifactService(tx, access, artifacts, audit, clock);
        getScanArtifact = new GetScanArtifactService(artifacts);
        completeScan = new CompleteScanService(tx, access, scans, scans, findings, profiles, events, idempotency, audit, clock);
        getScanSummary = new GetScanSummaryService(tx, scans, profiles, findings);
        listFindings = new ListFindingsService(tx, scans, findings);
        getFinding = new GetFindingService(findings);
        getTopology = new GetTopologyService(tx, topologies, sourceFiles);
        saveClarificationAnswers = new SaveClarificationAnswersService(tx, projects, clarifications, clarifications, profiles, audit, clock);
        getProjectProfile = new GetProjectProfileService(tx, projects, profiles, clarifications);
        createPlan = new CreatePlanService(tx, access, findings, findings, profiles, planner, plans, plans, events, idempotency, audit, clock, ids);
        getPlan = new GetPlanService(tx, scans, plans, plans);
        transitionPlanItem = new TransitionPlanItemService(tx, projects, gate, plans, plans, plans, events, idempotency, audit, clock, ids);
        getPlanReport = new GetPlanReportService(tx, scans, plans, findings, findings, profiles, plans, planner);
        getAuditLog = new GetAuditLogService(auditLog);
        relayOutboxEvents = new RelayOutboxEventsService(tx, outbox, publisher, idempotencyStore, audit, clock);
    }

    // ------------------------------------------------------------------ scenario helpers

    public static Optional<Idempotency> idem(String key, String digest) {
        return Optional.of(new Idempotency(key, digest));
    }

    public UUID project() {
        return registerProject.execute(new RegisterProjectCommand("/work/demo", "Demo", Optional.empty(), "UI")).id();
    }

    public UUID projectWithWarehouseConsent() {
        UUID projectId = project();
        grantConsent.execute(new GrantConsentCommand(projectId, "WAREHOUSE_ANALYTICS", 1, Optional.empty(), Optional.empty(), "UI"));
        return projectId;
    }

    public UUID runningScan(UUID projectId) {
        return startScan.execute(new StartScanCommand(projectId, Optional.empty(), "UI")).id();
    }

    public static FindingInput finding(String path, String symbol, String algorithm, String usage, String kind, String priority, Integer keySize) {
        return new FindingInput(path, symbol, algorithm, usage, kind, priority, Optional.ofNullable(keySize), Optional.empty(), Optional.empty(), 0.9, "STATIC");
    }

    public static FindingInput tlsFinding(String path, String symbol) {
        return finding(path, symbol, "RSA", "TLS_KEY_EXCHANGE", "CODE", "P1", 2048);
    }

    public RecordFindingsResult record(UUID scanId, FindingInput... findings) {
        return recordFindings.execute(new RecordFindingsCommand(scanId, List.of(findings), Optional.empty(), "UI"));
    }

    public ScanView complete(UUID scanId) {
        return completeScan.execute(new CompleteScanCommand(scanId, "COMPLETED", Optional.empty(), "UI"));
    }

    public List<PlanItemInput> assessAll(UUID scanId, double score) {
        return db.findings.values().stream()
                .filter(f -> db.sourceFiles.get(f.sourceFileId()).scanId().equals(scanId))
                .map(f -> new PlanItemInput(f.id(), score, List.of(new RiskFactorInput("algorithm_weakness", new BigDecimal("0.4")))))
                .toList();
    }

    public PlanView plan(UUID scanId, double score) {
        return createPlan.execute(new CreatePlanCommand(scanId, assessAll(scanId, score), Optional.empty(), "UI"));
    }

    public List<OutboxRecord> outbox() {
        return List.copyOf(db.outbox);
    }

    public List<EventType> outboxTypes() {
        return db.outbox.stream().map(OutboxRecord::type).toList();
    }

    public List<AuditAction> auditActions() {
        return db.audit.stream().map(AuditEntry::action).toList();
    }
}

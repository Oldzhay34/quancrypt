package com.quancrypt.core.infrastructure.config;

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
import com.quancrypt.core.port.inbound.CompleteScanUseCase;
import com.quancrypt.core.port.inbound.CreatePlanUseCase;
import com.quancrypt.core.port.inbound.DeleteProjectUseCase;
import com.quancrypt.core.port.inbound.GetAuditLogUseCase;
import com.quancrypt.core.port.inbound.GetConsentsUseCase;
import com.quancrypt.core.port.inbound.GetFindingUseCase;
import com.quancrypt.core.port.inbound.GetPlanReportUseCase;
import com.quancrypt.core.port.inbound.GetPlanUseCase;
import com.quancrypt.core.port.inbound.GetPrivacyNoticeUseCase;
import com.quancrypt.core.port.inbound.GetProjectProfileUseCase;
import com.quancrypt.core.port.inbound.GetProjectUseCase;
import com.quancrypt.core.port.inbound.GetScanArtifactUseCase;
import com.quancrypt.core.port.inbound.GetScanSummaryUseCase;
import com.quancrypt.core.port.inbound.GetTopologyUseCase;
import com.quancrypt.core.port.inbound.GrantConsentUseCase;
import com.quancrypt.core.port.inbound.ListFindingsUseCase;
import com.quancrypt.core.port.inbound.ListProjectsUseCase;
import com.quancrypt.core.port.inbound.ListScansUseCase;
import com.quancrypt.core.port.inbound.RecordFindingsUseCase;
import com.quancrypt.core.port.inbound.RecordRuntimeProfileUseCase;
import com.quancrypt.core.port.inbound.RecordScanArtifactUseCase;
import com.quancrypt.core.port.inbound.RecordTopologyUseCase;
import com.quancrypt.core.port.inbound.RegisterProjectUseCase;
import com.quancrypt.core.port.inbound.RelayOutboxEventsUseCase;
import com.quancrypt.core.port.inbound.RevokeConsentUseCase;
import com.quancrypt.core.port.inbound.SaveClarificationAnswersUseCase;
import com.quancrypt.core.port.inbound.StartScanUseCase;
import com.quancrypt.core.port.inbound.TransitionPlanItemUseCase;
import com.quancrypt.core.port.outbound.AuditLogReader;
import com.quancrypt.core.port.outbound.AuditLogWriter;
import com.quancrypt.core.port.outbound.ClarificationReader;
import com.quancrypt.core.port.outbound.ClarificationWriter;
import com.quancrypt.core.port.outbound.Clock;
import com.quancrypt.core.port.outbound.ConsentLock;
import com.quancrypt.core.port.outbound.ConsentReader;
import com.quancrypt.core.port.outbound.ConsentWriter;
import com.quancrypt.core.port.outbound.EventAnonymizer;
import com.quancrypt.core.port.outbound.EventPublisher;
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
import com.quancrypt.core.port.outbound.ProjectKeyHasher;
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
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Composition root of the domain services, use case helpers and the 28 use cases (D-137); the wiring mirrors the unit
 * test fixture. The class is longer than the usual 200 lines (solid-checklist S) because it holds one bean method per use
 * case and nothing else: no logic, one reason to change (how the use cases are wired). Splitting it by group would only
 * spread the same constructor calls over more files.
 */
@Configuration(proxyBeanMethods = false)
public class UseCaseConfig {

    // ------------------------------------------------------------------ domain services

    @Bean
    StrategyRegistry strategyRegistry() {
        return new StrategyRegistry(List.of(
                new FixWeakClassicStrategy(), new HybridTlsKexStrategy(), new DeviceHybridTlsStrategy(), new KemDemEncryptionStrategy(),
                new PqSignatureStrategy(), new KeepShortLivedTokenStrategy(), new HybridKexClassicCertStrategy(), new JdkUpgradeStrategy()));
    }

    @Bean
    StrategyPlanner strategyPlanner(StrategyRegistry registry) {
        return new StrategyPlanner(registry, new JdkRequirementPolicy(), new EffortPolicy());
    }

    @Bean
    FindingValidator findingValidator(StrategyRegistry registry) {
        return new FindingValidator(new PriorityPolicy(new PriorityClassifier()), registry);
    }

    // ------------------------------------------------------------------ use case helpers

    @Bean
    AuditRecorder auditRecorder(AuditLogWriter writer, Clock clock, IdGenerator ids) {
        return new AuditRecorder(writer, clock, ids);
    }

    @Bean
    EventRecorder eventRecorder(OutboxWriter outbox, EventAnonymizer anonymizer, Clock clock, IdGenerator ids) {
        return new EventRecorder(outbox, anonymizer, clock, ids);
    }

    @Bean
    ConsentGate consentGate(ConsentLock consentLock) {
        return new ConsentGate(consentLock);
    }

    @Bean
    IdempotentExecutor idempotentExecutor(IdempotencyStore store, Clock clock) {
        return new IdempotentExecutor(store, clock);
    }

    @Bean
    ScanAccess scanAccess(ScanReader scans, ProjectLock projectLock, ScanLock scanLock, ConsentGate gate) {
        return new ScanAccess(scans, projectLock, scanLock, gate);
    }

    @Bean
    SourceFileResolver sourceFileResolver(SourceFileReader reader, SourceFileWriter writer, IdGenerator ids) {
        return new SourceFileResolver(reader, writer, ids);
    }

    // ------------------------------------------------------------------ project

    @Bean
    RegisterProjectUseCase registerProject(TransactionRunner tx, ProjectKeyHasher hasher, ProjectReader reader, ProjectWriter writer,
                                           IdempotentExecutor idempotency, AuditRecorder audit, Clock clock, IdGenerator ids) {
        return new RegisterProjectService(tx, hasher, reader, writer, idempotency, audit, clock, ids);
    }

    @Bean
    GetProjectUseCase getProject(TransactionRunner tx, ProjectReader projects, RuntimeProfileReader profiles) {
        return new GetProjectService(tx, projects, profiles);
    }

    @Bean
    ListProjectsUseCase listProjects(ProjectReader projects) {
        return new ListProjectsService(projects);
    }

    @Bean
    RecordRuntimeProfileUseCase recordRuntimeProfile(TransactionRunner tx, ProjectLock lock, ConsentGate gate, RuntimeProfileReader reader,
                                                     RuntimeProfileWriter writer, EventRecorder events, IdempotentExecutor idempotency,
                                                     AuditRecorder audit, Clock clock) {
        return new RecordRuntimeProfileService(tx, lock, gate, reader, writer, events, idempotency, audit, clock);
    }

    @Bean
    DeleteProjectUseCase deleteProject(TransactionRunner tx, ProjectLock projectLock, ConsentLock consentLock, ProjectWriter writer,
                                       OutboxWriter outbox, EventRecorder events, AuditRecorder audit) {
        return new DeleteProjectService(tx, projectLock, consentLock, writer, outbox, events, audit);
    }

    // ------------------------------------------------------------------ consent

    @Bean
    GetPrivacyNoticeUseCase getPrivacyNotice(PrivacyNoticeReader notices) {
        return new GetPrivacyNoticeService(notices);
    }

    @Bean
    GrantConsentUseCase grantConsent(TransactionRunner tx, ProjectLock lock, ConsentReader reader, ConsentWriter writer,
                                     PrivacyNoticeReader notices, IdempotentExecutor idempotency, AuditRecorder audit, Clock clock,
                                     IdGenerator ids) {
        return new GrantConsentService(tx, lock, reader, writer, notices, idempotency, audit, clock, ids);
    }

    @Bean
    RevokeConsentUseCase revokeConsent(TransactionRunner tx, ProjectLock lock, ConsentReader reader, ConsentWriter writer,
                                       OutboxWriter outbox, EventRecorder events, AuditRecorder audit, Clock clock) {
        return new RevokeConsentService(tx, lock, reader, writer, outbox, events, audit, clock);
    }

    @Bean
    GetConsentsUseCase getConsents(TransactionRunner tx, ProjectReader projects, ConsentReader consents) {
        return new GetConsentsService(tx, projects, consents);
    }

    // ------------------------------------------------------------------ scan

    @Bean
    StartScanUseCase startScan(TransactionRunner tx, ProjectLock lock, RuntimeProfileReader profiles, ScanReader reader, ScanWriter writer,
                               IdempotentExecutor idempotency, AuditRecorder audit, Clock clock, IdGenerator ids) {
        return new StartScanService(tx, lock, profiles, reader, writer, idempotency, audit, clock, ids);
    }

    @Bean
    ListScansUseCase listScans(TransactionRunner tx, ProjectReader projects, ScanReader scans) {
        return new ListScansService(tx, projects, scans);
    }

    @Bean
    RecordFindingsUseCase recordFindings(TransactionRunner tx, ScanAccess access, SourceFileResolver files, FindingReader reader,
                                         FindingWriter writer, FindingValidator validator, EventRecorder events,
                                         IdempotentExecutor idempotency, AuditRecorder audit, IdGenerator ids) {
        return new RecordFindingsService(tx, access, files, reader, writer, validator, events, idempotency, audit, ids);
    }

    @Bean
    RecordTopologyUseCase recordTopology(TransactionRunner tx, ScanAccess access, SourceFileResolver resolver, SourceFileWriter files,
                                         FindingReader findings, TopologyReader reader, TopologyWriter writer, EventRecorder events,
                                         AuditRecorder audit, Clock clock, IdGenerator ids) {
        return new RecordTopologyService(tx, access, resolver, files, findings, reader, writer, events, audit, clock, ids);
    }

    @Bean
    RecordScanArtifactUseCase recordScanArtifact(TransactionRunner tx, ScanAccess access, ScanArtifactWriter writer, AuditRecorder audit,
                                                 Clock clock) {
        return new RecordScanArtifactService(tx, access, writer, audit, clock);
    }

    @Bean
    GetScanArtifactUseCase getScanArtifact(ScanArtifactReader artifacts) {
        return new GetScanArtifactService(artifacts);
    }

    @Bean
    CompleteScanUseCase completeScan(TransactionRunner tx, ScanAccess access, ScanReader reader, ScanWriter writer, FindingReader findings,
                                     RuntimeProfileReader profiles, EventRecorder events, IdempotentExecutor idempotency,
                                     AuditRecorder audit, Clock clock) {
        return new CompleteScanService(tx, access, reader, writer, findings, profiles, events, idempotency, audit, clock);
    }

    @Bean
    GetScanSummaryUseCase getScanSummary(TransactionRunner tx, ScanReader scans, RuntimeProfileReader profiles, FindingReader findings) {
        return new GetScanSummaryService(tx, scans, profiles, findings);
    }

    @Bean
    ListFindingsUseCase listFindings(TransactionRunner tx, ScanReader scans, FindingReader findings) {
        return new ListFindingsService(tx, scans, findings);
    }

    @Bean
    GetFindingUseCase getFinding(FindingReader findings) {
        return new GetFindingService(findings);
    }

    @Bean
    GetTopologyUseCase getTopology(TransactionRunner tx, TopologyReader topologies, SourceFileReader files) {
        return new GetTopologyService(tx, topologies, files);
    }

    // ------------------------------------------------------------------ profile

    @Bean
    SaveClarificationAnswersUseCase saveClarificationAnswers(TransactionRunner tx, ProjectLock lock, ClarificationReader reader,
                                                             ClarificationWriter writer, RuntimeProfileReader profiles, AuditRecorder audit,
                                                             Clock clock) {
        return new SaveClarificationAnswersService(tx, lock, reader, writer, profiles, audit, clock);
    }

    @Bean
    GetProjectProfileUseCase getProjectProfile(TransactionRunner tx, ProjectReader projects, RuntimeProfileReader profiles,
                                               ClarificationReader answers) {
        return new GetProjectProfileService(tx, projects, profiles, answers);
    }

    // ------------------------------------------------------------------ plan

    @Bean
    CreatePlanUseCase createPlan(TransactionRunner tx, ScanAccess access, FindingReader findings, PlanningContextReader contexts,
                                 RuntimeProfileReader profiles, StrategyPlanner planner, PlanReader reader, PlanWriter writer,
                                 EventRecorder events, IdempotentExecutor idempotency, AuditRecorder audit, Clock clock, IdGenerator ids) {
        return new CreatePlanService(tx, access, findings, contexts, profiles, planner, reader, writer, events, idempotency, audit, clock, ids);
    }

    @Bean
    GetPlanUseCase getPlan(TransactionRunner tx, ScanReader scans, PlanReader plans, RiskThresholdReader thresholds) {
        return new GetPlanService(tx, scans, plans, thresholds);
    }

    @Bean
    TransitionPlanItemUseCase transitionPlanItem(TransactionRunner tx, ProjectLock lock, ConsentGate gate, PlanReader reader, PlanWriter writer,
                                                 RiskThresholdReader thresholds, EventRecorder events, IdempotentExecutor idempotency,
                                                 AuditRecorder audit, Clock clock, IdGenerator ids) {
        return new TransitionPlanItemService(tx, lock, gate, reader, writer, thresholds, events, idempotency, audit, clock, ids);
    }

    @Bean
    GetPlanReportUseCase getPlanReport(TransactionRunner tx, ScanReader scans, PlanReader plans, FindingReader findings,
                                       PlanningContextReader contexts, RuntimeProfileReader profiles, ClarificationReader answers,
                                       RiskThresholdReader thresholds, StrategyPlanner planner) {
        return new GetPlanReportService(tx, scans, plans, findings, contexts, profiles, answers, thresholds, planner);
    }

    // ------------------------------------------------------------------ audit and events

    @Bean
    GetAuditLogUseCase getAuditLog(AuditLogReader audit) {
        return new GetAuditLogService(audit);
    }

    @Bean
    RelayOutboxEventsUseCase relayOutboxEvents(TransactionRunner tx, OutboxRelayRepository relay, EventPublisher publisher,
                                               IdempotencyStore idempotencyStore, AuditRecorder audit, Clock clock) {
        return new RelayOutboxEventsService(tx, relay, publisher, idempotencyStore, audit, clock);
    }
}

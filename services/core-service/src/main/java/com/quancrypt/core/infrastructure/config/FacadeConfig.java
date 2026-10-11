package com.quancrypt.core.infrastructure.config;

import com.quancrypt.core.api.TraceIdFilter;
import com.quancrypt.core.facade.AuditFacade;
import com.quancrypt.core.facade.OutboxRelayFacade;
import com.quancrypt.core.facade.PlanFacade;
import com.quancrypt.core.facade.ProjectFacade;
import com.quancrypt.core.facade.ScanFacade;
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
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;

/** The facades the driving adapters (controllers, the relay trigger) use, and the trace id filter in front of the security chain. */
@Configuration(proxyBeanMethods = false)
public class FacadeConfig {

    @Bean
    ProjectFacade projectFacade(
            RegisterProjectUseCase registerProject, ListProjectsUseCase listProjects, GetProjectUseCase getProject,
            DeleteProjectUseCase deleteProject, RecordRuntimeProfileUseCase recordRuntimeProfile, GetPrivacyNoticeUseCase getPrivacyNotice,
            GrantConsentUseCase grantConsent, RevokeConsentUseCase revokeConsent, GetConsentsUseCase getConsents,
            SaveClarificationAnswersUseCase saveClarificationAnswers, GetProjectProfileUseCase getProjectProfile) {
        return new ProjectFacade(registerProject, listProjects, getProject, deleteProject, recordRuntimeProfile, getPrivacyNotice, grantConsent,
                revokeConsent, getConsents, saveClarificationAnswers, getProjectProfile);
    }

    @Bean
    ScanFacade scanFacade(
            StartScanUseCase startScan, ListScansUseCase listScans, RecordFindingsUseCase recordFindings, ListFindingsUseCase listFindings,
            GetFindingUseCase getFinding, RecordTopologyUseCase recordTopology, GetTopologyUseCase getTopology,
            RecordScanArtifactUseCase recordScanArtifact, GetScanArtifactUseCase getScanArtifact, CompleteScanUseCase completeScan,
            GetScanSummaryUseCase getScanSummary) {
        return new ScanFacade(startScan, listScans, recordFindings, listFindings, getFinding, recordTopology, getTopology, recordScanArtifact,
                getScanArtifact, completeScan, getScanSummary);
    }

    @Bean
    PlanFacade planFacade(
            CreatePlanUseCase createPlan, GetPlanUseCase getPlan, TransitionPlanItemUseCase transitionPlanItem,
            GetPlanReportUseCase getPlanReport) {
        return new PlanFacade(createPlan, getPlan, transitionPlanItem, getPlanReport);
    }

    @Bean
    AuditFacade auditFacade(GetAuditLogUseCase getAuditLog) {
        return new AuditFacade(getAuditLog);
    }

    @Bean
    OutboxRelayFacade outboxRelayFacade(RelayOutboxEventsUseCase relay) {
        return new OutboxRelayFacade(relay);
    }

    /** Runs before everything else, so that even a 401 answer carries X-Trace-Id. */
    @Bean
    FilterRegistrationBean<TraceIdFilter> traceIdFilter() {
        FilterRegistrationBean<TraceIdFilter> registration = new FilterRegistrationBean<>(new TraceIdFilter());
        registration.setOrder(Ordered.HIGHEST_PRECEDENCE);
        return registration;
    }
}

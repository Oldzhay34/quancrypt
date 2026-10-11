package com.quancrypt.core.facade;

import com.quancrypt.core.facade.dto.AuditEntryDto;
import com.quancrypt.core.facade.dto.CallSiteDto;
import com.quancrypt.core.facade.dto.ClarificationAnswerDto;
import com.quancrypt.core.facade.dto.ConsentDto;
import com.quancrypt.core.facade.dto.FindingBatchResultDto;
import com.quancrypt.core.facade.dto.FindingDto;
import com.quancrypt.core.facade.dto.LinkDto;
import com.quancrypt.core.facade.dto.NodeDto;
import com.quancrypt.core.facade.dto.PageDto;
import com.quancrypt.core.facade.dto.PlanDto;
import com.quancrypt.core.facade.dto.PlanItemDto;
import com.quancrypt.core.facade.dto.PrivacyNoticeDto;
import com.quancrypt.core.facade.dto.ProjectDto;
import com.quancrypt.core.facade.dto.RiskFactorDto;
import com.quancrypt.core.facade.dto.RuntimeProfileDto;
import com.quancrypt.core.facade.dto.ScanArtifactDto;
import com.quancrypt.core.facade.dto.ScanDto;
import com.quancrypt.core.facade.dto.TopologyDto;
import com.quancrypt.core.port.inbound.view.AuditEntryView;
import com.quancrypt.core.port.inbound.view.CallSiteView;
import com.quancrypt.core.port.inbound.view.ClarificationAnswerView;
import com.quancrypt.core.port.inbound.view.ConsentView;
import com.quancrypt.core.port.inbound.view.FindingView;
import com.quancrypt.core.port.inbound.view.LinkView;
import com.quancrypt.core.port.inbound.view.NodeView;
import com.quancrypt.core.port.inbound.view.PageView;
import com.quancrypt.core.port.inbound.view.PlanItemView;
import com.quancrypt.core.port.inbound.view.PlanView;
import com.quancrypt.core.port.inbound.view.PrivacyNoticeView;
import com.quancrypt.core.port.inbound.view.ProjectView;
import com.quancrypt.core.port.inbound.view.RecordFindingsResult;
import com.quancrypt.core.port.inbound.view.RiskFactorView;
import com.quancrypt.core.port.inbound.view.RuntimeProfileView;
import com.quancrypt.core.port.inbound.view.ScanArtifactView;
import com.quancrypt.core.port.inbound.view.ScanView;
import com.quancrypt.core.port.inbound.view.TopologyView;
import java.util.List;
import java.util.Optional;
import java.util.function.Function;

/** Maps the use case views to the facade DTOs, which mirror the schemas of the contract (optional values become null). */
final class FacadeMapper {

    private FacadeMapper() {
    }

    static <A, B> PageDto<B> page(PageView<A> page, Function<A, B> item) {
        return new PageDto<>(page.items().stream().map(item).toList(), page.page(), page.size(), page.total());
    }

    static ProjectDto project(ProjectView v) {
        return new ProjectDto(v.id(), v.projectKey(), v.displayName(), v.createdAt());
    }

    static RuntimeProfileDto runtimeProfile(RuntimeProfileView v) {
        return new RuntimeProfileDto(v.sequenceNo(), v.javaVersion(), v.springBootVersion().orElse(null), v.recordedAt());
    }

    static RuntimeProfileDto runtimeProfile(Optional<RuntimeProfileView> v) {
        return v.map(FacadeMapper::runtimeProfile).orElse(null);
    }

    static PrivacyNoticeDto notice(PrivacyNoticeView v) {
        return new PrivacyNoticeDto(v.version(), v.textTr(), v.textEn(), v.publishedAt());
    }

    static ConsentDto consent(ConsentView v) {
        return new ConsentDto(v.consentType(), v.privacyNoticeVersion(), v.grantedAt(), v.revokedAt().orElse(null), v.version());
    }

    static ScanDto scan(ScanView v) {
        return new ScanDto(v.id(), v.projectId(), v.status(), v.startedAt(), v.completedAt().orElse(null),
                v.runtimeProfileSequenceNo().orElse(null));
    }

    static FindingBatchResultDto findingBatch(RecordFindingsResult v) {
        return new FindingBatchResultDto(v.createdCount(), v.existingCount(), v.createdIds());
    }

    static FindingDto finding(FindingView v) {
        return new FindingDto(v.id(), v.scanId(), v.path(), v.symbol(), v.algorithmFamily(), v.usageContext(), v.locationKind(),
                v.priority(), v.keySizeBits().orElse(null), v.lineStart().orElse(null), v.lineEnd().orElse(null), v.confidence(),
                v.classifiedBy());
    }

    static TopologyDto topology(TopologyView v) {
        return new TopologyDto(v.scanId(), v.recordedAt(), v.nodes().stream().map(FacadeMapper::node).toList(),
                v.links().stream().map(FacadeMapper::link).toList());
    }

    private static NodeDto node(NodeView v) {
        return new NodeDto(v.name(), v.nodeKind());
    }

    private static LinkDto link(LinkView v) {
        return new LinkDto(v.source(), v.target(), v.protocol(), v.tls(), v.mtls(), v.callSites().stream().map(FacadeMapper::callSite).toList(),
                v.findingIds());
    }

    private static CallSiteDto callSite(CallSiteView v) {
        return new CallSiteDto(v.path(), v.lineStart(), v.lineEnd(), v.locationKind());
    }

    static ScanArtifactDto artifact(ScanArtifactView v) {
        return new ScanArtifactDto(v.scanId(), v.contentType(), v.sha256(), v.createdAt());
    }

    static ClarificationAnswerDto answer(ClarificationAnswerView v) {
        return new ClarificationAnswerDto(v.questionCode(), v.optionCode().orElse(null), v.freeText().orElse(null));
    }

    static List<ClarificationAnswerDto> answers(List<ClarificationAnswerView> views) {
        return views.stream().map(FacadeMapper::answer).toList();
    }

    static PlanDto plan(PlanView v) {
        return new PlanDto(v.id(), v.scanId(), v.createdAt(), v.itemCount());
    }

    static PlanItemDto planItem(PlanItemView v) {
        return new PlanItemDto(v.id(), v.findingId(), v.strategy(), v.effort(), v.riskScore(), v.riskClass(), v.state(), v.version(),
                v.riskFactors().stream().map(FacadeMapper::riskFactor).toList());
    }

    static RiskFactorDto riskFactor(RiskFactorView v) {
        return new RiskFactorDto(v.featureName(), v.shapValue());
    }

    static AuditEntryDto audit(AuditEntryView v) {
        return new AuditEntryDto(v.id(), v.occurredAt(), v.action(), v.projectKey().orElse(null), v.subjectId().orElse(null), v.callerKind());
    }
}

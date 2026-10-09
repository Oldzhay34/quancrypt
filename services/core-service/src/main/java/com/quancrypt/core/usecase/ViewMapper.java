package com.quancrypt.core.usecase;

import com.quancrypt.core.domain.model.AuditEntry;
import com.quancrypt.core.domain.model.ClarificationAnswer;
import com.quancrypt.core.domain.model.Consent;
import com.quancrypt.core.domain.model.Finding;
import com.quancrypt.core.domain.model.FindingDetail;
import com.quancrypt.core.domain.model.PageResult;
import com.quancrypt.core.domain.model.Plan;
import com.quancrypt.core.domain.model.PlanItem;
import com.quancrypt.core.domain.model.Project;
import com.quancrypt.core.domain.model.ProjectKey;
import com.quancrypt.core.domain.model.RuntimeProfile;
import com.quancrypt.core.domain.model.Scan;
import com.quancrypt.core.domain.model.ServiceNode;
import com.quancrypt.core.domain.model.SourceFile;
import com.quancrypt.core.domain.model.Topology;
import com.quancrypt.core.domain.policy.RiskClassPolicy;
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
import com.quancrypt.core.port.inbound.view.ProjectView;
import com.quancrypt.core.port.inbound.view.RiskFactorView;
import com.quancrypt.core.port.inbound.view.RuntimeProfileView;
import com.quancrypt.core.port.inbound.view.ScanView;
import com.quancrypt.core.port.inbound.view.TopologyView;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.function.Function;
import java.util.stream.Collectors;

/** Maps domain objects to the coded views use cases return; the facade never sees the domain. */
final class ViewMapper {

    private ViewMapper() {
    }

    static ProjectView project(Project project, boolean created) {
        return new ProjectView(project.id(), project.key().value(), project.displayName(), project.createdAt(), created);
    }

    static RuntimeProfileView runtimeProfile(RuntimeProfile profile, boolean created) {
        return new RuntimeProfileView(profile.sequenceNo(), profile.javaVersion(), profile.springBootVersion(), profile.recordedAt(), created);
    }

    static ConsentView consent(Consent consent, boolean created) {
        return new ConsentView(consent.type().name(), consent.privacyNoticeVersion(), consent.grantedAt(), consent.revokedAt(), consent.version(), created);
    }

    static ScanView scan(Scan scan) {
        return new ScanView(scan.id(), scan.projectId(), scan.status().name(), scan.startedAt(), scan.completedAt(), scan.runtimeProfileSequenceNo());
    }

    static FindingView finding(FindingDetail detail) {
        Finding f = detail.finding();
        SourceFile file = detail.file();
        return new FindingView(f.id(), file.scanId(), file.path(), f.symbol(), f.algorithm().name(), f.usage().name(), file.locationKind().name(),
                f.priority().name(), f.keySizeBits(), f.lineStart(), f.lineEnd(), f.confidence(), f.classifiedBy().name());
    }

    static PlanView plan(Plan plan, int itemCount) {
        return new PlanView(plan.id(), plan.scanId(), plan.createdAt(), itemCount);
    }

    static List<RiskFactorView> riskFactors(PlanItem item) {
        return item.riskFactors().stream().map(r -> new RiskFactorView(r.rank(), r.featureName(), r.shapValue())).toList();
    }

    static PlanItemView planItem(PlanItem item, RiskClassPolicy policy) {
        return new PlanItemView(item.id(), item.findingId(), item.strategy().name(), item.effort().name(), item.riskScore().value(),
                policy.classify(item.riskScore()).name(), item.state().code().name(), item.version(), riskFactors(item));
    }

    static AuditEntryView audit(AuditEntry entry) {
        return new AuditEntryView(entry.id(), entry.occurredAt(), entry.action().name(), entry.projectKey().map(ProjectKey::value),
                entry.subjectId(), entry.caller().name());
    }

    static ClarificationAnswerView answer(ClarificationAnswer answer) {
        return new ClarificationAnswerView(answer.question().name(), answer.option(), answer.freeText());
    }

    static <T, R> PageView<R> page(PageResult<T> page, Function<T, R> mapper) {
        return new PageView<>(page.items().stream().map(mapper).toList(), page.page(), page.size(), page.total());
    }

    static TopologyView topology(Topology topology, Map<UUID, SourceFile> files) {
        Map<UUID, String> names = topology.nodes().stream().collect(Collectors.toMap(ServiceNode::id, ServiceNode::name));
        List<NodeView> nodes = topology.nodes().stream().map(n -> new NodeView(n.name(), n.kind().name())).toList();
        List<LinkView> links = topology.links().stream().map(link -> new LinkView(
                names.get(link.sourceNodeId()),
                names.get(link.targetNodeId()),
                link.protocol().name(),
                link.tls(),
                link.mtls(),
                link.callSites().stream().map(cs -> {
                    SourceFile file = files.get(cs.sourceFileId());
                    return new CallSiteView(file.path(), cs.lineStart(), cs.lineEnd(), file.locationKind().name());
                }).toList(),
                link.findingIds().stream().sorted(Comparator.comparing(UUID::toString)).toList())).toList();
        return new TopologyView(topology.scanId(), topology.recordedAt(), nodes, links);
    }
}

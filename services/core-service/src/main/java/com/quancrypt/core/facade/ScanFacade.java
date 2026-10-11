package com.quancrypt.core.facade;

import com.quancrypt.core.facade.dto.ArtifactContent;
import com.quancrypt.core.facade.dto.FindingBatchInput;
import com.quancrypt.core.facade.dto.FindingBatchResultDto;
import com.quancrypt.core.facade.dto.FindingDto;
import com.quancrypt.core.facade.dto.PageDto;
import com.quancrypt.core.facade.dto.ScanArtifactDto;
import com.quancrypt.core.facade.dto.ScanCompletionInput;
import com.quancrypt.core.facade.dto.ScanDto;
import com.quancrypt.core.facade.dto.ScanSummaryDto;
import com.quancrypt.core.facade.dto.TopologyDto;
import com.quancrypt.core.facade.dto.TopologyInput;
import com.quancrypt.core.port.inbound.CallSiteInput;
import com.quancrypt.core.port.inbound.CompleteScanCommand;
import com.quancrypt.core.port.inbound.CompleteScanUseCase;
import com.quancrypt.core.port.inbound.FindingInput;
import com.quancrypt.core.port.inbound.GetFindingQuery;
import com.quancrypt.core.port.inbound.GetFindingUseCase;
import com.quancrypt.core.port.inbound.GetScanArtifactQuery;
import com.quancrypt.core.port.inbound.GetScanArtifactUseCase;
import com.quancrypt.core.port.inbound.GetScanSummaryQuery;
import com.quancrypt.core.port.inbound.GetScanSummaryUseCase;
import com.quancrypt.core.port.inbound.GetTopologyQuery;
import com.quancrypt.core.port.inbound.GetTopologyUseCase;
import com.quancrypt.core.port.inbound.LinkInput;
import com.quancrypt.core.port.inbound.ListFindingsQuery;
import com.quancrypt.core.port.inbound.ListFindingsUseCase;
import com.quancrypt.core.port.inbound.ListScansQuery;
import com.quancrypt.core.port.inbound.ListScansUseCase;
import com.quancrypt.core.port.inbound.NodeInput;
import com.quancrypt.core.port.inbound.RecordFindingsCommand;
import com.quancrypt.core.port.inbound.RecordFindingsUseCase;
import com.quancrypt.core.port.inbound.RecordScanArtifactCommand;
import com.quancrypt.core.port.inbound.RecordScanArtifactUseCase;
import com.quancrypt.core.port.inbound.RecordTopologyCommand;
import com.quancrypt.core.port.inbound.RecordTopologyUseCase;
import com.quancrypt.core.port.inbound.StartScanCommand;
import com.quancrypt.core.port.inbound.StartScanUseCase;
import com.quancrypt.core.port.inbound.view.ScanArtifactContentView;
import com.quancrypt.core.port.inbound.view.ScanSummaryView;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

/** Scans, findings, topology and the CBOM file of a scan. */
public final class ScanFacade {

    private final StartScanUseCase startScan;
    private final ListScansUseCase listScans;
    private final RecordFindingsUseCase recordFindings;
    private final ListFindingsUseCase listFindings;
    private final GetFindingUseCase getFinding;
    private final RecordTopologyUseCase recordTopology;
    private final GetTopologyUseCase getTopology;
    private final RecordScanArtifactUseCase recordScanArtifact;
    private final GetScanArtifactUseCase getScanArtifact;
    private final CompleteScanUseCase completeScan;
    private final GetScanSummaryUseCase getScanSummary;

    public ScanFacade(
            StartScanUseCase startScan, ListScansUseCase listScans, RecordFindingsUseCase recordFindings, ListFindingsUseCase listFindings,
            GetFindingUseCase getFinding, RecordTopologyUseCase recordTopology, GetTopologyUseCase getTopology,
            RecordScanArtifactUseCase recordScanArtifact, GetScanArtifactUseCase getScanArtifact, CompleteScanUseCase completeScan,
            GetScanSummaryUseCase getScanSummary) {
        this.startScan = startScan;
        this.listScans = listScans;
        this.recordFindings = recordFindings;
        this.listFindings = listFindings;
        this.getFinding = getFinding;
        this.recordTopology = recordTopology;
        this.getTopology = getTopology;
        this.recordScanArtifact = recordScanArtifact;
        this.getScanArtifact = getScanArtifact;
        this.completeScan = completeScan;
        this.getScanSummary = getScanSummary;
    }

    public ScanDto start(UUID projectId, Optional<String> idempotencyKey, String caller) {
        return ProblemTranslator.call(() -> FacadeMapper.scan(startScan.execute(new StartScanCommand(
                projectId, Idem.of(idempotencyKey, "POST", "/api/v1/projects/{projectId}/scans", null, projectId.toString()), caller))));
    }

    public PageDto<ScanDto> list(UUID projectId, int page, int size) {
        return ProblemTranslator.call(() -> FacadeMapper.page(listScans.execute(new ListScansQuery(projectId, page, size)), FacadeMapper::scan));
    }

    public FindingBatchResultDto recordFindings(UUID scanId, FindingBatchInput body, Optional<String> idempotencyKey, String caller) {
        return ProblemTranslator.call(() -> {
            List<FindingInput> findings = body.findings().stream()
                    .map(f -> new FindingInput(f.path(), f.symbol(), f.algorithmFamily(), f.usageContext(), f.locationKind(), f.priority(),
                            Optional.ofNullable(f.keySizeBits()), Optional.ofNullable(f.lineStart()), Optional.ofNullable(f.lineEnd()),
                            f.confidence(), f.classifiedBy()))
                    .toList();
            return FacadeMapper.findingBatch(recordFindings.execute(new RecordFindingsCommand(scanId, findings,
                    Idem.of(idempotencyKey, "POST", "/api/v1/scans/{scanId}/findings", body, scanId.toString()), caller)));
        });
    }

    /** Optional filters; a null filter is not applied. */
    public PageDto<FindingDto> findings(
            UUID scanId, String priority, String algorithmFamily, String usageContext, String locationKind, String classifiedBy,
            int page, int size) {
        return ProblemTranslator.call(() -> FacadeMapper.page(listFindings.execute(new ListFindingsQuery(scanId, Optional.ofNullable(priority),
                Optional.ofNullable(algorithmFamily), Optional.ofNullable(usageContext), Optional.ofNullable(locationKind),
                Optional.ofNullable(classifiedBy), page, size)), FacadeMapper::finding));
    }

    public FindingDto finding(UUID findingId) {
        return ProblemTranslator.call(() -> FacadeMapper.finding(getFinding.execute(new GetFindingQuery(findingId))));
    }

    public TopologyDto recordTopology(UUID scanId, TopologyInput body, String caller) {
        return ProblemTranslator.call(() -> {
            List<NodeInput> nodes = body.nodes().stream().map(n -> new NodeInput(n.name(), n.nodeKind())).toList();
            List<LinkInput> links = body.links().stream()
                    .map(l -> new LinkInput(l.source(), l.target(), l.protocol(), l.tls(), l.mtls(),
                            l.callSites().stream().map(c -> new CallSiteInput(c.path(), c.lineStart(), c.lineEnd(), c.locationKind())).toList(),
                            l.findingIds()))
                    .toList();
            return FacadeMapper.topology(recordTopology.execute(new RecordTopologyCommand(scanId, nodes, links, caller)));
        });
    }

    public TopologyDto topology(UUID scanId) {
        return ProblemTranslator.call(() -> FacadeMapper.topology(getTopology.execute(new GetTopologyQuery(scanId))));
    }

    public ScanArtifactDto recordArtifact(UUID scanId, String contentType, byte[] content, String caller) {
        return ProblemTranslator.call(() -> FacadeMapper.artifact(
                recordScanArtifact.execute(new RecordScanArtifactCommand(scanId, contentType, content, caller))));
    }

    public ArtifactContent artifact(UUID scanId) {
        return ProblemTranslator.call(() -> {
            ScanArtifactContentView view = getScanArtifact.execute(new GetScanArtifactQuery(scanId));
            return new ArtifactContent(view.contentType(), view.sha256(), view.content());
        });
    }

    public ScanDto complete(UUID scanId, ScanCompletionInput body, Optional<String> idempotencyKey, String caller) {
        return ProblemTranslator.call(() -> FacadeMapper.scan(completeScan.execute(new CompleteScanCommand(scanId, body.outcome(),
                Idem.of(idempotencyKey, "POST", "/api/v1/scans/{scanId}/completion", body, scanId.toString()), caller))));
    }

    public ScanSummaryDto summary(UUID scanId) {
        return ProblemTranslator.call(() -> {
            ScanSummaryView view = getScanSummary.execute(new GetScanSummaryQuery(scanId));
            return new ScanSummaryDto(FacadeMapper.scan(view.scan()), FacadeMapper.runtimeProfile(view.runtimeProfile()), view.findingCount(),
                    view.countsByPriority(), view.countsByAlgorithmFamily(), view.countsByLocationKind());
        });
    }
}

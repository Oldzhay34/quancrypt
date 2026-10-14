package com.quancrypt.analyzer.facade;

import com.quancrypt.analyzer.facade.dto.AnalysisDto;
import com.quancrypt.analyzer.facade.dto.AnalysisRequestInput;
import com.quancrypt.analyzer.facade.dto.PluginListDto;
import com.quancrypt.analyzer.facade.dto.SnippetDto;
import com.quancrypt.analyzer.facade.dto.TopologyDto;
import com.quancrypt.analyzer.facade.dto.TopologyRequestInput;
import com.quancrypt.analyzer.facade.error.ApiProblemException;
import com.quancrypt.analyzer.facade.error.ProblemKind;
import com.quancrypt.analyzer.port.inbound.AnalysisView;
import com.quancrypt.analyzer.port.inbound.AnalyzeCryptoCommand;
import com.quancrypt.analyzer.port.inbound.AnalyzeCryptoUseCase;
import com.quancrypt.analyzer.port.inbound.AnalyzerUseCaseException;
import com.quancrypt.analyzer.port.inbound.BuildTopologyCommand;
import com.quancrypt.analyzer.port.inbound.BuildTopologyUseCase;
import com.quancrypt.analyzer.port.inbound.EvidenceView;
import com.quancrypt.analyzer.port.inbound.FindingView;
import com.quancrypt.analyzer.port.inbound.GetSnippetQuery;
import com.quancrypt.analyzer.port.inbound.GetSnippetUseCase;
import com.quancrypt.analyzer.port.inbound.ListPluginsUseCase;
import com.quancrypt.analyzer.port.inbound.ProblemCode;
import com.quancrypt.analyzer.port.inbound.SnippetView;
import com.quancrypt.analyzer.port.inbound.TopologyView;
import java.util.List;
import java.util.Objects;
import java.util.function.Supplier;

/**
 * The one entry point of the controllers: builds the commands from the request, runs the use case, maps the views to
 * the facade DTOs and the use case failures to the problem types of the contract. It holds no business rule: the use
 * cases validate roots, paths and limits (hexagonal-service, section 1).
 */
public final class AnalyzerFacade {

    private final AnalyzeCryptoUseCase analyze;
    private final BuildTopologyUseCase topology;
    private final GetSnippetUseCase snippet;
    private final ListPluginsUseCase plugins;

    public AnalyzerFacade(AnalyzeCryptoUseCase analyze, BuildTopologyUseCase topology, GetSnippetUseCase snippet,
            ListPluginsUseCase plugins) {
        this.analyze = Objects.requireNonNull(analyze, "analyze");
        this.topology = Objects.requireNonNull(topology, "topology");
        this.snippet = Objects.requireNonNull(snippet, "snippet");
        this.plugins = Objects.requireNonNull(plugins, "plugins");
    }

    public AnalysisDto analyze(AnalysisRequestInput request) {
        if (request == null) {
            throw new ApiProblemException(ProblemKind.VALIDATION_FAILED, "the request body must name a root");
        }
        String root = requireRoot(request.root());
        boolean includeTests = request.includeTests() == null || request.includeTests();
        return map(() -> toDto(analyze.analyze(new AnalyzeCryptoCommand(root, includeTests))));
    }

    public TopologyDto topology(TopologyRequestInput request) {
        if (request == null) {
            throw new ApiProblemException(ProblemKind.VALIDATION_FAILED, "the request body must name a root");
        }
        String root = requireRoot(request.root());
        return map(() -> toDto(topology.build(new BuildTopologyCommand(root))));
    }

    public SnippetDto snippet(String root, String path, int line, int context) {
        return map(() -> toDto(snippet.get(new GetSnippetQuery(root, path, line, context))));
    }

    public PluginListDto plugins() {
        return map(() -> new PluginListDto(plugins.list().stream()
                .map(p -> new PluginListDto.PluginDto(p.id(), p.name(), p.version(), p.projectTypes())).toList()));
    }

    private static String requireRoot(String root) {
        if (root == null || root.isBlank()) {
            throw new ApiProblemException(ProblemKind.VALIDATION_FAILED, "the request body must name a root");
        }
        return root;
    }

    private static <T> T map(Supplier<T> call) {
        try {
            return call.get();
        } catch (AnalyzerUseCaseException e) {
            throw new ApiProblemException(kind(e.problemCode()), e.getMessage());
        }
    }

    private static ProblemKind kind(ProblemCode code) {
        return switch (code) {
            case VALIDATION_FAILED -> ProblemKind.VALIDATION_FAILED;
            case PATH_NOT_ALLOWED -> ProblemKind.PATH_NOT_ALLOWED;
            case NOT_FOUND -> ProblemKind.NOT_FOUND;
            case UNSUPPORTED_PROJECT -> ProblemKind.UNSUPPORTED_PROJECT;
            case ANALYSIS_TIMEOUT -> ProblemKind.ANALYSIS_TIMEOUT;
        };
    }

    private static AnalysisDto toDto(AnalysisView view) {
        return new AnalysisDto(view.analysisId(), view.projectType(),
                new AnalysisDto.RuntimeDto(view.runtime().javaVersion().orElse(null), view.runtime().springBootVersion().orElse(null)),
                view.findings().stream().map(AnalyzerFacade::toDto).toList(), view.cbom().json(),
                new AnalysisDto.StatsDto(view.stats().filesScanned(), view.stats().findingsTotal(), view.stats().durationMs()));
    }

    private static AnalysisDto.FindingDto toDto(FindingView f) {
        return new AnalysisDto.FindingDto(f.file(), f.lineStart().orElse(null), f.lineEnd().orElse(null), f.rawName(), f.symbol(),
                f.algorithmFamily(), f.mode().orElse(null), f.padding().orElse(null), f.hash().orElse(null), f.keySizeBits().orElse(null),
                f.usageContext(), f.locationKind(), f.priority(), f.library().orElse(null), f.confidence(), f.detectorId());
    }

    private static SnippetDto toDto(SnippetView view) {
        return new SnippetDto(view.path(), view.lines().stream().map(l -> new SnippetDto.LineDto(l.number(), l.text())).toList());
    }

    private static TopologyDto toDto(TopologyView view) {
        return new TopologyDto(
                view.nodes().stream().map(n -> new TopologyDto.NodeDto(n.id(), n.name(), n.kind(), evidence(n.evidence()))).toList(),
                view.edges().stream().map(e -> new TopologyDto.EdgeDto(e.source(), e.target(), e.protocol(), e.tls(), e.mtls(),
                        evidence(e.evidence()))).toList());
    }

    private static List<TopologyDto.EvidenceDto> evidence(List<EvidenceView> views) {
        return views.stream().map(v -> new TopologyDto.EvidenceDto(v.file(), v.lineStart().orElse(null), v.lineEnd().orElse(null),
                v.locationKind())).toList();
    }
}

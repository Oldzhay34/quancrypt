package com.quancrypt.analyzer.infrastructure.plugin.javaspring;

import com.quancrypt.analyzer.domain.exception.AnalysisTimeoutException;
import com.quancrypt.analyzer.domain.exception.SourceTooLargeException;
import com.quancrypt.analyzer.domain.model.CryptoUsage;
import com.quancrypt.analyzer.domain.model.LocationKind;
import com.quancrypt.analyzer.domain.model.PluginInfo;
import com.quancrypt.analyzer.domain.model.ProjectDescriptor;
import com.quancrypt.analyzer.domain.model.ProjectType;
import com.quancrypt.analyzer.domain.model.RuntimeInfo;
import com.quancrypt.analyzer.domain.model.ServiceGraph;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.topology.TopologyBuilder;
import com.quancrypt.analyzer.port.outbound.LanguagePlugin;
import com.quancrypt.analyzer.port.outbound.SourceTree;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;

/**
 * The Java / Spring Boot language plugin (NFR-06). The first pass reads the whole project into a {@link ProjectIndex}; the
 * second runs every detector over the files it applies to, parsing each Java file once and handing the same parsed unit
 * to all code detectors. A detector that fails on a file is counted in the diagnostics and does not stop the analysis.
 * Nothing is compiled or executed (FR-12) and no symbol is resolved across projects.
 */
public final class JavaSpringPlugin implements LanguagePlugin {

    public static final String ID = "java-spring";
    private static final int MAX_RECORDED_FAILURES = 200;
    private static final PluginInfo INFO = new PluginInfo(ID, "Java and Spring Boot", "1.0.0", Set.of(ProjectType.MAVEN, ProjectType.GRADLE));

    private final List<CryptoDetector> detectors;
    private final BuildRuntime runtime;
    private final ProjectIndexBuilder indexBuilder;
    private final JavaSources sources;
    private final UsageAssembler assembler;
    private final TopologyBuilder topology;

    JavaSpringPlugin(List<CryptoDetector> detectors, BuildRuntime runtime, ProjectIndexBuilder indexBuilder, JavaSources sources,
            UsageAssembler assembler, TopologyBuilder topology) {
        this.detectors = List.copyOf(detectors);
        this.runtime = Objects.requireNonNull(runtime, "runtime");
        this.indexBuilder = Objects.requireNonNull(indexBuilder, "indexBuilder");
        this.sources = Objects.requireNonNull(sources, "sources");
        this.assembler = Objects.requireNonNull(assembler, "assembler");
        this.topology = Objects.requireNonNull(topology, "topology");
    }

    @Override
    public PluginInfo info() {
        return INFO;
    }

    @Override
    public boolean supports(ProjectDescriptor project) {
        return INFO.projectTypes().contains(project.type());
    }

    @Override
    public List<CryptoUsage> analyzeCrypto(SourceTree tree) {
        return analyze(tree).usages();
    }

    /** The usages with the library facts and the diagnostics. */
    public AnalysisOutcome analyze(SourceTree tree) {
        return analyze(tree, indexBuilder.build(tree)).outcome();
    }

    /** One analysis and the Java files the topology detectors may use (their paths only: no syntax tree is kept). */
    private record Analysis(AnalysisOutcome outcome, List<ProjectFile> topologyFiles) {
    }

    private Analysis analyze(SourceTree tree, ProjectIndex index) {
        List<ProjectFile> topologyFiles = new ArrayList<>();
        KeyFileLinker linker = new KeyFileLinker(index.pem());
        CollectingSink sink = new CollectingSink();
        List<String> failures = new ArrayList<>();
        int parsed = 0;
        int skipped = 0;
        for (ProjectFile file : index.files()) {
            tree.checkpoint();
            Optional<JavaUnit> unit = Optional.empty();
            if (file.kind() == FileKind.JAVA) {
                unit = sources.parse(tree, file);
                if (unit.isEmpty()) {
                    skipped++;
                    continue;
                }
                parsed++;
                linker.collect(unit.get());
                if (unit.get().topologyRelevant() && file.location() != LocationKind.TEST_CODE) {
                    topologyFiles.add(file);
                }
            }
            FileContext context = new FileContext(file, unit);
            for (CryptoDetector detector : detectors) {
                if (detector.appliesTo(file)) {
                    run(detector, index, context, sink, failures);
                }
            }
        }
        KeyFileLinker.Linking linking = linker.resolve(sink.observations());
        List<CryptoUsage> usages = assembler.assemble(sink.observations(), linking);
        return new Analysis(new AnalysisOutcome(usages, sink.libraries(), new Diagnostics(parsed, skipped, failures, sink.unresolved())), topologyFiles);
    }

    private static void run(CryptoDetector detector, ProjectIndex index, FileContext context, DetectionSink sink, List<String> failures) {
        try {
            detector.detect(index, context, sink);
        } catch (SourceTooLargeException | AnalysisTimeoutException e) {
            throw e;
        } catch (RuntimeException | StackOverflowError e) {
            if (failures.size() < MAX_RECORDED_FAILURES) {
                failures.add(detector.detectorId() + " on " + context.file().path().value() + ": " + e.getClass().getSimpleName());
            }
        }
    }

    @Override
    public ServiceGraph buildTopology(SourceTree tree) {
        ProjectIndex index = indexBuilder.build(tree);
        Analysis analysis = analyze(tree, index);
        return topology.build(tree, index, analysis.outcome().usages(), analysis.topologyFiles());
    }

    @Override
    public RuntimeInfo runtimeInfo(SourceTree tree) {
        return runtime.read(tree, indexBuilder.classify(tree));
    }
}

package com.quancrypt.analyzer.unit.plugin;

import com.quancrypt.analyzer.domain.model.AnalysisRoot;
import com.quancrypt.analyzer.domain.model.CanonicalNames;
import com.quancrypt.analyzer.domain.model.RuntimeInfo;
import com.quancrypt.analyzer.fake.InMemorySourceTreeReader;
import com.quancrypt.analyzer.infrastructure.dictionary.CanonicalDictionaryLoader;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.BuildRuntime;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.CryptoDetector;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.DetectionSink;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.FileClassifier;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.FileContext;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.FileKind;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.JavaSources;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.JavaUnit;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.LibraryDependency;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.Observation;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.ProjectFile;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.ProjectIndex;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.ProjectIndexBuilder;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.Role;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.config.SpringConfigReader;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.pem.PemReader;
import com.quancrypt.analyzer.port.outbound.SourceTree;
import java.io.UncheckedIOException;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.TreeSet;

/** Runs one detector over a small in-memory project, the way the plugin would. */
final class DetectorHarness {

    static final String ROOT = "/workspace/project";
    private static final CanonicalNames NAMES = load();

    /** What a detector reported. */
    record Outcome(List<Observation> observations, List<LibraryDependency> libraries, Set<String> unresolved) {

        List<Observation> findings() {
            return observations.stream().filter(o -> o.role() == Role.FINDING).toList();
        }

        Observation only() {
            if (observations.size() != 1) {
                throw new AssertionError("expected one observation but got " + observations);
            }
            return observations.get(0);
        }
    }

    private DetectorHarness() {
    }

    static CanonicalNames names() {
        return NAMES;
    }

    /** The project as an index (for tests of the index itself). */
    static ProjectIndex index(String... pathsAndContents) {
        return builder().build(tree(pathsAndContents));
    }

    static SourceTree tree(String... pathsAndContents) {
        InMemorySourceTreeReader reader = new InMemorySourceTreeReader().directory(ROOT);
        for (int i = 0; i + 1 < pathsAndContents.length; i += 2) {
            reader.file(ROOT, pathsAndContents[i], pathsAndContents[i + 1]);
        }
        return reader.open(new AnalysisRoot(ROOT));
    }

    static ProjectIndexBuilder builder() {
        return new ProjectIndexBuilder(new FileClassifier(), new SpringConfigReader(), new PemReader(NAMES));
    }

    static Outcome run(CryptoDetector detector, String... pathsAndContents) {
        return runOn(detector, tree(pathsAndContents));
    }

    /** The Java and Spring Boot version a runtime reader finds in the project. */
    static RuntimeInfo runtimeOf(BuildRuntime runtime, String... pathsAndContents) {
        SourceTree tree = tree(pathsAndContents);
        return runtime.read(tree, builder().classify(tree));
    }

    static Outcome runOn(CryptoDetector detector, SourceTree tree) {
        ProjectIndex index = builder().build(tree);
        JavaSources sources = new JavaSources();
        List<Observation> observations = new ArrayList<>();
        List<LibraryDependency> libraries = new ArrayList<>();
        Set<String> unresolved = new TreeSet<>();
        DetectionSink sink = new DetectionSink() {
            @Override
            public void add(Observation observation) {
                observations.add(observation);
            }

            @Override
            public void library(LibraryDependency dependency) {
                libraries.add(dependency);
            }

            @Override
            public void unresolved(String detectorId, String rawName) {
                unresolved.add(rawName);
            }
        };
        for (ProjectFile file : index.files()) {
            if (!detector.appliesTo(file)) {
                continue;
            }
            Optional<JavaUnit> unit = file.kind() == FileKind.JAVA ? sources.parse(tree, file) : Optional.empty();
            detector.detect(index, new FileContext(file, unit), sink);
        }
        return new Outcome(observations, libraries, unresolved);
    }

    private static CanonicalNames load() {
        try {
            return new CanonicalNames(new CanonicalDictionaryLoader().loadFromClasspath());
        } catch (UncheckedIOException e) {
            throw new IllegalStateException(e);
        }
    }

}

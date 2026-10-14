package com.quancrypt.analyzer.infrastructure.plugin.javaspring;

import com.quancrypt.analyzer.domain.exception.PathNotAllowedException;
import com.quancrypt.analyzer.domain.exception.SourceNotFoundException;
import com.quancrypt.analyzer.domain.exception.SourceTooLargeException;
import com.quancrypt.analyzer.domain.model.RelativePath;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.config.ConfigIndex;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.config.ConfigProperty;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.config.SpringConfigReader;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.pem.PemFacts;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.pem.PemIndex;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.pem.PemReader;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.ssl.SslBundleIndex;
import com.quancrypt.analyzer.port.outbound.SourceTree;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

/** The first pass: classifies the files, then reads configuration and PEM files into the {@link ProjectIndex}. */
public final class ProjectIndexBuilder {

    /** Configuration properties of the whole project; a file adds at most 20,000 itself (D-181 reading limit). */
    static final int MAX_PROJECT_PROPERTIES = 200_000;

    private final FileClassifier classifier;
    private final SpringConfigReader configReader;
    private final PemReader pemReader;

    public ProjectIndexBuilder(FileClassifier classifier, SpringConfigReader configReader, PemReader pemReader) {
        this.classifier = classifier;
        this.configReader = configReader;
        this.pemReader = pemReader;
    }

    /** The project's files that are not in a skipped directory, with their kinds. */
    public List<ProjectFile> classify(SourceTree tree) {
        List<ProjectFile> files = new ArrayList<>();
        for (RelativePath path : visible(tree.files())) {
            files.add(classifier.classify(path));
        }
        return files;
    }

    public ProjectIndex build(SourceTree tree) {
        List<ProjectFile> files = classify(tree);
        List<ConfigProperty> properties = new ArrayList<>();
        List<PemFacts> pems = new ArrayList<>();
        for (ProjectFile file : files) {
            switch (file.kind()) {
                case SPRING_YAML -> text(tree, file).ifPresent(t -> properties.addAll(configReader.yaml(file.path(), t)));
                case SPRING_PROPERTIES -> lines(tree, file).ifPresent(l -> properties.addAll(configReader.properties(file.path(), l)));
                case PEM -> lines(tree, file).flatMap(l -> pemReader.read(file.path(), l)).ifPresent(pems::add);
                default -> { }
            }
            if (properties.size() > MAX_PROJECT_PROPERTIES) {
                throw new SourceTooLargeException("the project has more configuration properties than one analysis reads");
            }
        }
        ConfigIndex config = new ConfigIndex(properties);
        return new ProjectIndex(tree, files, config, new PemIndex(pems), new SslBundleIndex(config));
    }

    /** The files that are not below a skipped directory. */
    List<RelativePath> visible(List<RelativePath> all) {
        Map<String, Set<String>> children = new HashMap<>();
        Set<String> directories = new HashSet<>();
        for (RelativePath path : all) {
            List<String> segments = path.segments();
            StringBuilder prefix = new StringBuilder();
            for (int i = 0; i < segments.size(); i++) {
                children.computeIfAbsent(prefix.toString(), k -> new HashSet<>()).add(segments.get(i));
                if (!prefix.isEmpty()) {
                    prefix.append('/');
                }
                prefix.append(segments.get(i));
                if (i < segments.size() - 1) {
                    directories.add(prefix.toString());
                }
            }
        }
        Set<String> skipped = new HashSet<>();
        for (String directory : directories) {
            int slash = directory.lastIndexOf('/');
            String name = slash < 0 ? directory : directory.substring(slash + 1);
            String parent = slash < 0 ? "" : directory.substring(0, slash);
            if (classifier.skipsDirectory(name, children.getOrDefault(parent, Set.of()))) {
                skipped.add(directory);
            }
        }
        List<RelativePath> visible = new ArrayList<>();
        for (RelativePath path : all) {
            if (!below(path, skipped)) {
                visible.add(path);
            }
        }
        return visible;
    }

    private static boolean below(RelativePath path, Set<String> skipped) {
        if (skipped.isEmpty()) {
            return false;
        }
        List<String> segments = path.segments();
        StringBuilder prefix = new StringBuilder();
        for (int i = 0; i < segments.size() - 1; i++) {
            if (!prefix.isEmpty()) {
                prefix.append('/');
            }
            prefix.append(segments.get(i));
            if (skipped.contains(prefix.toString())) {
                return true;
            }
        }
        return false;
    }

    private static Optional<List<String>> lines(SourceTree tree, ProjectFile file) {
        try {
            return Optional.of(tree.readLines(file.path()));
        } catch (SourceNotFoundException | PathNotAllowedException e) {
            return Optional.empty();
        }
    }

    private static Optional<String> text(SourceTree tree, ProjectFile file) {
        return lines(tree, file).map(l -> String.join("\n", l)).filter(SpringConfigReader::isText);
    }
}

package com.quancrypt.analyzer.infrastructure.plugin.javaspring.topology;

import com.quancrypt.analyzer.domain.model.LocationKind;
import com.quancrypt.analyzer.domain.model.RelativePath;
import com.quancrypt.analyzer.domain.model.RuntimeInfo;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.BuildRuntime;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.FileKind;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.NameSanitizer;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.ProjectFile;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.ProjectIndex;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.config.ConfigProperty;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.TreeSet;
import java.util.regex.Pattern;

/**
 * The modules of a project (ServiceIdentityResolver, first half): every directory with a build file is a module, named by its
 * {@code spring.application.name} and otherwise by its directory name. A file belongs to the module with the longest
 * directory that contains it.
 */
public final class Modules {

    private static final Pattern NAME = Pattern.compile("[A-Za-z0-9._-]{1,200}");

    private final List<Module> modules;

    private Modules(List<Module> modules) {
        this.modules = modules.stream().sorted(Comparator.comparingInt((Module m) -> m.dir().length()).reversed().thenComparing(Module::dir))
                .toList();
    }

    public static Modules discover(ProjectIndex index, BuildRuntime runtime) {
        Set<String> directories = new TreeSet<>();
        for (ProjectFile file : index.files()) {
            if (file.kind() == FileKind.POM || file.kind() == FileKind.GRADLE) {
                directories.add(directoryOf(file.path()));
            }
        }
        Set<RelativePath> testFiles = new TreeSet<>(Comparator.comparing(RelativePath::value));
        for (ProjectFile file : index.files()) {
            if (file.location() == LocationKind.TEST_CODE) {
                testFiles.add(file.path());
            }
        }
        RuntimeInfo project = runtime.read(index.tree(), index.files());
        String rootName = lastSegment(index.tree().root().value());
        // A file belongs to the module with the longest directory that contains it: the directories are tried longest first.
        List<String> longestFirst = directories.stream().sorted(Comparator.comparingInt(String::length).reversed().thenComparing(d -> d)).toList();
        Map<String, List<ProjectFile>> files = new HashMap<>();
        for (ProjectFile file : index.files()) {
            owner(longestFirst, file.path()).ifPresent(dir -> files.computeIfAbsent(dir, d -> new ArrayList<>()).add(file));
        }
        Map<String, List<ConfigProperty>> properties = new HashMap<>();
        for (ConfigProperty property : index.config().all()) {
            if (!testFiles.contains(property.file())) {
                owner(longestFirst, property.file()).ifPresent(dir -> properties.computeIfAbsent(dir, d -> new ArrayList<>()).add(property));
            }
        }
        List<Module> found = new ArrayList<>();
        for (String dir : directories) {
            ModuleConfig config = new ModuleConfig(properties.getOrDefault(dir, List.of()), index.config());
            String name = config.value("spring.application.name").filter(v -> NAME.matcher(v).matches())
                    .orElseGet(() -> NameSanitizer.clean(dir.isEmpty() ? rootName : dir.substring(dir.lastIndexOf('/') + 1)));
            Optional<String> java = runtime.read(index.tree(), files.getOrDefault(dir, List.of())).javaVersion().or(project::javaVersion);
            found.add(new Module(dir, name, config, java));
        }
        return new Modules(found);
    }

    public List<Module> all() {
        return List.copyOf(modules);
    }

    /** The module a file belongs to (the one with the longest containing directory). */
    public Optional<Module> of(RelativePath file) {
        return modules.stream().filter(m -> m.contains(file)).findFirst();
    }

    /** The name of the analysis root's own directory, for a build file at the root. */
    private static String lastSegment(String root) {
        String trimmed = root.endsWith("/") ? root.substring(0, root.length() - 1) : root;
        return trimmed.substring(trimmed.lastIndexOf('/') + 1);
    }

    private static Optional<String> owner(List<String> longestFirst, RelativePath file) {
        String path = file.value();
        for (String dir : longestFirst) {
            if (dir.isEmpty() || path.startsWith(dir + "/")) {
                return Optional.of(dir);
            }
        }
        return Optional.empty();
    }

    private static String directoryOf(RelativePath file) {
        String value = file.value();
        int slash = value.lastIndexOf('/');
        return slash < 0 ? "" : value.substring(0, slash);
    }
}

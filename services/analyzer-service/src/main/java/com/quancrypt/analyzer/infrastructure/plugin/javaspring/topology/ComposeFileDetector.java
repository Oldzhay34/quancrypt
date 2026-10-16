package com.quancrypt.analyzer.infrastructure.plugin.javaspring.topology;

import com.quancrypt.analyzer.domain.exception.PathNotAllowedException;
import com.quancrypt.analyzer.domain.exception.SourceNotFoundException;
import com.quancrypt.analyzer.domain.model.LocationKind;
import com.quancrypt.analyzer.domain.model.Protocol;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.FileKind;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.ProjectFile;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.ProjectIndex;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.config.ConfigProperty;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.config.SpringConfigReader;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * The services of {@code docker-compose*.yml} files: image, where the code is built from, ports, bind mounts, networks and
 * {@code depends_on}. A compose service that publishes a port is reachable from outside, so every such Spring service gets an
 * edge from the synthetic {@code external-client} node (whether it is encrypted is the service's own TLS setting, decided by
 * the assembler). Mounts and dependencies are used by the MQTT detector for devices.
 */
final class ComposeFileDetector implements TopologyDetector {

    static final String ID = "topology.compose";
    private static final Pattern KEY = Pattern.compile("^services\\.([^.\\[\\]]{1,128})\\.(.+)$");
    private static final Pattern INDEXED = Pattern.compile("^(ports|volumes|networks|depends_on)\\[(\\d+)](?:\\.(.+))?$");
    private static final Pattern DEPENDS_MAP = Pattern.compile("^depends_on\\.([^.\\[\\]]{1,128})\\..+$");
    private static final Pattern NETWORKS_MAP = Pattern.compile("^networks\\.([^.\\[\\]]{1,128})(?:\\..+)?$");

    private final SpringConfigReader reader;

    ComposeFileDetector(SpringConfigReader reader) {
        this.reader = reader;
    }

    @Override
    public String detectorId() {
        return ID;
    }

    /** The compose services of the project, in file and name order. */
    List<ComposeService> read(ProjectIndex index) {
        List<ComposeService> services = new ArrayList<>();
        for (ProjectFile file : index.files()) {
            if (file.kind() != FileKind.COMPOSE || file.location() == LocationKind.TEST_CODE) {
                continue;
            }
            index.tree().checkpoint();
            Optional<String> text = text(index, file);
            text.ifPresent(t -> services.addAll(parse(file, reader.yaml(file.path(), t))));
        }
        return services;
    }

    @Override
    public void detect(TopologyContext context, TopologySink sink) {
        for (ComposeService service : context.compose()) {
            Optional<TNode> node = context.registry().byName(service.name());
            if (node.isEmpty() || !node.get().present || node.get().module.isEmpty() || !service.hasPublishedPort()) {
                continue;
            }
            for (ComposeService.Published port : service.ports()) {
                if (port.published()) {
                    sink.edge(RawEdge.of(TopologySink.EXTERNAL_CLIENT, new Target(service.name().toLowerCase(java.util.Locale.ROOT), -1, ""),
                            Protocol.HTTP, false, TopologyContext.at(service.file(), port.line(), LocationKind.CONFIG)));
                }
            }
        }
    }

    private static Optional<String> text(ProjectIndex index, ProjectFile file) {
        try {
            String text = String.join("\n", index.tree().readLines(file.path()));
            return SpringConfigReader.isText(text) ? Optional.of(text) : Optional.empty();
        } catch (SourceNotFoundException | PathNotAllowedException e) {
            return Optional.empty();
        }
    }

    private static List<ComposeService> parse(ProjectFile file, List<ConfigProperty> properties) {
        Map<String, List<ConfigProperty>> byService = new LinkedHashMap<>();
        for (ConfigProperty property : properties) {
            Matcher matcher = KEY.matcher(property.key());
            if (matcher.matches()) {
                byService.computeIfAbsent(matcher.group(1), k -> new ArrayList<>()).add(property);
            }
        }
        String base = ProjectPaths.directoryOf(file.path().value());
        List<ComposeService> services = new ArrayList<>();
        byService.forEach((name, own) -> services.add(service(file, base, name, own)));
        return services;
    }

    private static ComposeService service(ProjectFile file, String base, String name, List<ConfigProperty> own) {
        Optional<String> image = Optional.empty();
        Optional<String> context = Optional.empty();
        Optional<String> dockerfile = Optional.empty();
        List<ComposeService.Dependency> depends = new ArrayList<>();
        List<ComposeService.Published> ports = new ArrayList<>();
        List<ComposeService.Mount> mounts = new ArrayList<>();
        List<String> networks = new ArrayList<>();
        int line = own.stream().mapToInt(ConfigProperty::line).min().orElse(1);
        for (ConfigProperty property : own) {
            String key = KEY.matcher(property.key()).replaceFirst("$2");
            String value = property.value().strip();
            Matcher indexed = INDEXED.matcher(key);
            Matcher dependsMap = DEPENDS_MAP.matcher(key);
            Matcher networksMap = NETWORKS_MAP.matcher(key);
            if (key.equals("image")) {
                image = Optional.of(value);
            } else if (key.equals("build") || key.equals("build.context")) {
                context = Optional.of(value);
            } else if (key.equals("build.dockerfile")) {
                dockerfile = Optional.of(value);
            } else if (indexed.matches()) {
                String kind = indexed.group(1);
                String member = indexed.group(3);
                if (kind.equals("depends_on") && member == null) {
                    depends.add(new ComposeService.Dependency(value, property.line()));
                } else if (kind.equals("ports") && (member == null || member.equals("published") || member.equals("target"))) {
                    ports.add(port(value, member, property.line()));
                } else if (kind.equals("volumes") && (member == null || member.equals("source"))) {
                    mounts.add(new ComposeService.Mount(hostPath(base, value, member != null), property.line()));
                } else if (kind.equals("networks") && member == null) {
                    networks.add(value);
                }
            } else if (dependsMap.matches() && key.endsWith(".condition")) {
                depends.add(new ComposeService.Dependency(dependsMap.group(1), property.line()));
            } else if (networksMap.matches() && !networks.contains(networksMap.group(1))) {
                networks.add(networksMap.group(1));
            }
        }
        return new ComposeService(name, file.path(), line, image, directory(base, context, dockerfile), depends, ports, mounts, networks);
    }

    /** The directory with the service's code: the Dockerfile's directory when it is below the context, else the context. */
    private static Optional<String> directory(String base, Optional<String> context, Optional<String> dockerfile) {
        if (context.isEmpty()) {
            return Optional.empty();
        }
        Optional<String> contextDirectory = ProjectPaths.resolve(base, context.get());
        if (contextDirectory.isEmpty()) {
            return Optional.empty();
        }
        Optional<String> fileDirectory = dockerfile.filter(d -> d.contains("/"))
                .flatMap(d -> ProjectPaths.resolve(contextDirectory.get(), ProjectPaths.directoryOf(d)));
        Optional<String> chosen = fileDirectory.or(() -> contextDirectory);
        return chosen.filter(d -> !d.isEmpty());
    }

    private static ComposeService.Published port(String value, String member, int line) {
        String text = value.replace("\"", "").strip();
        if (member != null) {
            return new ComposeService.Published(member.equals("published"), number(text), line);
        }
        String withoutProtocol = text.contains("/") ? text.substring(0, text.indexOf('/')) : text;
        String[] parts = withoutProtocol.split(":");
        return new ComposeService.Published(parts.length > 1, number(parts[parts.length - 1]), line);
    }

    private static int number(String text) {
        try {
            int number = Integer.parseInt(text.strip());
            return number > 0 && number <= 65535 ? number : -1;
        } catch (NumberFormatException e) {
            return -1;
        }
    }

    private static Optional<String> hostPath(String base, String value, boolean longSyntax) {
        String host = longSyntax ? value : value.split(":", 2)[0];
        if (!(host.startsWith("./") || host.startsWith("../")) && !host.contains("/")) {
            return Optional.empty();
        }
        return ProjectPaths.resolve(base, host).filter(p -> !p.isEmpty());
    }
}

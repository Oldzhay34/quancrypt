package com.quancrypt.analyzer.infrastructure.plugin.javaspring.topology;

import com.quancrypt.analyzer.domain.model.RelativePath;
import java.util.List;
import java.util.Optional;

/**
 * A service of a compose file. {@code directory} is where its code is: the build context, or the directory of the
 * Dockerfile when the Dockerfile lies below the context (the context is then only the build's reach); empty when the
 * service is image-only or builds from the root.
 */
record ComposeService(String name, RelativePath file, int line, Optional<String> image, Optional<String> directory, List<Dependency> dependsOn,
        List<Published> ports, List<Mount> volumes, List<String> networks) {

    record Dependency(String name, int line) {
    }

    /** One {@code ports} entry; {@code published} when it maps a host port. */
    record Published(boolean published, int containerPort, int line) {
    }

    /** One {@code volumes} entry; {@code hostPath} is the normalised path of a bind mount inside the project, when it is one. */
    record Mount(Optional<String> hostPath, int line) {
    }

    ComposeService {
        dependsOn = List.copyOf(dependsOn);
        ports = List.copyOf(ports);
        volumes = List.copyOf(volumes);
        networks = List.copyOf(networks);
    }

    boolean hasPublishedPort() {
        return ports.stream().anyMatch(Published::published);
    }
}

package com.quancrypt.analyzer.infrastructure.plugin.javaspring.topology;

import com.quancrypt.analyzer.domain.model.Evidence;
import com.quancrypt.analyzer.domain.model.LineRange;
import com.quancrypt.analyzer.domain.model.LocationKind;
import com.quancrypt.analyzer.domain.model.RelativePath;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.ProjectIndex;
import java.util.List;
import java.util.Optional;

/**
 * What topology detectors share: the project index, its modules, the compose services, the registry of nodes and the facts the
 * Java code gave about each module.
 */
record TopologyContext(ProjectIndex index, Modules modules, List<ComposeService> compose, ServiceRegistry registry, ModuleFacts facts) {

    TopologyContext {
        compose = List.copyOf(compose);
    }

    /** The node of the module a file belongs to. */
    Optional<TNode> nodeOf(RelativePath file) {
        return modules.of(file).flatMap(registry::nodeOf);
    }

    static Evidence at(RelativePath file, int line, LocationKind kind) {
        return new Evidence(file, line > 0 ? Optional.of(new LineRange(line, line)) : Optional.empty(), kind);
    }
}

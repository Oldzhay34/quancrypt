package com.quancrypt.analyzer.usecase;

import com.quancrypt.analyzer.port.inbound.BuildTopologyCommand;
import com.quancrypt.analyzer.port.inbound.BuildTopologyUseCase;
import com.quancrypt.analyzer.port.inbound.TopologyView;
import java.util.Objects;

/** Builds a project's service topology with the plugin that supports it. */
public final class BuildTopologyService implements BuildTopologyUseCase {

    private final ProjectOpener opener;
    private final PluginSelector plugins;

    public BuildTopologyService(ProjectOpener opener, PluginSelector plugins) {
        this.opener = Objects.requireNonNull(opener, "opener");
        this.plugins = Objects.requireNonNull(plugins, "plugins");
    }

    @Override
    public TopologyView build(BuildTopologyCommand command) {
        OpenedProject project = opener.open(command.root());
        return Failures.translate(() -> Views.topology(plugins.select(project.descriptor()).buildTopology(project.tree())));
    }
}

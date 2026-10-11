package com.quancrypt.analyzer.usecase;

import com.quancrypt.analyzer.domain.exception.UnsupportedProjectException;
import com.quancrypt.analyzer.domain.model.ProjectDescriptor;
import com.quancrypt.analyzer.port.outbound.LanguagePlugin;
import java.util.List;

/** Picks the first registered plugin that supports a project; a new language needs no change here (OCP). */
public final class PluginSelector {

    private final List<LanguagePlugin> plugins;

    public PluginSelector(List<LanguagePlugin> plugins) {
        this.plugins = List.copyOf(plugins);
    }

    LanguagePlugin select(ProjectDescriptor project) {
        return plugins.stream()
                .filter(plugin -> plugin.supports(project))
                .findFirst()
                .orElseThrow(() -> new UnsupportedProjectException("no installed plugin supports the project"));
    }

    List<LanguagePlugin> all() {
        return plugins;
    }
}

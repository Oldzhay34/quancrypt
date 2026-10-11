package com.quancrypt.analyzer.usecase;

import com.quancrypt.analyzer.port.inbound.ListPluginsUseCase;
import com.quancrypt.analyzer.port.inbound.PluginView;
import com.quancrypt.analyzer.port.outbound.LanguagePlugin;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;

/** Lists the installed plugins, sorted by id. */
public final class ListPluginsService implements ListPluginsUseCase {

    private final PluginSelector plugins;

    public ListPluginsService(PluginSelector plugins) {
        this.plugins = Objects.requireNonNull(plugins, "plugins");
    }

    @Override
    public List<PluginView> list() {
        return plugins.all().stream()
                .map(LanguagePlugin::info)
                .map(Views::plugin)
                .sorted(Comparator.comparing(PluginView::id))
                .toList();
    }
}

package com.quancrypt.analyzer.port.inbound;

import java.util.List;

/** An installed language plugin. */
public record PluginView(String id, String name, String version, List<String> projectTypes) {

    public PluginView {
        projectTypes = List.copyOf(projectTypes);
    }
}

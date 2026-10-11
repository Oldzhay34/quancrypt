package com.quancrypt.analyzer.domain.model;

import java.util.Set;

/** What a language plugin says about itself (GET /api/v1/plugins). */
public record PluginInfo(String id, String name, String version, Set<ProjectType> projectTypes) {

    public PluginInfo {
        Text.matching(id, Text.IDENTIFIER, "id");
        Text.printable(name, 128, "name");
        Text.matching(version, Text.VERSION, "version");
        projectTypes = Set.copyOf(projectTypes);
        if (projectTypes.isEmpty()) {
            throw new IllegalArgumentException("a plugin supports at least one project type");
        }
    }
}

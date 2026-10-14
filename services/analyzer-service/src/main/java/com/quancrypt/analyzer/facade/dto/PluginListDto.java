package com.quancrypt.analyzer.facade.dto;

import java.util.List;

/** The installed language plugins (contract `PluginList`). */
public record PluginListDto(List<PluginDto> plugins) {

    public PluginListDto {
        plugins = List.copyOf(plugins);
    }

    /** One plugin. */
    public record PluginDto(String id, String name, String version, List<String> projectTypes) {

        public PluginDto {
            projectTypes = List.copyOf(projectTypes);
        }
    }
}

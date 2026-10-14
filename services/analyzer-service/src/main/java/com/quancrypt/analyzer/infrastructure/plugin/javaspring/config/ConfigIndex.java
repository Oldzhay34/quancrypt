package com.quancrypt.analyzer.infrastructure.plugin.javaspring.config;

import com.quancrypt.analyzer.domain.model.RelativePath;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.Placeholders;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.function.Predicate;

/** All configuration properties of the project (every Spring config file, every profile). */
public final class ConfigIndex {

    private final List<ConfigProperty> properties;
    private final Map<RelativePath, List<ConfigProperty>> byFile = new HashMap<>();
    private final Map<String, String> firstValueByKey = new HashMap<>();

    public ConfigIndex(List<ConfigProperty> properties) {
        this.properties = List.copyOf(properties);
        for (ConfigProperty property : this.properties) {
            byFile.computeIfAbsent(property.file(), file -> new ArrayList<>()).add(property);
            firstValueByKey.putIfAbsent(property.key(), property.value());
        }
    }

    public List<ConfigProperty> all() {
        return properties;
    }

    public List<ConfigProperty> of(RelativePath file) {
        return List.copyOf(byFile.getOrDefault(file, List.of()));
    }

    public List<ConfigProperty> matching(Predicate<ConfigProperty> test) {
        return properties.stream().filter(test).toList();
    }

    /** The value of a key anywhere in the project (first in file order), for placeholder resolution. */
    public Optional<String> value(String key) {
        return Optional.ofNullable(firstValueByKey.get(key));
    }

    /** The value with placeholders resolved against the project's own properties and their defaults. */
    public String resolved(String value) {
        return Placeholders.resolve(value, this::value);
    }
}

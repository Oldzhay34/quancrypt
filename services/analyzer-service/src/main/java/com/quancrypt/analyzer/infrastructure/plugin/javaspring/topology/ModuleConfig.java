package com.quancrypt.analyzer.infrastructure.plugin.javaspring.topology;

import com.quancrypt.analyzer.infrastructure.plugin.javaspring.Placeholders;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.config.ConfigIndex;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.config.ConfigProperty;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.function.Supplier;

/**
 * The configuration properties of one module (its own files, test resources left out). A placeholder is resolved against the
 * module's own properties first and only then against the project's, so two modules that name the same key do not read each
 * other's value.
 */
public final class ModuleConfig {

    private final List<ConfigProperty> properties;
    private final ConfigIndex project;
    private final Map<String, ConfigProperty> first = new HashMap<>();
    private final Map<String, Object> cache = new HashMap<>();

    ModuleConfig(List<ConfigProperty> properties, ConfigIndex project) {
        this.properties = List.copyOf(properties);
        this.project = project;
        for (ConfigProperty property : this.properties) {
            first.putIfAbsent(property.key(), property);
        }
    }

    /** A value worked out from the properties once and kept (the properties never change). */
    @SuppressWarnings("unchecked")
    <T> T cached(String name, Supplier<T> compute) {
        return (T) cache.computeIfAbsent(name, k -> compute.get());
    }

    public List<ConfigProperty> all() {
        return properties;
    }

    public Optional<ConfigProperty> property(String key) {
        return Optional.ofNullable(first.get(key));
    }

    /** The resolved value of a key, when the module sets it. */
    public Optional<String> value(String key) {
        return property(key).map(p -> resolved(p.value()).strip());
    }

    public boolean hasKeyStartingWith(String prefix) {
        return properties.stream().anyMatch(p -> p.key().startsWith(prefix));
    }

    public String resolved(String value) {
        return Placeholders.resolve(value, key -> Optional.ofNullable(first.get(key)).map(ConfigProperty::value).or(() -> project.value(key)));
    }
}

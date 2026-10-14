package com.quancrypt.analyzer.infrastructure.plugin.javaspring.ssl;

import com.quancrypt.analyzer.infrastructure.plugin.javaspring.config.ConfigIndex;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.config.ConfigProperty;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.TreeSet;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * The SSL bundles declared in the project's configuration and the names that point at a bundle from the server side
 * (server.ssl.bundle, management.server.ssl.bundle) as opposed to a client side reference.
 */
public final class SslBundleIndex {

    private static final Pattern BUNDLE_KEY = Pattern.compile("spring\\.ssl\\.bundle\\.(pem|jks)\\.([^.\\[\\]]+)\\.(.+)");

    private final Map<String, SslBundle> bundles = new LinkedHashMap<>();
    private final Set<String> serverNames = new TreeSet<>();

    public SslBundleIndex(ConfigIndex config) {
        Map<String, List<ConfigProperty>> grouped = new LinkedHashMap<>();
        for (ConfigProperty property : config.all()) {
            Matcher matcher = BUNDLE_KEY.matcher(property.key());
            if (matcher.matches()) {
                grouped.computeIfAbsent(matcher.group(1) + "|" + matcher.group(2), k -> new ArrayList<>()).add(property);
            }
            if (property.key().equals("server.ssl.bundle") || property.key().equals("management.server.ssl.bundle")) {
                serverNames.add(config.resolved(property.value()));
            }
        }
        grouped.forEach((id, properties) -> {
            String[] parts = id.split("\\|", 2);
            List<String> keystore = new ArrayList<>();
            List<String> truststore = new ArrayList<>();
            for (ConfigProperty property : properties) {
                String key = property.key().substring(property.key().indexOf(parts[1] + ".") + parts[1].length() + 1);
                String value = config.resolved(property.value());
                if (key.equals("keystore.certificate") || key.equals("keystore.location")) {
                    keystore.add(value);
                } else if (key.equals("truststore.certificate") || key.equals("truststore.location")) {
                    truststore.add(value);
                }
            }
            ConfigProperty first = properties.get(0);
            bundles.putIfAbsent(parts[1], new SslBundle(parts[1], parts[0], first.file(), properties.stream().mapToInt(ConfigProperty::line)
                    .min().orElse(first.line()), keystore, truststore));
        });
    }

    public Optional<SslBundle> get(String name) {
        return Optional.ofNullable(bundles.get(name));
    }

    public List<SslBundle> all() {
        return List.copyOf(bundles.values());
    }

    public boolean isServerBundle(String name) {
        return serverNames.contains(name);
    }
}

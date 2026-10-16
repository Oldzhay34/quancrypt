package com.quancrypt.analyzer.infrastructure.plugin.javaspring.topology;

import com.quancrypt.analyzer.domain.model.Protocol;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.config.ConfigProperty;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Optional;
import java.util.Set;
import java.util.regex.Pattern;

/**
 * The URLs a module configuration names and the client SSL bundles it configures, shared by the detectors that bind code to
 * configuration. Server side keys, bundle definitions and logging are not connections. Everything is worked out once per module
 * (a module can have tens of thousands of properties and every detector asks), so the cost grows with the properties and not
 * with the properties times the detectors, the files or the bundles.
 */
final class ConfigUrls {

    private static final Pattern GATEWAY_ROUTE_URI = Pattern.compile("^spring\\.cloud\\.gateway\\..*routes\\[\\d+]\\.uri$");
    private static final Pattern BUNDLE_REFERENCE = Pattern.compile(".*\\bssl[.-]bundle$");
    private static final Pattern INDEX = Pattern.compile("\\[\\d+]");
    private static final List<String> NOT_CONNECTIONS = List.of("spring.ssl.bundle.", "server.", "management.", "logging.");
    private static final int MAX_URL_LENGTH = 2048;

    /** A property whose value is a connection URL. */
    record UrlProperty(ConfigProperty property, Target target, Protocol protocol) {
    }

    /** A property that names an SSL bundle the client uses; the segments of its key are split once. */
    private record BundleReference(String[] segments, String value) {
    }

    private ConfigUrls() {
    }

    /** The URL-valued properties of a module that describe a connection (gateway routes are left to their own detector). */
    static List<UrlProperty> of(Module module) {
        return module.config().cached("urls", () -> {
            List<UrlProperty> found = new ArrayList<>();
            for (ConfigProperty property : module.config().all()) {
                String key = property.key();
                if (NOT_CONNECTIONS.stream().anyMatch(key::startsWith) || GATEWAY_ROUTE_URI.matcher(key).matches()) {
                    continue;
                }
                url(module, property).ifPresent(found::add);
            }
            return List.copyOf(found);
        });
    }

    /** The gateway route URIs of a module. */
    static List<UrlProperty> routes(Module module) {
        return module.config().cached("routes", () -> {
            List<UrlProperty> found = new ArrayList<>();
            for (ConfigProperty property : module.config().all()) {
                if (GATEWAY_ROUTE_URI.matcher(property.key()).matches()) {
                    url(module, property).ifPresent(found::add);
                }
            }
            return List.copyOf(found);
        });
    }

    private static Optional<UrlProperty> url(Module module, ConfigProperty property) {
        if (property.value().length() > MAX_URL_LENGTH) {
            return Optional.empty();
        }
        String value = module.config().resolved(property.value()).strip();
        if (value.contains("${") || value.length() > MAX_URL_LENGTH) {
            return Optional.empty();
        }
        return Target.ofUrl(value).flatMap(target -> target.protocol().map(protocol -> new UrlProperty(property, target, protocol)));
    }

    /** The client bundles configured next to a key: bundle references whose key shares at least three leading segments with it. */
    static Set<String> bundlesNear(Module module, String key) {
        List<BundleReference> references = references(module);
        Set<String> bundles = new LinkedHashSet<>();
        if (references.isEmpty()) {
            return bundles;
        }
        String[] segments = INDEX.matcher(key).replaceAll("").split("\\.");
        for (BundleReference reference : references) {
            if (sharedSegments(segments, reference.segments()) >= 3) {
                bundles.add(reference.value());
            }
        }
        return bundles;
    }

    /** Every client bundle name the configuration references. */
    static Set<String> configuredBundles(Module module) {
        Set<String> bundles = new LinkedHashSet<>();
        references(module).forEach(r -> bundles.add(r.value()));
        return bundles;
    }

    private static List<BundleReference> references(Module module) {
        return module.config().cached("bundle-references", () -> {
            List<BundleReference> found = new ArrayList<>();
            for (ConfigProperty property : module.config().all()) {
                String key = property.key();
                if (BUNDLE_REFERENCE.matcher(key).matches() && !key.equals("server.ssl.bundle") && !key.equals("management.server.ssl.bundle")) {
                    String value = module.config().resolved(property.value()).strip();
                    if (!value.isEmpty() && !value.contains("${")) {
                        found.add(new BundleReference(INDEX.matcher(key).replaceAll("").split("\\."), value));
                    }
                }
            }
            return List.copyOf(found);
        });
    }

    /** A name without case, dashes and underscores: {@code account-service-url} and {@code accountServiceUrl} compare equal. */
    static String relaxed(String name) {
        return name.replace("-", "").replace("_", "").toLowerCase(Locale.ROOT);
    }

    /** The last segment of a property key, without an index. */
    static String lastSegment(String key) {
        String last = key.substring(key.lastIndexOf('.') + 1);
        int bracket = last.indexOf('[');
        return bracket < 0 ? last : last.substring(0, bracket);
    }

    private static int sharedSegments(String[] left, String[] right) {
        int shared = 0;
        while (shared < Math.min(left.length, right.length) && left[shared].equals(right[shared])) {
            shared++;
        }
        return shared;
    }
}

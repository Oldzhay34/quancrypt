package com.quancrypt.core.domain.event;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;

/** Small helpers to build ordered, null-tolerant payload maps. */
final class Payloads {

    private Payloads() {
    }

    static Map<String, Object> of(Object... keyValues) {
        Map<String, Object> map = new LinkedHashMap<>();
        for (int i = 0; i < keyValues.length; i += 2) {
            map.put((String) keyValues[i], keyValues[i + 1]);
        }
        return java.util.Collections.unmodifiableMap(map);
    }

    static Object orNull(Optional<?> value) {
        return value.orElse(null);
    }

    static <K extends Enum<K>> Map<String, Object> counts(Map<K, Integer> counts) {
        Map<String, Object> map = new LinkedHashMap<>();
        counts.entrySet().stream()
                .sorted(Map.Entry.comparingByKey())
                .forEach(e -> map.put(e.getKey().name(), e.getValue()));
        return java.util.Collections.unmodifiableMap(map);
    }
}

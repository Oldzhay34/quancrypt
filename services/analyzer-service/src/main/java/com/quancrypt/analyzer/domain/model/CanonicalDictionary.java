package com.quancrypt.analyzer.domain.model;

import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;

/**
 * The canonical dictionary (contracts/canonical_dictionary.csv): raw spellings mapped to crypto-domain codes. Lookups
 * ignore case and the spellings "-", "_" and " " of a name, so "SHA-256", "sha256" and "SHA_256" are the same; rows keep
 * their own spelling. A raw value that is not in the dictionary has no entry and the caller reports UNKNOWN.
 */
public final class CanonicalDictionary {

    private final Map<CanonicalKind, Map<String, CanonicalEntry>> byKind = new HashMap<>();
    private final int size;

    public CanonicalDictionary(List<CanonicalEntry> entries) {
        for (CanonicalEntry entry : entries) {
            Map<String, CanonicalEntry> rows = byKind.computeIfAbsent(entry.kind(), k -> new HashMap<>());
            if (rows.putIfAbsent(normalize(entry.raw()), entry) != null) {
                throw new IllegalArgumentException("the dictionary has two rows for the same " + entry.kind() + " spelling");
            }
        }
        this.size = entries.size();
    }

    public Optional<CanonicalEntry> lookup(CanonicalKind kind, String raw) {
        if (raw == null) {
            return Optional.empty();
        }
        Map<String, CanonicalEntry> rows = byKind.get(kind);
        return rows == null ? Optional.empty() : Optional.ofNullable(rows.get(normalize(raw)));
    }

    public int size() {
        return size;
    }

    private static String normalize(String raw) {
        return raw.strip().toLowerCase(Locale.ROOT).replace("-", "").replace("_", "").replace(" ", "");
    }
}

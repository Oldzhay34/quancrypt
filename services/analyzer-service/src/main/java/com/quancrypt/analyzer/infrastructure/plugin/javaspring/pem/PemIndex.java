package com.quancrypt.analyzer.infrastructure.plugin.javaspring.pem;

import com.quancrypt.analyzer.domain.model.AlgorithmFamily;
import com.quancrypt.analyzer.domain.exception.PathNotAllowedException;
import com.quancrypt.analyzer.domain.model.RelativePath;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.TreeMap;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * The PEM files of a project. Private keys take algorithm and size from the public file with the same stem in the same
 * directory (x.key.pem next to x.crt.pem or x.pub.pem), because a private key is never parsed (D-185).
 */
public final class PemIndex {

    private static final Pattern PRIVATE_STEM = Pattern.compile("(.+?)(\\.key\\.pem|\\.key|-key\\.pem)");
    private static final List<String> PUBLIC_SUFFIXES = List.of(".crt.pem", ".cert.pem", ".pub.pem", ".crt", ".cer", ".pem", ".pub");

    private final Map<RelativePath, PemFacts> facts = new TreeMap<>((a, b) -> a.value().compareTo(b.value()));
    private final Map<RelativePath, PemFacts> counterparts = new TreeMap<>((a, b) -> a.value().compareTo(b.value()));

    public PemIndex(List<PemFacts> parsed) {
        List<PemFacts> privateKeys = new ArrayList<>();
        for (PemFacts fact : parsed) {
            facts.put(fact.file(), fact);
            if (fact.role() == PemRole.PRIVATE_KEY) {
                privateKeys.add(fact);
            }
        }
        for (PemFacts key : privateKeys) {
            Optional<PemFacts> counterpart = counterpartOf(key);
            counterpart.ifPresent(c -> counterparts.put(key.file(), c));
            PemFacts completed = counterpart.map(c -> key.withKey(key.family().or(c::family), c.keySizeBits())).orElse(key);
            facts.put(key.file(), completed);
        }
    }

    public Optional<PemFacts> get(RelativePath file) {
        return Optional.ofNullable(facts.get(file));
    }

    public List<PemFacts> all() {
        return List.copyOf(facts.values());
    }

    /** The public file (certificate or public key) that belongs to a private key file, when there is one. */
    public Optional<PemFacts> counterpart(RelativePath privateKey) {
        return Optional.ofNullable(counterparts.get(privateKey));
    }

    /** The unique PEM file with this base name anywhere in the project (configuration paths hold placeholders). */
    public Optional<PemFacts> byBasename(String basename) {
        List<PemFacts> matches = facts.values().stream().filter(f -> baseName(f.file()).equals(basename)).toList();
        return matches.size() == 1 ? Optional.of(matches.get(0)) : Optional.empty();
    }

    /** The family all certificates of the project agree on, empty when there is none or they differ. */
    public Optional<PemFacts> commonCertificateKey() {
        List<PemFacts> certs = facts.values().stream().filter(f -> f.role() == PemRole.CERTIFICATE && f.family().isPresent()).toList();
        if (certs.isEmpty()) {
            return Optional.empty();
        }
        AlgorithmFamily family = certs.get(0).family().get();
        boolean sameFamily = certs.stream().allMatch(c -> c.family().equals(Optional.of(family)));
        if (!sameFamily) {
            return Optional.empty();
        }
        Optional<Integer> size = certs.get(0).keySizeBits();
        boolean sameSize = certs.stream().allMatch(c -> c.keySizeBits().equals(size));
        return Optional.of(sameSize ? certs.get(0) : certs.get(0).withKey(Optional.of(family), Optional.empty()));
    }

    private Optional<PemFacts> counterpartOf(PemFacts key) {
        String name = baseName(key.file());
        Matcher matcher = PRIVATE_STEM.matcher(name);
        if (!matcher.matches()) {
            return Optional.empty();
        }
        String stem = matcher.group(1);
        String directory = directory(key.file());
        for (String suffix : PUBLIC_SUFFIXES) {
            RelativePath candidate = companionPath(directory, stem + suffix);
            PemFacts fact = candidate == null ? null : facts.get(candidate);
            if (fact != null && fact.role() != PemRole.PRIVATE_KEY && fact.role() != PemRole.OTHER) {
                return Optional.of(fact);
            }
        }
        return Optional.empty();
    }

    /** The path of a companion file, or null when the name would be too long to be a path the project can contain. */
    private static RelativePath companionPath(String directory, String name) {
        try {
            return RelativePath.of(directory.isEmpty() ? name : directory + "/" + name);
        } catch (PathNotAllowedException e) {
            return null;
        }
    }

    public static String baseName(RelativePath file) {
        List<String> segments = file.segments();
        return segments.get(segments.size() - 1);
    }

    private static String directory(RelativePath file) {
        String value = file.value();
        int slash = value.lastIndexOf('/');
        return slash < 0 ? "" : value.substring(0, slash);
    }
}

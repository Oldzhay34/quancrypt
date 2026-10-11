package com.quancrypt.analyzer.domain.policy;

import com.quancrypt.analyzer.domain.model.RelativePath;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/**
 * Files whose content is never served as a snippet (D-180): environment files, keystores (never opened, D-19) and
 * private key files. The decision is made on the file name alone, case-insensitively.
 */
public final class SensitiveFilePolicy {

    private static final List<String> KEYSTORE_SUFFIXES = List.of(".p12", ".pfx", ".jks", ".jceks", ".keystore", ".bks");
    private static final List<String> KEY_SUFFIXES = List.of(".key", ".key.pem", "-key.pem");
    private static final Set<String> SSH_KEYS = Set.of("id_rsa", "id_dsa", "id_ecdsa", "id_ed25519");

    public boolean isRefused(RelativePath path) {
        List<String> segments = path.segments();
        String name = segments.get(segments.size() - 1).toLowerCase(Locale.ROOT);
        return ".env".equals(name) || name.startsWith(".env.")
                || KEYSTORE_SUFFIXES.stream().anyMatch(name::endsWith)
                || KEY_SUFFIXES.stream().anyMatch(name::endsWith)
                || SSH_KEYS.contains(name);
    }
}

package com.quancrypt.analyzer.domain.policy;

import com.quancrypt.analyzer.domain.model.RelativePath;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/**
 * Files whose content is never served as a snippet (D-180, extended by D-205): environment files, keystores (never opened,
 * D-19), private key files (also the binary DER, PKCS#8 and PuTTY forms) and credential files (.netrc, .pgpass, .git-credentials,
 * the AWS credentials file). The decision is made on the file name alone, case-insensitively.
 */
public final class SensitiveFilePolicy {

    private static final List<String> KEYSTORE_SUFFIXES = List.of(".p12", ".pfx", ".jks", ".jceks", ".keystore", ".bks");
    private static final List<String> KEY_SUFFIXES = List.of(".key", ".key.pem", "-key.pem", ".ppk", ".p8", ".pk8", ".der");
    private static final Set<String> SSH_KEYS = Set.of("id_rsa", "id_dsa", "id_ecdsa", "id_ed25519");
    private static final Set<String> CREDENTIAL_FILES = Set.of(".netrc", "_netrc", ".pgpass", ".git-credentials", "credentials");

    public boolean isRefused(RelativePath path) {
        List<String> segments = path.segments();
        String name = segments.get(segments.size() - 1).toLowerCase(Locale.ROOT);
        return ".env".equals(name) || name.startsWith(".env.")
                || KEYSTORE_SUFFIXES.stream().anyMatch(name::endsWith)
                || KEY_SUFFIXES.stream().anyMatch(name::endsWith)
                || SSH_KEYS.contains(name)
                || CREDENTIAL_FILES.contains(name);
    }
}

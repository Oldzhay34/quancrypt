package com.quancrypt.analyzer.infrastructure.plugin.javaspring.topology;

import com.quancrypt.analyzer.domain.model.GroupFamily;
import com.quancrypt.analyzer.domain.model.KeyExchange;
import java.util.List;
import java.util.Locale;
import java.util.Optional;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * What a Java version offers as TLS 1.3 key exchange groups when nothing names them (D-210, D-213). Sources, read on
 * 2026-10-15: the default list of OpenJDK {@code jdk-25.0.4-ga} ({@code sun/security/ssl/NamedGroup.java}, class
 * {@code SupportedGroups}) and JEP 527 for JDK 27 ({@code X25519MLKEM768} first). A later JDK 25 update (the {@code jdk25u}
 * development branch already lists {@code X25519MLKEM768} first) can differ from 25.0.4 and the project's version only says
 * the feature release, so JDK 25 has the lowest confidence. Other versions below 27 are classical (crypto-domain); their group
 * order was not checked and is not written. The confidences are judgements, not measurements.
 */
final class JdkTlsDefaults {

    private static final Pattern MAJOR = Pattern.compile("^(?:1\\.)?(\\d{1,3})(?:[.\\-+_].*)?$");
    private static final List<String> JDK_25 = List.of("x25519", "secp256r1", "secp384r1", "secp521r1", "x448", "ffdhe2048", "ffdhe3072",
            "ffdhe4096", "ffdhe6144", "ffdhe8192");
    private static final List<String> JDK_27 = List.of("X25519MLKEM768", "x25519", "secp256r1", "secp384r1", "secp521r1", "x448", "ffdhe2048",
            "ffdhe3072", "ffdhe4096");

    private JdkTlsDefaults() {
    }

    /** The inferred key exchange for a Java version; empty when the version is unknown or not a number. */
    static Optional<KeyExchange> inferred(Optional<String> javaVersion) {
        return javaVersion.flatMap(JdkTlsDefaults::major).map(major -> {
            if (major == 27) {
                return new KeyExchange(GroupFamily.HYBRID, JDK_27, true, 0.6);
            }
            if (major > 27) {
                // JEP 527 is about JDK 27; that a later release keeps the default is not checked, so no groups and a lower confidence
                return new KeyExchange(GroupFamily.HYBRID, List.of(), true, 0.4);
            }
            if (major == 25) {
                return new KeyExchange(GroupFamily.CLASSICAL, JDK_25, true, 0.5);
            }
            return new KeyExchange(GroupFamily.CLASSICAL, List.of(), true, 0.6);
        });
    }

    /** The key exchange of groups the code or the configuration names (a {@code jdk.tls.namedGroups} list): not an inference. */
    static Optional<KeyExchange> named(String list, Optional<String> javaVersion) {
        List<String> groups = java.util.Arrays.stream(list.split(",")).map(String::strip).filter(g -> g.matches("[A-Za-z0-9_-]{1,32}")).toList();
        if (groups.isEmpty()) {
            return Optional.empty();
        }
        boolean hybrid = groups.stream().anyMatch(g -> g.toUpperCase(Locale.ROOT).contains("MLKEM"));
        // a hybrid group named for a Java version that does not have it (JDK 25.0.4 has none, D-213) may be ignored by the JDK
        boolean maybeUnsupported = hybrid && javaVersion.flatMap(JdkTlsDefaults::major).filter(major -> major < 27).isPresent();
        return Optional.of(new KeyExchange(hybrid ? GroupFamily.HYBRID : GroupFamily.CLASSICAL, groups.subList(0, Math.min(groups.size(), KeyExchange.MAX_GROUPS)),
                false, maybeUnsupported ? 0.5 : 0.9));
    }

    private static Optional<Integer> major(String version) {
        Matcher matcher = MAJOR.matcher(version.strip());
        return matcher.matches() ? Optional.of(Integer.parseInt(matcher.group(1))) : Optional.empty();
    }
}

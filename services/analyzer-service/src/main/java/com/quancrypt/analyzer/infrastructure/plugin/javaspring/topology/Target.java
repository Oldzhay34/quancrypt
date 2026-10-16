package com.quancrypt.analyzer.infrastructure.plugin.javaspring.topology;

import com.quancrypt.analyzer.domain.model.NodeKind;
import com.quancrypt.analyzer.domain.model.Protocol;
import java.util.Locale;
import java.util.Optional;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Where a connection goes, as written in a URL, a host and port or a service name. User information of a URL is dropped on
 * the way in (it may be a secret and never reaches a node name). {@code port} is -1 when none is written.
 */
public record Target(String host, int port, String scheme) {

    // The user information runs to the LAST '@' of the authority and the host cannot hold an '@': a password with an unescaped '@'
    // is dropped whole, and what cannot be read as an authority is no target at all (a secret never becomes a node name).
    private static final Pattern URL = Pattern.compile("^([A-Za-z][A-Za-z0-9+.-]{0,15}):(?://)?(?:[^/?#\\s]{0,256}@)?(\\[[0-9A-Fa-f:.]{2,45}]|[^/:?#@\\s]{1,253})(?::(\\d{1,5}))?(?:[/?#].*)?$");
    private static final Pattern JDBC = Pattern.compile("^jdbc:([A-Za-z0-9]{1,16}):(?://)?(?:[^/?#;\\s]{0,256}@)?(\\[[0-9A-Fa-f:.]{2,45}]|[^/:?#;@\\s]{1,253})(?::(\\d{1,5}))?(?:[/?#;].*)?$");
    private static final Pattern HOST_PORT = Pattern.compile("^(?:[^/?#\\s]{0,256}@)?(\\[[0-9A-Fa-f:.]{2,45}]|[A-Za-z0-9][A-Za-z0-9._-]{0,252}):(\\d{1,5})$");
    private static final int MAX_LENGTH = 2048;
    private static final Set<String> TLS_SCHEMES = Set.of("https", "wss", "ssl", "mqtts", "tcps", "amqps", "grpcs", "kafkas");
    private static final Set<String> IGNORED_SCHEMES = Set.of("file", "classpath", "jar", "http+unix", "data", "mailto");

    /** The target of a URL ({@code scheme://host[:port]/..}, also {@code jdbc:db://host:port/..}). */
    public static Optional<Target> ofUrl(String value) {
        String text = value.strip();
        if (text.length() > MAX_LENGTH) {
            return Optional.empty();
        }
        Matcher jdbc = JDBC.matcher(text);
        if (jdbc.matches()) {
            return Optional.of(new Target(host(jdbc.group(2)), port(jdbc.group(3)), "jdbc"));
        }
        Matcher url = URL.matcher(text);
        if (!url.matches() || !text.contains(":")) {
            return Optional.empty();
        }
        if (ambiguousAuthority(text)) {
            return Optional.empty();
        }
        String scheme = url.group(1).toLowerCase(Locale.ROOT);
        if (IGNORED_SCHEMES.contains(scheme) || !text.regionMatches(scheme.length(), ":", 0, 1)) {
            return Optional.empty();
        }
        if (!text.startsWith(url.group(1) + "://") && !scheme.equals("lb")) {
            return Optional.empty();
        }
        return Optional.of(new Target(host(url.group(2)), port(url.group(3)), scheme));
    }

    /** The target of {@code host:port} (a bootstrap server, a broker address). */
    public static Optional<Target> ofHostPort(String value) {
        if (value.length() > MAX_LENGTH) {
            return Optional.empty();
        }
        Matcher matcher = HOST_PORT.matcher(value.strip());
        if (!matcher.matches()) {
            return Optional.empty();
        }
        return Optional.of(new Target(host(matcher.group(1)), port(matcher.group(2)), ""));
    }

    /** A host or service name without a port. */
    public static Optional<Target> ofName(String name) {
        String text = name.strip();
        return text.matches("[A-Za-z0-9][A-Za-z0-9._-]{0,252}") ? Optional.of(new Target(text.toLowerCase(Locale.ROOT), -1, "")) : Optional.empty();
    }

    /** Whether the scheme itself says the connection is encrypted. */
    public boolean secureScheme() {
        return TLS_SCHEMES.contains(scheme);
    }

    /** The protocol a scheme stands for; empty for a scheme that is not a connection scheme. */
    public Optional<Protocol> protocol() {
        return switch (scheme) {
            case "http", "https", "ws", "wss", "lb" -> Optional.of(Protocol.HTTP);
            case "ssl", "tcp", "tcps", "mqtt", "mqtts" -> Optional.of(Protocol.MQTT);
            case "amqp", "amqps" -> Optional.of(Protocol.AMQP);
            case "grpc", "grpcs" -> Optional.of(Protocol.GRPC);
            case "kafka", "kafkas" -> Optional.of(Protocol.KAFKA);
            case "jdbc" -> Optional.of(Protocol.OTHER);
            default -> Optional.empty();
        };
    }

    /** What an endpoint reached by this scheme is: a database for jdbc, a broker for the messaging schemes, else unknown. */
    public NodeKind impliedKind() {
        return switch (scheme) {
            case "jdbc" -> NodeKind.DATABASE;
            case "ssl", "tcp", "tcps", "mqtt", "mqtts", "amqp", "amqps", "kafka", "kafkas" -> NodeKind.BROKER;
            default -> NodeKind.EXTERNAL;
        };
    }

    public boolean local() {
        return host.isEmpty() || host.equals("localhost") || host.equals("127.0.0.1") || host.equals("::1") || host.equals("[::1]")
                || host.equals("0.0.0.0");
    }

    /** An '@' both in the authority and after it: where the user information ends is a guess, so the text is no target. */
    private static boolean ambiguousAuthority(String text) {
        int start = text.indexOf("://");
        String rest = start < 0 ? text : text.substring(start + 3);
        int end = 0;
        while (end < rest.length() && "/?#".indexOf(rest.charAt(end)) < 0) {
            end++;
        }
        return rest.substring(0, end).indexOf('@') >= 0 && rest.substring(end).indexOf('@') >= 0;
    }

    private static String host(String raw) {
        return raw.toLowerCase(Locale.ROOT);
    }

    private static int port(String raw) {
        if (raw == null) {
            return -1;
        }
        int port = Integer.parseInt(raw);
        return port > 0 && port <= 65535 ? port : -1;
    }
}

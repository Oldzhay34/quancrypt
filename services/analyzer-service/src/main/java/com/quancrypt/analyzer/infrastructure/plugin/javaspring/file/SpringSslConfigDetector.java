package com.quancrypt.analyzer.infrastructure.plugin.javaspring.file;

import com.quancrypt.analyzer.domain.model.AlgorithmFamily;
import com.quancrypt.analyzer.domain.model.CanonicalEntry;
import com.quancrypt.analyzer.domain.model.CanonicalKind;
import com.quancrypt.analyzer.domain.model.CanonicalNames;
import com.quancrypt.analyzer.domain.model.CryptoAlgorithm;
import com.quancrypt.analyzer.domain.model.UsageContext;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.CodeSupport;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.CryptoDetector;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.DetectionSink;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.FileContext;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.FileKind;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.FileSupport;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.ProjectFile;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.ProjectIndex;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.TlsIdentity;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.config.ConfigProperty;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.ssl.SslBundle;
import java.util.Locale;
import java.util.Optional;
import java.util.regex.Pattern;

/**
 * TLS settings of Spring Boot configuration (YAML and .properties, every profile): {@code server.ssl.*}, SSL bundles
 * ({@code spring.ssl.bundle.pem.*} and {@code .jks.*}), client side bundle references (any {@code ...ssl.bundle} or
 * {@code ssl-bundle} key), client authentication, protocols, and https/ssl URLs the application connects to. A bundle used by
 * {@code server.ssl.bundle} is the server's certificate (CERTIFICATE), any other bundle with a keystore is a client identity
 * (MTLS_CLIENT_AUTH); the key is read from the bundle's certificate file.
 */
public final class SpringSslConfigDetector implements CryptoDetector {

    public static final String ID = "spring.ssl-config";
    private static final String LIBRARY = "spring-boot";
    private static final Pattern TLS_URL = Pattern.compile("^(https|ssl|tcps|wss|mqtts|amqps)://[^\\s/]");
    private static final Pattern BUNDLE_REFERENCE = Pattern.compile(".*\\bssl[.-]bundle$");

    private final CanonicalNames names;

    public SpringSslConfigDetector(CanonicalNames names) {
        this.names = names;
    }

    @Override
    public String detectorId() {
        return ID;
    }

    @Override
    public boolean appliesTo(ProjectFile file) {
        return file.kind() == FileKind.SPRING_YAML || file.kind() == FileKind.SPRING_PROPERTIES;
    }

    @Override
    public void detect(ProjectIndex index, FileContext context, DetectionSink sink) {
        ProjectFile file = context.file();
        for (ConfigProperty property : index.config().of(file.path())) {
            String key = property.key();
            String value = index.config().resolved(property.value()).strip();
            if (BUNDLE_REFERENCE.matcher(key).matches() && !value.isEmpty()) {
                sink.add(FileSupport.tls(file, property.line(), key, index.identityOf(value), "SslBundle", null, ID, LIBRARY));
            } else if (key.equals("server.ssl.client-auth") && isRequired(value)) {
                sink.add(FileSupport.identityUsage(file, property.line(), key, serverIdentity(index), "client-auth:" + value.toLowerCase(Locale.ROOT),
                        UsageContext.MTLS_CLIENT_AUTH, ID, LIBRARY));
            } else if (key.equals("server.ssl.protocol") || key.equals("server.ssl.enabled-protocols") || key.startsWith("server.ssl.enabled-protocols[")) {
                protocol(index, file, property, value, sink);
            } else if (key.equals("server.ssl.key-store") || key.equals("server.ssl.trust-store")) {
                sink.add(FileSupport.atLine(file, property.line(), key, new CryptoAlgorithm(AlgorithmFamily.UNKNOWN, "server.ssl keystore",
                        Optional.empty(), Optional.empty(), Optional.empty(), Optional.empty()), UsageContext.KEYSTORE, 0.9, ID, LIBRARY));
            } else if (key.equals("server.ssl.certificate")) {
                sink.add(FileSupport.identityUsage(file, property.line(), key, index.identityOfFile(value), "server certificate",
                        UsageContext.CERTIFICATE, ID, LIBRARY));
            } else if (!key.startsWith("spring.ssl.bundle.") && TLS_URL.matcher(value).lookingAt()) {
                String scheme = value.substring(0, value.indexOf("://") + 3);
                sink.add(FileSupport.tls(file, property.line(), key, index.defaultIdentity(), scheme, null, ID, LIBRARY));
            }
        }
        for (SslBundle bundle : index.bundles().all()) {
            if (bundle.file().equals(file.path())) {
                bundle(index, file, bundle, sink);
            }
        }
    }

    private void bundle(ProjectIndex index, ProjectFile file, SslBundle bundle, DetectionSink sink) {
        String symbol = "spring.ssl.bundle." + bundle.type() + "." + bundle.name();
        if (bundle.isJks()) {
            sink.add(FileSupport.atLine(file, bundle.line(), symbol, new CryptoAlgorithm(AlgorithmFamily.UNKNOWN, "JKS bundle " + CodeSupport.nameShaped(bundle.name()),
                    Optional.empty(), Optional.empty(), Optional.empty(), Optional.empty()), UsageContext.KEYSTORE, 0.9, ID, LIBRARY));
            return;
        }
        if (!bundle.hasIdentity()) {
            return;
        }
        UsageContext usage = index.bundles().isServerBundle(bundle.name()) ? UsageContext.CERTIFICATE : UsageContext.MTLS_CLIENT_AUTH;
        sink.add(FileSupport.identityUsage(file, bundle.line(), symbol, index.identityOf(bundle.name()), "SslBundle " + CodeSupport.nameShaped(bundle.name()), usage,
                ID, LIBRARY));
    }

    private void protocol(ProjectIndex index, ProjectFile file, ConfigProperty property, String value, DetectionSink sink) {
        Optional<CanonicalEntry> entry = names.entry(CanonicalKind.TLS_PROTOCOL, value);
        if (entry.isEmpty()) {
            sink.unresolved(ID, value);
            return;
        }
        sink.add(FileSupport.tls(file, property.line(), property.key(), index.defaultIdentity(), "protocol:" + value,
                entry.get().mode().orElse(null), ID, LIBRARY));
    }

    private static TlsIdentity serverIdentity(ProjectIndex index) {
        return index.config().value("server.ssl.bundle").map(index.config()::resolved).map(index::identityOf)
                .orElseGet(index::defaultIdentity);
    }

    private static boolean isRequired(String value) {
        String lower = value.toLowerCase(Locale.ROOT);
        return lower.equals("need") || lower.equals("want");
    }
}

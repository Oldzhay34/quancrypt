package com.quancrypt.analyzer.infrastructure.plugin.javaspring.file;

import com.quancrypt.analyzer.domain.model.CanonicalKind;
import com.quancrypt.analyzer.domain.model.CanonicalNames;
import com.quancrypt.analyzer.domain.model.CryptoAlgorithm;
import com.quancrypt.analyzer.domain.model.UsageContext;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.CryptoDetector;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.DetectionSink;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.FileContext;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.FileKind;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.FileSupport;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.ProjectFile;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.ProjectIndex;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.config.ConfigProperty;
import java.util.List;
import java.util.Optional;

/**
 * {@code spring.security.oauth2.resourceserver.jwt.*}: the accepted signature algorithms ({@code jws-algorithms}); a
 * JWT resource server configured by key source only ({@code jwk-set-uri}, {@code issuer-uri},
 * {@code public-key-location}) uses Spring's documented default RS256.
 */
public final class SpringJwtConfigDetector implements CryptoDetector {

    public static final String ID = "spring.jwt-config";
    private static final String LIBRARY = "spring-security-oauth2-jose";
    private static final String PREFIX = "spring.security.oauth2.resourceserver.jwt.";
    private static final List<String> KEY_SOURCES = List.of(PREFIX + "jwk-set-uri", PREFIX + "issuer-uri", PREFIX + "public-key-location");

    private final CanonicalNames names;

    public SpringJwtConfigDetector(CanonicalNames names) {
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
        List<ConfigProperty> properties = index.config().of(file.path());
        boolean explicit = false;
        for (ConfigProperty property : properties) {
            if (property.key().equals(PREFIX + "jws-algorithms") || property.key().startsWith(PREFIX + "jws-algorithms[")) {
                explicit = true;
                for (String raw : index.config().resolved(property.value()).split(",")) {
                    emit(file, property, raw.strip(), 0.9, sink);
                }
            }
        }
        if (!explicit) {
            properties.stream().filter(p -> KEY_SOURCES.contains(p.key())).findFirst()
                    .ifPresent(property -> emit(file, property, "RS256", 0.6, sink));
        }
    }

    private void emit(ProjectFile file, ConfigProperty property, String raw, double confidence, DetectionSink sink) {
        Optional<CryptoAlgorithm> algorithm = names.algorithm(CanonicalKind.JWT_ALG, raw);
        if (algorithm.isEmpty()) {
            sink.unresolved(ID, raw);
            return;
        }
        sink.add(FileSupport.atLine(file, property.line(), property.key(), algorithm.get(), UsageContext.TOKEN_SIGNATURE, confidence, ID, LIBRARY));
    }
}

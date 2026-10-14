package com.quancrypt.analyzer.infrastructure.plugin.javaspring.file;

import com.quancrypt.analyzer.domain.model.CanonicalEntry;
import com.quancrypt.analyzer.domain.model.CanonicalKind;
import com.quancrypt.analyzer.domain.model.CanonicalNames;
import com.quancrypt.analyzer.domain.model.UsageContext;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.CryptoDetector;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.DetectionSink;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.FileContext;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.FileKind;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.FileSupport;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.ProjectFile;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.ProjectIndex;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.TlsIdentity;
import java.util.List;
import java.util.Locale;
import java.util.Optional;

/**
 * The TLS settings of a Mosquitto broker configuration (D-184): {@code certfile} (the broker's certificate and so the key
 * of its TLS), {@code require_certificate true} (mutual TLS) and {@code tls_version}. The format is one setting per line,
 * the key first, then the value; lines starting with # are comments.
 */
public final class MosquittoConfigDetector implements CryptoDetector {

    public static final String ID = "mosquitto.config";
    private static final String LIBRARY = "mosquitto";

    private final CanonicalNames names;

    public MosquittoConfigDetector(CanonicalNames names) {
        this.names = names;
    }

    @Override
    public String detectorId() {
        return ID;
    }

    @Override
    public boolean appliesTo(ProjectFile file) {
        return file.kind() == FileKind.MOSQUITTO_CONF;
    }

    @Override
    public void detect(ProjectIndex index, FileContext context, DetectionSink sink) {
        ProjectFile file = context.file();
        List<String> lines = index.lines(file.path());
        TlsIdentity identity = index.defaultIdentity();
        for (int i = 0; i < lines.size(); i++) {
            String line = lines.get(i).strip();
            if (line.isEmpty() || line.startsWith("#")) {
                continue;
            }
            String[] parts = line.split("\\s+", 2);
            if (parts.length < 2) {
                continue;
            }
            if (parts[0].equals("certfile")) {
                identity = index.identityOfFile(parts[1].strip());
            }
        }
        for (int i = 0; i < lines.size(); i++) {
            String line = lines.get(i).strip();
            String[] parts = line.split("\\s+", 2);
            if (line.isEmpty() || line.startsWith("#") || parts.length < 2) {
                continue;
            }
            String value = parts[1].strip();
            switch (parts[0]) {
                case "certfile" -> sink.add(FileSupport.tls(file, i + 1, "certfile", index.identityOfFile(value), "certfile", null, ID, LIBRARY));
                case "require_certificate" -> {
                    if (value.equalsIgnoreCase("true")) {
                        sink.add(FileSupport.identityUsage(file, i + 1, "require_certificate", identity, "require_certificate",
                                UsageContext.MTLS_CLIENT_AUTH, ID, LIBRARY));
                    }
                }
                case "tls_version" -> {
                    Optional<CanonicalEntry> protocol = names.entry(CanonicalKind.TLS_PROTOCOL, value.toLowerCase(Locale.ROOT));
                    if (protocol.isPresent()) {
                        sink.add(FileSupport.tls(file, i + 1, "tls_version", identity, "protocol:" + value, protocol.get().mode().orElse(null),
                                ID, LIBRARY));
                    } else {
                        sink.unresolved(ID, value);
                    }
                }
                default -> {
                }
            }
        }
    }
}

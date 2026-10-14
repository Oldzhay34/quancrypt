package com.quancrypt.analyzer.infrastructure.plugin.javaspring;

import com.quancrypt.analyzer.domain.model.RelativePath;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.config.ConfigIndex;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.pem.PemFacts;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.pem.PemIndex;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.pem.PemRole;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.ssl.SslBundle;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.ssl.SslBundleIndex;
import com.quancrypt.analyzer.port.outbound.SourceTree;
import java.util.List;
import java.util.Optional;

/**
 * What the first pass learned about the project, shared by every detector in the second pass: the files, the
 * configuration, the PEM files and the SSL bundles, and from them the key a TLS connection authenticates with.
 */
public final class ProjectIndex {

    private final SourceTree tree;
    private final List<ProjectFile> files;
    private final ConfigIndex config;
    private final PemIndex pem;
    private final SslBundleIndex bundles;

    public ProjectIndex(SourceTree tree, List<ProjectFile> files, ConfigIndex config, PemIndex pem, SslBundleIndex bundles) {
        this.tree = tree;
        this.files = List.copyOf(files);
        this.config = config;
        this.pem = pem;
        this.bundles = bundles;
    }

    public SourceTree tree() {
        return tree;
    }

    public List<ProjectFile> files() {
        return files;
    }

    public ConfigIndex config() {
        return config;
    }

    public PemIndex pem() {
        return pem;
    }

    public SslBundleIndex bundles() {
        return bundles;
    }

    public List<String> lines(RelativePath path) {
        return tree.readLines(path);
    }

    /** The key of a bundle's own certificate, or of the certificate it trusts when it has no identity. */
    public TlsIdentity identityOf(String bundleName) {
        Optional<SslBundle> bundle = bundles.get(bundleName);
        if (bundle.isEmpty()) {
            return defaultIdentity();
        }
        List<String> references = bundle.get().hasIdentity() ? bundle.get().keystoreReferences() : bundle.get().truststoreReferences();
        for (String reference : references) {
            Optional<PemFacts> certificate = pem.byBasename(basename(reference)).filter(f -> f.role() == PemRole.CERTIFICATE);
            if (certificate.isPresent() && certificate.get().family().isPresent()) {
                return new TlsIdentity(certificate.get().family(), certificate.get().keySizeBits(), true);
            }
        }
        return defaultIdentity();
    }

    /** The key all certificates of the project share, as a guess; unknown when they differ or there are none. */
    public TlsIdentity defaultIdentity() {
        return pem.commonCertificateKey().map(f -> new TlsIdentity(f.family(), f.keySizeBits(), false)).orElse(TlsIdentity.UNKNOWN);
    }

    /** The identity of a certificate file named in configuration (placeholders and directories are ignored). */
    public TlsIdentity identityOfFile(String reference) {
        Optional<PemFacts> certificate = pem.byBasename(basename(reference)).filter(f -> f.family().isPresent());
        return certificate.map(f -> new TlsIdentity(f.family(), f.keySizeBits(), true)).orElseGet(this::defaultIdentity);
    }

    public static String basename(String reference) {
        String cleaned = reference.strip();
        int colon = cleaned.indexOf(':');
        if (colon >= 0 && colon < 12 && !cleaned.startsWith("$")) {
            cleaned = cleaned.substring(colon + 1);
        }
        int slash = Math.max(cleaned.lastIndexOf('/'), cleaned.lastIndexOf('\\'));
        return slash < 0 ? cleaned : cleaned.substring(slash + 1);
    }
}

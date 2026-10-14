package com.quancrypt.analyzer.infrastructure.cbom;

import com.quancrypt.analyzer.domain.model.AlgorithmFamily;
import com.quancrypt.analyzer.domain.model.CryptoAlgorithm;
import com.quancrypt.analyzer.domain.model.CryptoUsage;
import com.quancrypt.analyzer.domain.model.LocationKind;
import com.quancrypt.analyzer.domain.model.UsageContext;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.TreeMap;
import org.cyclonedx.model.Component;
import org.cyclonedx.model.Evidence;
import org.cyclonedx.model.component.crypto.AlgorithmProperties;
import org.cyclonedx.model.component.crypto.CryptoProperties;
import org.cyclonedx.model.component.crypto.ProtocolProperties;
import org.cyclonedx.model.component.crypto.RelatedCryptoMaterialProperties;
import org.cyclonedx.model.component.crypto.enums.AssetType;
import org.cyclonedx.model.component.crypto.enums.Primitive;
import org.cyclonedx.model.component.crypto.enums.ProtocolType;
import org.cyclonedx.model.component.crypto.enums.RelatedCryptoMaterialType;
import org.cyclonedx.model.component.evidence.Occurrence;

/**
 * Turns usages into the cryptographic-asset components of a CBOM (D-195 to D-197, D-202). Every usage is an occurrence of
 * the algorithm component it uses, so each component names where it was seen; a certificate usage also appears under a
 * certificate component, a TLS usage under a protocol component that refers to the algorithm, and a keystore (whose
 * content is never opened, D-19) is a related-crypto-material component only. Components are keyed by a stable
 * {@code bom-ref}, so the same algorithm used in many places is one component with many occurrences.
 */
final class ComponentCatalog {

    private static final Set<UsageContext> TLS = Set.of(UsageContext.TLS_KEY_EXCHANGE, UsageContext.TLS_SERVER_AUTH,
            UsageContext.MTLS_CLIENT_AUTH);

    private final Map<String, Component> components = new TreeMap<>();
    private final Map<String, Set<String>> occurrenceKeys = new TreeMap<>();

    void add(CryptoUsage usage) {
        if (usage.usageContext() == UsageContext.KEYSTORE) {
            occurrence(material("keystore:" + place(usage), label(usage), RelatedCryptoMaterialType.OTHER), usage);
            return;
        }
        boolean tls = TLS.contains(usage.usageContext());
        Component algorithm = algorithm(usage, tls);
        occurrence(algorithm, usage);
        if (usage.usageContext() == UsageContext.CERTIFICATE && isPrivateKeyFile(usage)) {
            // A private key that belongs to a certificate shares its usage (D-185) but is key material, not a certificate.
            occurrence(material("key:" + place(usage), label(usage), RelatedCryptoMaterialType.PRIVATE_KEY), usage);
        } else if (usage.usageContext() == UsageContext.CERTIFICATE) {
            occurrence(certificate("cert:" + place(usage), label(usage)), usage);
        } else if (tls) {
            Component protocol = protocol(usage);
            occurrence(protocol, usage);
            List<String> refs = protocol.getCryptoProperties().getProtocolProperties().getCryptoRefArray();
            if (!refs.contains(algorithm.getBomRef())) {
                refs.add(algorithm.getBomRef());
            }
        }
    }

    /** The components in bom-ref order, so the same usages always give the same document. */
    List<Component> components() {
        return new ArrayList<>(components.values());
    }

    private Component algorithm(CryptoUsage usage, boolean tls) {
        CryptoAlgorithm a = usage.algorithm();
        // For a TLS usage the mode field carries the protocol version, which belongs to the protocol component.
        Optional<String> mode = tls ? Optional.empty() : a.mode().filter(m -> !m.equals("NONE"));
        Optional<String> padding = a.padding().filter(p -> !p.equals("NONE"));
        Primitive primitive = AlgorithmMapping.primitive(a.family(), usage.usageContext(), mode);
        // The same RSA key can sign in one place and encrypt in another; each is its own component, so none is mislabeled.
        boolean ambiguous = a.family() == AlgorithmFamily.RSA && primitive != Primitive.UNKNOWN;
        String name = algorithmName(a, mode, padding) + (ambiguous ? "/" + primitive.getName() : "");
        return components.computeIfAbsent("alg:" + name, ref -> {
            Component component = base(ref, name);
            AlgorithmProperties properties = new AlgorithmProperties();
            properties.setPrimitive(primitive);
            AlgorithmMapping.mode(mode).ifPresent(properties::setMode);
            AlgorithmMapping.padding(padding).ifPresent(properties::setPadding);
            a.keySizeBits().ifPresent(bits -> properties.setParameterSetIdentifier(Integer.toString(bits)));
            AlgorithmMapping.nistQuantumSecurityLevel(a.family()).ifPresent(properties::setNistQuantumSecurityLevel);
            CryptoProperties crypto = new CryptoProperties();
            crypto.setAssetType(AssetType.ALGORITHM);
            crypto.setAlgorithmProperties(properties);
            component.setCryptoProperties(crypto);
            return component;
        });
    }

    private static String algorithmName(CryptoAlgorithm a, Optional<String> mode, Optional<String> padding) {
        if (a.family() == AlgorithmFamily.UNKNOWN) {
            return "unknown:" + a.rawName();
        }
        StringBuilder name = new StringBuilder(a.family().name());
        a.keySizeBits().ifPresent(bits -> name.append('-').append(bits));
        mode.ifPresent(m -> name.append('/').append(m));
        padding.ifPresent(p -> name.append('/').append(p));
        // SHA1 and MD5 are their own digest; SHA2 and SHA3 need the digest size to be told apart.
        a.hash().filter(h -> a.family() != AlgorithmFamily.SHA1 && a.family() != AlgorithmFamily.MD5).ifPresent(h -> name.append('/').append(h));
        return name.toString();
    }

    private Component certificate(String ref, String name) {
        return components.computeIfAbsent(ref, r -> {
            Component component = base(r, name);
            CryptoProperties crypto = new CryptoProperties();
            crypto.setAssetType(AssetType.CERTIFICATE);
            component.setCryptoProperties(crypto);
            return component;
        });
    }

    private Component material(String ref, String name, RelatedCryptoMaterialType type) {
        return components.computeIfAbsent(ref, r -> {
            Component component = base(r, name);
            RelatedCryptoMaterialProperties properties = new RelatedCryptoMaterialProperties();
            properties.setType(type);
            CryptoProperties crypto = new CryptoProperties();
            crypto.setAssetType(AssetType.RELATED_CRYPTO_MATERIAL);
            crypto.setRelatedCryptoMaterialProperties(properties);
            component.setCryptoProperties(crypto);
            return component;
        });
    }

    private Component protocol(CryptoUsage usage) {
        Optional<String> version = usage.algorithm().mode()
                .filter(m -> m.startsWith("TLS") || m.startsWith("SSL") || m.startsWith("DTLS"));
        String name = version.orElse("TLS");
        return components.computeIfAbsent("proto:" + name, ref -> {
            Component component = base(ref, name);
            ProtocolProperties properties = new ProtocolProperties();
            properties.setType(ProtocolType.TLS);
            version.ifPresent(properties::setVersion);
            properties.setCryptoRefArray(new ArrayList<>());
            CryptoProperties crypto = new CryptoProperties();
            crypto.setAssetType(AssetType.PROTOCOL);
            crypto.setProtocolProperties(properties);
            component.setCryptoProperties(crypto);
            return component;
        });
    }

    private static Component base(String ref, String name) {
        Component component = new Component();
        component.setType(Component.Type.CRYPTOGRAPHIC_ASSET);
        component.setBomRef(ref);
        component.setName(name);
        component.setEvidence(new Evidence());
        return component;
    }

    private void occurrence(Component component, CryptoUsage usage) {
        Occurrence occurrence = new Occurrence();
        occurrence.setLocation(usage.evidence().file().value());
        usage.evidence().lines().ifPresent(lines -> occurrence.setLine(lines.start()));
        occurrence.setSymbol(usage.symbol());
        String key = occurrence.getLocation() + ":" + occurrence.getLine() + ":" + occurrence.getSymbol();
        if (occurrenceKeys.computeIfAbsent(component.getBomRef(), ref -> new HashSet<>()).add(key)) {
            component.getEvidence().addOccurrence(occurrence);
        }
    }

    /** The PEM scanner names a key file by the label of its header (never by its file name), for example "PRIVATE KEY". */
    private static boolean isPrivateKeyFile(CryptoUsage usage) {
        return usage.detectorId().equals("pem.certificate") && usage.algorithm().rawName().contains("PRIVATE KEY");
    }

    private static boolean wholeFile(CryptoUsage usage) {
        return usage.evidence().locationKind() == LocationKind.CERTIFICATE_FILE
                || usage.evidence().locationKind() == LocationKind.KEYSTORE_FILE;
    }

    /** A certificate or keystore file is identified by its path; one named inside a configuration file by its symbol too. */
    private static String place(CryptoUsage usage) {
        String file = usage.evidence().file().value();
        return wholeFile(usage) ? file : file + "#" + usage.symbol();
    }

    private static String label(CryptoUsage usage) {
        if (!wholeFile(usage)) {
            return usage.symbol();
        }
        String file = usage.evidence().file().value();
        return file.substring(file.lastIndexOf('/') + 1);
    }
}

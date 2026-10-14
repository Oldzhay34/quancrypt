package com.quancrypt.analyzer.infrastructure.plugin.javaspring.pem;

import com.quancrypt.analyzer.domain.model.AlgorithmFamily;
import com.quancrypt.analyzer.domain.model.CanonicalKind;
import com.quancrypt.analyzer.domain.model.CanonicalNames;
import com.quancrypt.analyzer.domain.model.CryptoAlgorithm;
import com.quancrypt.analyzer.domain.model.RelativePath;
import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyFactory;
import java.security.PublicKey;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;
import java.security.interfaces.DSAPublicKey;
import java.security.interfaces.ECPublicKey;
import java.security.interfaces.RSAPublicKey;
import java.security.spec.X509EncodedKeySpec;
import java.util.Base64;
import java.util.List;
import java.util.Optional;
import javax.crypto.interfaces.DHPublicKey;

/**
 * Reads the facts of a PEM file. Certificates and public keys are parsed with the JDK; a private key (any label that
 * names a private key) is recognised from its header line only and its content is never decoded. A block ends at the next
 * BEGIN line as well as at an END line, so a block without an END line never reaches into a private key that follows it.
 */
public final class PemReader {

    private static final List<String> PUBLIC_KEY_ALGORITHMS = List.of("RSA", "EC", "Ed25519", "X25519", "DSA", "DH", "ML-DSA", "ML-KEM");

    private final CanonicalNames names;

    public PemReader(CanonicalNames names) {
        this.names = names;
    }

    /** The facts, or empty when the text is not PEM at all. */
    public Optional<PemFacts> read(RelativePath file, List<String> lines) {
        int begin = -1;
        String label = null;
        for (int i = 0; i < lines.size() && i < 50; i++) {
            String line = lines.get(i).strip();
            if (line.startsWith("-----BEGIN ") && line.endsWith("-----")) {
                begin = i;
                label = line.substring("-----BEGIN ".length(), line.length() - "-----".length());
                break;
            }
        }
        if (label == null) {
            return Optional.empty();
        }
        if (label.contains("PRIVATE")) {
            return Optional.of(privateKey(file, label));
        }
        if (label.equals("CERTIFICATE") || label.equals("TRUSTED CERTIFICATE") || label.equals("X509 CERTIFICATE")) {
            return Optional.of(certificate(file, label, lines, begin));
        }
        if (label.equals("PUBLIC KEY")) {
            return Optional.of(publicKey(file, label, block(lines, begin)));
        }
        if (label.equals("RSA PUBLIC KEY")) {
            return Optional.of(new PemFacts(file, PemRole.PUBLIC_KEY, label, Optional.of(AlgorithmFamily.RSA), Optional.empty(), Optional.empty()));
        }
        return Optional.of(new PemFacts(file, PemRole.OTHER, label, Optional.empty(), Optional.empty(), Optional.empty()));
    }

    private PemFacts privateKey(RelativePath file, String label) {
        Optional<AlgorithmFamily> family = switch (label) {
            case "RSA PRIVATE KEY" -> Optional.of(AlgorithmFamily.RSA);
            case "EC PRIVATE KEY" -> Optional.of(AlgorithmFamily.ECDSA);
            case "DSA PRIVATE KEY" -> Optional.of(AlgorithmFamily.DSA);
            default -> Optional.empty();
        };
        return new PemFacts(file, PemRole.PRIVATE_KEY, label, family, Optional.empty(), Optional.empty());
    }

    private PemFacts certificate(RelativePath file, String label, List<String> lines, int begin) {
        try {
            StringBuilder block = new StringBuilder();
            for (int i = begin; i < lines.size(); i++) {
                String line = lines.get(i).strip();
                if (i > begin && line.startsWith("-----BEGIN ")) {
                    break;
                }
                block.append(line).append('\n');
                if (line.startsWith("-----END ")) {
                    break;
                }
            }
            X509Certificate certificate = (X509Certificate) CertificateFactory.getInstance("X.509")
                    .generateCertificate(new ByteArrayInputStream(block.toString().getBytes(StandardCharsets.US_ASCII)));
            PublicKey key = certificate.getPublicKey();
            Optional<CryptoAlgorithm> signature = names.algorithm(CanonicalKind.SIGNATURE, certificate.getSigAlgName())
                    .or(() -> names.algorithm(CanonicalKind.OID, certificate.getSigAlgOID()));
            return new PemFacts(file, PemRole.CERTIFICATE, label, family(key), keySize(key), signature);
        } catch (GeneralSecurityException | ClassCastException e) {
            return new PemFacts(file, PemRole.CERTIFICATE, label, Optional.empty(), Optional.empty(), Optional.empty());
        }
    }

    private PemFacts publicKey(RelativePath file, String label, byte[] der) {
        for (String algorithm : PUBLIC_KEY_ALGORITHMS) {
            try {
                PublicKey key = KeyFactory.getInstance(algorithm).generatePublic(new X509EncodedKeySpec(der));
                return new PemFacts(file, PemRole.PUBLIC_KEY, label, family(key), keySize(key), Optional.empty());
            } catch (GeneralSecurityException e) {
                // not this algorithm (or not supported by this JDK): try the next one
                continue;
            }
        }
        return new PemFacts(file, PemRole.PUBLIC_KEY, label, Optional.empty(), Optional.empty(), Optional.empty());
    }

    private Optional<AlgorithmFamily> family(PublicKey key) {
        return names.algorithm(CanonicalKind.PUBKEY_ALG, key.getAlgorithm()).map(CryptoAlgorithm::family)
                .filter(family -> family != AlgorithmFamily.UNKNOWN);
    }

    private static Optional<Integer> keySize(PublicKey key) {
        if (key instanceof RSAPublicKey rsa) {
            return Optional.of(rsa.getModulus().bitLength());
        }
        if (key instanceof ECPublicKey ec) {
            return Optional.of(ec.getParams().getCurve().getField().getFieldSize());
        }
        if (key instanceof DSAPublicKey dsa) {
            return Optional.of(dsa.getParams().getP().bitLength());
        }
        if (key instanceof DHPublicKey dh) {
            return Optional.of(dh.getParams().getP().bitLength());
        }
        return Optional.empty();
    }

    private static byte[] block(List<String> lines, int begin) {
        StringBuilder base64 = new StringBuilder();
        for (int i = begin + 1; i < lines.size(); i++) {
            String line = lines.get(i).strip();
            if (line.startsWith("-----END ") || line.startsWith("-----BEGIN ")) {
                break;
            }
            if (!line.contains(":")) {
                base64.append(line);
            }
        }
        try {
            return Base64.getMimeDecoder().decode(base64.toString());
        } catch (IllegalArgumentException e) {
            return new byte[0];
        }
    }
}

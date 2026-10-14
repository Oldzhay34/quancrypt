package com.quancrypt.analyzer.unit.cbom;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.analyzer.domain.model.AlgorithmFamily;
import com.quancrypt.analyzer.domain.model.AnalysisRoot;
import com.quancrypt.analyzer.domain.model.Cbom;
import com.quancrypt.analyzer.domain.model.CryptoAlgorithm;
import com.quancrypt.analyzer.domain.model.CryptoUsage;
import com.quancrypt.analyzer.domain.model.Evidence;
import com.quancrypt.analyzer.domain.model.LineRange;
import com.quancrypt.analyzer.domain.model.LocationKind;
import com.quancrypt.analyzer.domain.model.Priority;
import com.quancrypt.analyzer.domain.model.ProjectDescriptor;
import com.quancrypt.analyzer.domain.model.ProjectType;
import com.quancrypt.analyzer.domain.model.RelativePath;
import com.quancrypt.analyzer.domain.model.UsageContext;
import com.quancrypt.analyzer.fake.FixedIds;
import com.quancrypt.analyzer.fake.Usages;
import com.quancrypt.analyzer.infrastructure.cbom.CycloneDxCbomWriter;
import com.quancrypt.analyzer.port.outbound.Clock;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/**
 * The CBOM against the CycloneDX 1.6 JSON schema (D-195) and against the rules of D-196, D-197 and D-202: components per
 * canonical algorithm, certificate, protocol and keystore, an occurrence for every use, quantum level only where
 * crypto-domain has a source, no project name, and a document that is the same for the same usages.
 */
class CycloneDxCbomWriterTest {

    private static final JsonMapper JSON = JsonMapper.builder().build();
    private static final Instant NOW = Instant.parse("2026-10-14T12:00:00Z");
    private static final Clock CLOCK = () -> NOW;
    private static final ProjectDescriptor PROJECT = new ProjectDescriptor(new AnalysisRoot("/workspace/customer-secret-name"), ProjectType.MAVEN);

    private final CycloneDxCbomWriter writer = new CycloneDxCbomWriter(CLOCK, new FixedIds(), "1.0.0");

    private static CryptoUsage usage(String file, Integer line, LocationKind kind, String symbol, AlgorithmFamily family, String raw,
            String mode, String padding, String hash, Integer size, UsageContext context) {
        Optional<LineRange> lines = line == null ? Optional.empty() : Optional.of(new LineRange(line, line));
        return new CryptoUsage(new Evidence(RelativePath.of(file), lines, kind), symbol,
                new CryptoAlgorithm(family, raw, Optional.ofNullable(mode), Optional.ofNullable(padding), Optional.ofNullable(hash),
                        Optional.ofNullable(size)),
                context, Priority.P1, Optional.empty(), 0.9, "test.detector");
    }

    private static CryptoUsage withDetector(CryptoUsage u, String detectorId) {
        return new CryptoUsage(u.evidence(), u.symbol(), u.algorithm(), u.usageContext(), u.priority(), u.library(), u.confidence(), detectorId);
    }

    private static List<CryptoUsage> realistic() {
        List<CryptoUsage> usages = new ArrayList<>();
        usages.add(usage("src/main/java/Card.java", 10, LocationKind.CODE, "Card#encrypt", AlgorithmFamily.RSA,
                "RSA/ECB/OAEPWithSHA-256AndMGF1Padding", "NONE", "OAEP", "SHA-256", 2048, UsageContext.ENCRYPTION));
        usages.add(Usages.certificateFile("certs/server.crt.pem"));
        usages.add(usage("src/main/resources/application.yml", 8, LocationKind.CONFIG, "server.ssl.bundle", AlgorithmFamily.RSA, "SslBundle",
                "TLSv1.2", null, null, 2048, UsageContext.TLS_KEY_EXCHANGE));
        usages.add(usage("src/main/java/Legacy.java", 21, LocationKind.CODE, "Legacy#encrypt", AlgorithmFamily.AES, "AES/ECB/PKCS5Padding",
                "ECB", "PKCS5", null, null, UsageContext.SYMMETRIC_ENCRYPTION));
        usages.add(usage("src/main/java/Legacy.java", 30, LocationKind.CODE, "Legacy#gcm", AlgorithmFamily.AES, "AES/GCM/NoPadding",
                "GCM", "NONE", null, 256, UsageContext.SYMMETRIC_ENCRYPTION));
        usages.add(usage("src/main/java/Sign.java", 12, LocationKind.CODE, "Sign#sign", AlgorithmFamily.RSA, "SHA1withRSA", "NONE",
                "PKCS1_V1_5", "SHA-1", 1024, UsageContext.SIGNATURE));
        usages.add(usage("src/main/java/Sign.java", 40, LocationKind.CODE, "Sign#hash", AlgorithmFamily.SHA1, "SHA-1", null, null, null, null,
                UsageContext.SIGNATURE));
        usages.add(usage("src/main/java/Tls.java", 7, LocationKind.CODE, "Tls#trustAll", AlgorithmFamily.UNKNOWN, "TrustManager:trust-all",
                null, null, null, null, UsageContext.TLS_SERVER_AUTH));
        usages.add(usage("config/legacy.jks", null, LocationKind.KEYSTORE_FILE, "legacy.jks", AlgorithmFamily.UNKNOWN, "keystore", null,
                null, null, null, UsageContext.KEYSTORE));
        usages.add(withDetector(usage("certs/server.key.pem", null, LocationKind.CERTIFICATE_FILE, "server.key.pem", AlgorithmFamily.RSA,
                "PRIVATE KEY", null, null, null, 2048, UsageContext.CERTIFICATE), "pem.certificate"));
        usages.add(usage("src/main/java/Jwt.java", 9, LocationKind.CODE, "Jwt#sign", AlgorithmFamily.ECDSA, "ES256", null, null, "SHA-256",
                256, UsageContext.TOKEN_SIGNATURE));
        return usages;
    }

    private JsonNode write(List<CryptoUsage> usages) {
        Cbom cbom = writer.write(PROJECT, usages);
        assertThat(cbom.specVersion()).isEqualTo("1.6");
        return JSON.readTree(cbom.json());
    }

    private static Map<String, JsonNode> byRef(JsonNode bom) {
        Map<String, JsonNode> components = new HashMap<>();
        bom.get("components").forEach(c -> components.put(c.get("bom-ref").asString(), c));
        return components;
    }

    @Test
    void theCbomValidatesAgainstTheCycloneDx16Schema() {
        String json = writer.write(PROJECT, realistic()).json();

        assertThat(CycloneDxSchema.validate(json)).isEmpty();
        assertThat(JSON.readTree(json).get("specVersion").asString()).isEqualTo("1.6");
        assertThat(JSON.readTree(json).get("bomFormat").asString()).isEqualTo("CycloneDX");
    }

    @Test
    void anEmptyAnalysisIsAValidCbom() {
        String json = writer.write(PROJECT, List.of()).json();

        assertThat(CycloneDxSchema.validate(json)).isEmpty();
    }

    @Test
    void everyComponentIsACryptographicAssetWithAtLeastOneOccurrence() {
        JsonNode bom = write(realistic());

        assertThat(bom.get("components").size()).isPositive();
        for (JsonNode component : bom.get("components")) {
            assertThat(component.get("type").asString()).isEqualTo("cryptographic-asset");
            assertThat(component.get("cryptoProperties").get("assetType").asString())
                    .isIn("algorithm", "certificate", "protocol", "related-crypto-material");
            JsonNode occurrences = component.get("evidence").get("occurrences");
            assertThat(occurrences.size()).as(component.get("bom-ref").asString()).isPositive();
            occurrences.forEach(o -> assertThat(o.get("location").asString()).isNotBlank());
        }
    }

    @Test
    void anOccurrenceNamesTheFileTheLineAndTheSymbol() {
        JsonNode oaep = byRef(write(realistic())).get("alg:RSA-2048/OAEP/SHA-256/pke");

        JsonNode occurrence = oaep.get("evidence").get("occurrences").get(0);
        assertThat(occurrence.get("location").asString()).isEqualTo("src/main/java/Card.java");
        assertThat(occurrence.get("line").asInt()).isEqualTo(10);
        assertThat(occurrence.get("symbol").asString()).isEqualTo("Card#encrypt");
    }

    @Test
    void aWholeFileUsageHasALocationAndNoLine() {
        JsonNode certificate = byRef(write(realistic())).get("cert:certs/server.crt.pem");

        JsonNode occurrence = certificate.get("evidence").get("occurrences").get(0);
        assertThat(occurrence.get("location").asString()).isEqualTo("certs/server.crt.pem");
        assertThat(occurrence.has("line")).isFalse();
        assertThat(certificate.get("name").asString()).isEqualTo("server.crt.pem");
        assertThat(certificate.get("cryptoProperties").get("assetType").asString()).isEqualTo("certificate");
    }

    @Test
    void theSameAlgorithmUsedTwiceIsOneComponentWithTwoOccurrencesAndARepeatedUseCountsOnce() {
        CryptoUsage first = usage("A.java", 3, LocationKind.CODE, "A#x", AlgorithmFamily.AES, "AES", "ECB", null, null, null, UsageContext.SYMMETRIC_ENCRYPTION);
        CryptoUsage second = usage("B.java", 5, LocationKind.CODE, "B#y", AlgorithmFamily.AES, "AES", "ECB", null, null, null, UsageContext.SYMMETRIC_ENCRYPTION);

        JsonNode bom = write(List.of(first, second, first));

        assertThat(bom.get("components").size()).isEqualTo(1);
        assertThat(bom.get("components").get(0).get("evidence").get("occurrences").size()).isEqualTo(2);
    }

    @Test
    void theQuantumLevelIsZeroOnlyForFamiliesCryptoDomainCallsVulnerable() {
        Map<String, JsonNode> components = byRef(write(realistic()));

        for (JsonNode component : components.values()) {
            JsonNode algorithm = component.get("cryptoProperties").get("algorithmProperties");
            if (algorithm == null) {
                continue;
            }
            String ref = component.get("bom-ref").asString();
            boolean vulnerable = ref.startsWith("alg:RSA") || ref.startsWith("alg:ECDSA");
            assertThat(algorithm.has("nistQuantumSecurityLevel")).as(ref).isEqualTo(vulnerable);
            if (vulnerable) {
                assertThat(algorithm.get("nistQuantumSecurityLevel").asInt()).as(ref).isZero();
            }
            assertThat(algorithm.has("classicalSecurityLevel")).as(ref).isFalse();
        }
    }

    @Test
    void primitivesModesAndPaddingsFollowTheSchemaLists() {
        Map<String, JsonNode> components = byRef(write(realistic()));

        JsonNode ecb = components.get("alg:AES/ECB/PKCS5").get("cryptoProperties").get("algorithmProperties");
        assertThat(ecb.get("primitive").asString()).isEqualTo("block-cipher");
        assertThat(ecb.get("mode").asString()).isEqualTo("ecb");
        assertThat(ecb.get("padding").asString()).isEqualTo("pkcs5");
        JsonNode gcm = components.get("alg:AES-256/GCM").get("cryptoProperties").get("algorithmProperties");
        assertThat(gcm.get("primitive").asString()).isEqualTo("ae");
        assertThat(gcm.get("mode").asString()).isEqualTo("gcm");
        assertThat(gcm.has("padding")).isFalse();
        assertThat(gcm.get("parameterSetIdentifier").asString()).isEqualTo("256");
        JsonNode signature = components.get("alg:RSA-1024/PKCS1_V1_5/SHA-1/signature").get("cryptoProperties").get("algorithmProperties");
        assertThat(signature.get("primitive").asString()).isEqualTo("signature");
        assertThat(signature.get("padding").asString()).isEqualTo("pkcs1v15");
        assertThat(components.get("alg:RSA-2048/OAEP/SHA-256/pke").get("cryptoProperties").get("algorithmProperties").get("primitive").asString())
                .isEqualTo("pke");
        assertThat(components.get("alg:SHA1").get("cryptoProperties").get("algorithmProperties").get("primitive").asString()).isEqualTo("hash");
        assertThat(components.get("alg:unknown:TrustManager:trust-all").get("cryptoProperties").get("algorithmProperties").get("primitive").asString())
                .isEqualTo("unknown");
    }

    @Test
    void aTlsUsageIsAProtocolComponentThatRefersToTheKeyAlgorithmAndTheVersionIsNotAnAlgorithmMode() {
        Map<String, JsonNode> components = byRef(write(realistic()));

        JsonNode protocol = components.get("proto:TLSv1.2").get("cryptoProperties");
        assertThat(protocol.get("assetType").asString()).isEqualTo("protocol");
        assertThat(protocol.get("protocolProperties").get("type").asString()).isEqualTo("tls");
        assertThat(protocol.get("protocolProperties").get("version").asString()).isEqualTo("TLSv1.2");
        assertThat(protocol.get("protocolProperties").get("cryptoRefArray").get(0).asString()).isEqualTo("alg:RSA-2048");
        assertThat(components).containsKey("alg:RSA-2048");
        assertThat(components.get("alg:RSA-2048").get("cryptoProperties").get("algorithmProperties").has("mode")).isFalse();
        assertThat(components).containsKey("proto:TLS");
    }

    @Test
    void aPrivateKeyFileOfACertificateIsKeyMaterialAndNotACertificate() {
        Map<String, JsonNode> components = byRef(write(realistic()));

        JsonNode key = components.get("key:certs/server.key.pem");
        assertThat(key.get("cryptoProperties").get("assetType").asString()).isEqualTo("related-crypto-material");
        assertThat(key.get("cryptoProperties").get("relatedCryptoMaterialProperties").get("type").asString()).isEqualTo("private-key");
        assertThat(components).doesNotContainKey("cert:certs/server.key.pem");
    }

    @Test
    void aKeystoreIsRelatedCryptoMaterialAndNeverAnAlgorithm() {
        Map<String, JsonNode> components = byRef(write(realistic()));

        JsonNode keystore = components.get("keystore:config/legacy.jks");
        assertThat(keystore.get("cryptoProperties").get("assetType").asString()).isEqualTo("related-crypto-material");
        assertThat(keystore.get("cryptoProperties").get("relatedCryptoMaterialProperties").get("type").asString()).isEqualTo("other");
        assertThat(components).doesNotContainKey("alg:unknown:keystore");
    }

    @Test
    void theDocumentNamesNoProjectAndIsTheSameForTheSameUsages() {
        String json = writer.write(PROJECT, realistic()).json();
        JsonNode bom = JSON.readTree(json);

        assertThat(json).doesNotContain("customer-secret-name");
        assertThat(bom.get("metadata").has("component")).isFalse();
        assertThat(bom.get("metadata").get("tools").get("components").get(0).get("name").asString()).isEqualTo("quancrypt-analyzer-service");
        assertThat(bom.get("metadata").get("tools").get("components").get(0).get("version").asString()).isEqualTo("1.0.0");
        assertThat(bom.get("serialNumber").asString()).isEqualTo("urn:uuid:" + FixedIds.ID);
        assertThat(bom.get("metadata").get("timestamp").asString()).startsWith("2026-10-14T12:00:00");
        assertThat(writer.write(PROJECT, realistic()).json()).isEqualTo(json);
    }
}

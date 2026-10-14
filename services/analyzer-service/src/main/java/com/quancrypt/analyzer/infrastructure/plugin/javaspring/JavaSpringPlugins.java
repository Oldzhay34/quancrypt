package com.quancrypt.analyzer.infrastructure.plugin.javaspring;

import com.quancrypt.analyzer.domain.model.CanonicalNames;
import com.quancrypt.analyzer.domain.policy.PriorityClassifier;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.code.BouncyCastleDetector;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.code.JcaCipherDetector;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.code.JcaKemDetector;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.code.JcaKeyAgreementDetector;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.code.JcaKeyFactoryDetector;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.code.JcaKeyPairGeneratorDetector;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.code.JcaSignatureDetector;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.code.JwtLibraryDetector;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.code.MqttTlsDetector;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.code.TlsApiDetector;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.config.SpringConfigReader;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.file.BuildFileDetector;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.file.BuildRuntimeReader;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.file.KeystoreFileDetector;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.file.MosquittoConfigDetector;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.file.PemCertificateScanner;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.file.SpringJwtConfigDetector;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.file.SpringSslConfigDetector;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.pem.PemReader;
import java.util.List;
import java.util.function.UnaryOperator;

/** Builds the standard Java / Spring Boot plugin: every detector of P3.2 wired to one canonical dictionary. */
public final class JavaSpringPlugins {

    private JavaSpringPlugins() {
    }

    public static JavaSpringPlugin standard(CanonicalNames names) {
        return standard(names, UnaryOperator.identity());
    }

    /** The standard plugin whose findings pass their raw names and symbols through the sanitizer (UsageAssembler). */
    public static JavaSpringPlugin standard(CanonicalNames names, UnaryOperator<String> sanitizer) {
        List<CryptoDetector> detectors = List.of(
                new JcaCipherDetector(names), new JcaKeyPairGeneratorDetector(names), new JcaSignatureDetector(names),
                new JcaKeyAgreementDetector(names), new JcaKemDetector(names), new JcaKeyFactoryDetector(names),
                new TlsApiDetector(names), new BouncyCastleDetector(names), new JwtLibraryDetector(names), new MqttTlsDetector(),
                new SpringSslConfigDetector(names), new SpringJwtConfigDetector(names), new MosquittoConfigDetector(names),
                new PemCertificateScanner(names), new KeystoreFileDetector(), new BuildFileDetector());
        return of(names, detectors, new BuildRuntimeReader(), sanitizer);
    }

    /** A plugin with the given detectors (a deployment with fewer or more detectors, or a test with a double). */
    public static JavaSpringPlugin of(CanonicalNames names, List<CryptoDetector> detectors, BuildRuntime runtime) {
        return of(names, detectors, runtime, UnaryOperator.identity());
    }

    public static JavaSpringPlugin of(CanonicalNames names, List<CryptoDetector> detectors, BuildRuntime runtime,
            UnaryOperator<String> sanitizer) {
        ProjectIndexBuilder index = new ProjectIndexBuilder(new FileClassifier(), new SpringConfigReader(), new PemReader(names));
        return new JavaSpringPlugin(detectors, runtime, index, new JavaSources(), new UsageAssembler(new PriorityClassifier(), sanitizer));
    }
}

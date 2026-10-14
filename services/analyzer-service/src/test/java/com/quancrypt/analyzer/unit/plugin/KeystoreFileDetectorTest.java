package com.quancrypt.analyzer.unit.plugin;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.analyzer.domain.model.AlgorithmFamily;
import com.quancrypt.analyzer.domain.model.LocationKind;
import com.quancrypt.analyzer.domain.model.RelativePath;
import com.quancrypt.analyzer.domain.model.UsageContext;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.Observation;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.file.KeystoreFileDetector;
import com.quancrypt.analyzer.port.outbound.SourceTree;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class KeystoreFileDetectorTest {

    private final KeystoreFileDetector detector = new KeystoreFileDetector();

    @Test
    void keystoresAreReportedByTypeWithoutAnAlgorithm() {
        List<Observation> found = DetectorHarness.run(detector, "certs/app.p12", "binary", "legacy/old.jks", "binary", "x/a.bks", "binary",
                "x/b.keystore", "binary").observations();

        assertThat(found).extracting(o -> o.algorithm().rawName()).containsExactlyInAnyOrder("PKCS12 keystore", "JKS keystore", "BKS keystore",
                "keystore keystore");
        assertThat(found).extracting(Observation::usage).containsOnly(UsageContext.KEYSTORE);
        assertThat(found).extracting(o -> o.algorithm().family()).containsOnly(AlgorithmFamily.UNKNOWN);
        assertThat(found).extracting(o -> o.evidence().locationKind()).containsOnly(LocationKind.KEYSTORE_FILE);
        assertThat(found).extracting(Observation::confidence).containsOnly(1.0);
    }

    @Test
    void theContentOfAKeystoreIsNeverOpened() {
        List<String> reads = new ArrayList<>();
        SourceTree tree = DetectorHarness.tree("certs/app.p12", "secret-binary", "src/main/java/A.java", "class A {}");
        SourceTree watching = new SourceTree() {
            @Override
            public com.quancrypt.analyzer.domain.model.AnalysisRoot root() {
                return tree.root();
            }

            @Override
            public List<RelativePath> files() {
                return tree.files();
            }

            @Override
            public boolean exists(RelativePath path) {
                return tree.exists(path);
            }

            @Override
            public byte[] read(RelativePath path) {
                reads.add(path.value());
                return tree.read(path);
            }

            @Override
            public List<String> readLines(RelativePath path) {
                reads.add(path.value());
                return tree.readLines(path);
            }
        };

        DetectorHarness.runOn(detector, watching);

        assertThat(reads).doesNotContain("certs/app.p12");
    }
}


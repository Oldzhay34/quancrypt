package com.quancrypt.analyzer.unit.plugin;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.analyzer.domain.model.LocationKind;
import com.quancrypt.analyzer.domain.model.RelativePath;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.FileClassifier;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.FileKind;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.ProjectFile;
import java.util.Set;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class FileClassifierTest {

    private final FileClassifier classifier = new FileClassifier();

    @ParameterizedTest
    @CsvSource({
        "src/main/java/com/acme/A.java,JAVA,CODE",
        "src/test/java/com/acme/ATest.java,JAVA,TEST_CODE",
        "src/integrationTest/java/B.java,JAVA,TEST_CODE",
        "module/src/main/java/ProviderIT.java,JAVA,TEST_CODE",
        "src/main/resources/application.yml,SPRING_YAML,CONFIG",
        "src/main/resources/application-prod.yaml,SPRING_YAML,CONFIG",
        "src/main/resources/bootstrap.properties,SPRING_PROPERTIES,CONFIG",
        "src/test/resources/application.yml,SPRING_YAML,TEST_CODE",
        "mosquitto/mosquitto.conf,MOSQUITTO_CONF,CONFIG",
        "certs/ca.crt.pem,PEM,CERTIFICATE_FILE",
        "certs/server.key,PEM,CERTIFICATE_FILE",
        "certs/server.p12,KEYSTORE,KEYSTORE_FILE",
        "keys/app.JKS,KEYSTORE,KEYSTORE_FILE",
        "pom.xml,POM,BUILD_FILE",
        "build.gradle.kts,GRADLE,BUILD_FILE",
        "settings.gradle,GRADLE,BUILD_FILE",
        "docs/readme.md,OTHER,CONFIG",
        "docker-compose.yml,OTHER,CONFIG"})
    void filesAreClassifiedByTheirPath(String path, FileKind kind, LocationKind location) {
        ProjectFile file = classifier.classify(RelativePath.of(path));

        assertThat(file.kind()).isEqualTo(kind);
        assertThat(file.location()).isEqualTo(location);
    }

    @Test
    void toolDirectoriesAreAlwaysSkipped() {
        assertThat(classifier.skipsDirectory(".git", Set.of())).isTrue();
        assertThat(classifier.skipsDirectory("node_modules", Set.of("package.json"))).isTrue();
        assertThat(classifier.skipsDirectory(".gradle", Set.of())).isTrue();
        assertThat(classifier.skipsDirectory(".idea", Set.of())).isTrue();
    }

    @Test
    void buildOutputIsSkippedOnlyNextToABuildFile() {
        assertThat(classifier.skipsDirectory("build", Set.of("build.gradle.kts", "src"))).isTrue();
        assertThat(classifier.skipsDirectory("target", Set.of("pom.xml"))).isTrue();
        assertThat(classifier.skipsDirectory("build", Set.of("Foo.java"))).isFalse();
        assertThat(classifier.skipsDirectory("target", Set.of("notes.txt"))).isFalse();
        assertThat(classifier.skipsDirectory("out", Set.of("pom.xml"))).isFalse();
    }
}

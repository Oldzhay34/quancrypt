package com.quancrypt.analyzer.unit.evaluation;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.analyzer.evaluation.PerformanceMeasurement;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Objects;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** The performance measurement of NFR-01 (D-198): it times the whole analysis and reports the size of what it analyzed. */
class PerformanceMeasurementTest {

    @TempDir
    Path project;

    private void write(String path, String content) throws IOException {
        Path file = project.resolve(path);
        Files.createDirectories(Objects.requireNonNull(file.getParent()));
        Files.writeString(file, content);
    }

    @Test
    void itRunsTheAnalysisAndCountsTheJavaSourceOutsideSkippedDirectories() throws IOException {
        write("pom.xml", "<project/>");
        write("src/main/java/A.java", "import javax.crypto.Cipher;\nclass A {\n  void f() throws Exception {\n    Cipher.getInstance(\"DES\");\n  }\n}\n");
        write("src/main/java/B.java", "class B {\n}\n");
        write("target/generated/C.java", "class C {\n}\n");

        PerformanceMeasurement.Result result = PerformanceMeasurement.measure(project, 2);

        assertThat(result.javaFiles()).isEqualTo(2);
        assertThat(result.javaLines()).isEqualTo(8);
        assertThat(result.runsMs()).hasSize(2);
        assertThat(result.findings()).isPositive();
        assertThat(result.filesScanned()).isEqualTo(4);
        assertThat(result.withinTarget()).isTrue();
        assertThat(result.project()).isEqualTo(Objects.requireNonNull(project.getFileName()).toString());
        assertThat(result.wholeUseCase()).isTrue();
    }

    @Test
    void aDirectoryOfIndependentServicesIsMeasuredThroughThePluginDirectly() throws IOException {
        write("service-a/pom.xml", "<project/>");
        write("service-a/src/main/java/A.java", "import javax.crypto.Cipher;\nclass A {\n  void f() throws Exception {\n    Cipher.getInstance(\"DES\");\n  }\n}\n");
        write("service-b/build.gradle.kts", "");

        PerformanceMeasurement.Result result = PerformanceMeasurement.measure(project, 1);

        assertThat(result.wholeUseCase()).isFalse();
        assertThat(result.findings()).isPositive();
        assertThat(result.javaFiles()).isEqualTo(1);
        assertThat(PerformanceMeasurement.render(List.of(result))).contains("proje türü tespiti yok");
    }

    @Test
    void theSectionNamesTheMeasurementAndTheVerdict() throws IOException {
        write("pom.xml", "<project/>");
        write("src/main/java/A.java", "class A {\n}\n");

        String section = PerformanceMeasurement.render(List.of(PerformanceMeasurement.measure(project, 3)));

        assertThat(section).startsWith("## 5. Performans (NFR-01: ≤ 300 sn)").contains("Koşu 1 (soğuk)").contains("Koşu 3")
                .contains("En yüksek heap").contains("Karşılandı");
    }
}

package com.quancrypt.analyzer.unit.plugin;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.analyzer.domain.model.RuntimeInfo;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.LibraryDependency;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.file.BuildFileDetector;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.file.BuildRuntimeReader;
import java.util.Optional;
import org.junit.jupiter.api.Test;

class BuildFileDetectorTest {

    private final BuildFileDetector detector = new BuildFileDetector();

    private static final String POM = """
            <?xml version="1.0"?>
            <project>
              <parent>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-starter-parent</artifactId>
                <version>3.2.0</version>
              </parent>
              <properties>
                <java.version>17</java.version>
                <jjwt.version>0.12.5</jjwt.version>
              </properties>
              <dependencies>
                <dependency>
                  <groupId>org.bouncycastle</groupId>
                  <artifactId>bcprov-jdk18on</artifactId>
                  <version>1.78</version>
                </dependency>
                <dependency>
                  <groupId>io.jsonwebtoken</groupId>
                  <artifactId>jjwt-api</artifactId>
                  <version>${jjwt.version}</version>
                  <exclusions><exclusion><groupId>x</groupId><artifactId>y</artifactId></exclusion></exclusions>
                </dependency>
                <dependency>
                  <groupId>org.springframework.boot</groupId>
                  <artifactId>spring-boot-starter-web</artifactId>
                </dependency>
              </dependencies>
            </project>
            """;

    @Test
    void mavenCryptoDependenciesAreCollectedWithResolvedVersions() {
        DetectorHarness.Outcome outcome = DetectorHarness.run(detector, "pom.xml", POM);

        assertThat(outcome.observations()).isEmpty();
        assertThat(outcome.libraries()).extracting(LibraryDependency::artifact).containsExactly("bcprov-jdk18on", "jjwt-api");
        assertThat(outcome.libraries().get(0).version()).contains("1.78");
        assertThat(outcome.libraries().get(1).version()).contains("0.12.5");
        assertThat(outcome.libraries().get(0).line()).isEqualTo(13);
    }

    @Test
    void gradleCryptoDependenciesAreCollectedFromBothDsls() {
        DetectorHarness.Outcome kotlin = DetectorHarness.run(detector, "build.gradle.kts", """
                dependencies {
                    implementation("com.nimbusds:nimbus-jose-jwt:9.37")
                    implementation("org.eclipse.paho:org.eclipse.paho.client.mqttv3:1.2.5")
                    implementation("org.apache.commons:commons-lang3:3.14.0")
                }
                """);
        DetectorHarness.Outcome groovy = DetectorHarness.run(detector, "build.gradle", """
                dependencies {
                    implementation 'com.auth0:java-jwt:4.4.0'
                    implementation 'com.auth0:auth0-spring:2.0'
                }
                """);

        assertThat(kotlin.libraries()).extracting(LibraryDependency::artifact).containsExactly("nimbus-jose-jwt", "org.eclipse.paho.client.mqttv3");
        assertThat(groovy.libraries()).extracting(LibraryDependency::artifact).containsExactly("java-jwt");
    }

    @Test
    void theJavaAndBootVersionsOfAMavenProjectAreRead() {
        RuntimeInfo info = runtime("pom.xml", POM);

        assertThat(info.javaVersion()).contains("17");
        assertThat(info.springBootVersion()).contains("3.2.0");
    }

    @Test
    void theJavaAndBootVersionsOfAGradleProjectAreRead() {
        assertThat(runtime("build.gradle.kts", """
                plugins {
                    id("org.springframework.boot") version "4.1.1"
                }
                java {
                    toolchain {
                        languageVersion = JavaLanguageVersion.of(25)
                    }
                }
                """)).isEqualTo(new RuntimeInfo(Optional.of("25"), Optional.of("4.1.1")));
        assertThat(runtime("build.gradle", """
                plugins {
                    id 'org.springframework.boot' version '3.2.0'
                }
                sourceCompatibility = '17'
                """)).isEqualTo(new RuntimeInfo(Optional.of("17"), Optional.of("3.2.0")));
    }

    @Test
    void versionsThatCannotBeFoundAreEmptyAndNothingIsRaised() {
        assertThat(runtime("pom.xml", "<project><modelVersion>4.0.0</modelVersion></project>")).isEqualTo(RuntimeInfo.UNKNOWN);
        assertThat(runtime("pom.xml", "<project><unclosed>")).isEqualTo(RuntimeInfo.UNKNOWN);
        assertThat(runtime("build.gradle", "// nothing here")).isEqualTo(RuntimeInfo.UNKNOWN);
    }

    @Test
    void theRootBuildFileWinsOverModules() {
        RuntimeInfo info = DetectorHarness.runtimeOf(new BuildRuntimeReader(), "module/pom.xml",
                "<project><properties><java.version>11</java.version></properties></project>", "pom.xml",
                "<project><properties><java.version>21</java.version></properties></project>");

        assertThat(info.javaVersion()).contains("21");
    }

    @Test
    void aMavenFileWithADoctypeIsReadWithoutFetchingAnything() {
        RuntimeInfo info = runtime("pom.xml", "<!DOCTYPE project [<!ENTITY x SYSTEM \"file:///etc/passwd\">]><project><properties>"
                + "<java.version>17</java.version></properties></project>");

        assertThat(info.javaVersion()).isIn(Optional.of("17"), Optional.empty());
    }

    private RuntimeInfo runtime(String path, String content) {
        return DetectorHarness.runtimeOf(new BuildRuntimeReader(), path, content);
    }
}


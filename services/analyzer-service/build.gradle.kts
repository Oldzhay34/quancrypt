import java.math.BigDecimal

plugins {
    java
    jacoco
    checkstyle
    id("org.springframework.boot") version "4.1.1"
    id("com.github.spotbugs") version "6.5.12"
}

group = "com.quancrypt"
version = "1.0.0"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(25)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation(platform("org.springframework.boot:spring-boot-dependencies:4.1.1"))
    // Spring Boot carries the REST layer, the token security and the health endpoints (P3.3, D-200); the domain, port and
    // usecase layers stay framework free.
    implementation("org.springframework.boot:spring-boot-starter")
    implementation("org.springframework.boot:spring-boot-starter-webmvc")
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-actuator")

    // The CBOM is written with the CycloneDX library (D-18, D-195); only infrastructure/cbom imports it.
    implementation("org.cyclonedx:cyclonedx-core-java:13.2.0")

    // Source analysis without compiling (FR-12): JavaParser only, no symbol solver (D-187). YAML comes from the Boot BOM.
    implementation("com.github.javaparser:javaparser-core:3.28.2")
    implementation("org.yaml:snakeyaml")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.boot:spring-boot-starter-webmvc-test")
    testImplementation("com.networknt:json-schema-validator:3.0.8")
    testImplementation("com.tngtech.archunit:archunit-junit5:1.5.1")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

// The canonical dictionary has one source, contracts/canonical_dictionary.csv; the build copies it into the resources
// under the name the service loads (P3.2, section 4 of the prompt).
tasks.processResources {
    from(layout.projectDirectory.file("../../contracts/canonical_dictionary.csv")) {
        rename { "canonical-names.csv" }
    }
    // The redaction rules have one source as well (guardrails-security, section 5); the snippet endpoint and the log
    // formatter read them from the classpath (P3.3).
    from(layout.projectDirectory.file("../../contracts/redaction-rules.yaml")) {
        into("redaction")
    }
}

// The CBOM names the tool version; build-info.properties carries it into the service.
springBoot {
    buildInfo()
}

// Detection evaluation (recall and precision against the QBank golden inventory and the benchmark subset). The code lives
// in its own source set, so it is not part of the service.
sourceSets {
    create("eval") {
        java.srcDir("src/eval/java")
        compileClasspath += sourceSets.main.get().output + configurations.runtimeClasspath.get()
        runtimeClasspath += output + compileClasspath
    }
}

dependencies {
    // The golden test uses the same comparison code as the evaluation task.
    testImplementation(sourceSets["eval"].output)
}

tasks.register<JavaExec>("detectionEval") {
    group = "verification"
    description = "Measures detection recall and precision on the QBank golden inventory and writes docs/detection_eval.md (benchmark not measured, D-191)."
    classpath = sourceSets["eval"].runtimeClasspath
    mainClass.set("com.quancrypt.analyzer.evaluation.DetectionEval")
    workingDir = projectDir
    systemProperty("quancrypt.contracts.dir", file("../../contracts").absolutePath)
    systemProperty("quancrypt.expected.dir", file("../../reference-system/expected").absolutePath)
    systemProperty("quancrypt.reference.dir", file("../../reference-system").absolutePath)
    systemProperty("quancrypt.report.file", file("docs/detection_eval.md").absolutePath)
    // The project of the performance measurement (NFR-01, D-198): -Pquancrypt.perf.root=<path>; without it the section stays.
    if (project.hasProperty("quancrypt.perf.root")) {
        systemProperty("quancrypt.perf.root", project.property("quancrypt.perf.root") as String)
    }
}

tasks.withType<JavaCompile> {
    options.compilerArgs.addAll(listOf("-Xlint:all", "-parameters"))
}

tasks.jar {
    enabled = false
}

tasks.bootJar {
    archiveFileName.set("analyzer-service.jar")
}

tasks.test {
    useJUnitPlatform()
    // The code-list contract test compares the domain enums with the JSON Schemas (D-17).
    systemProperty("quancrypt.contracts.dir", file("../../contracts").absolutePath)
    systemProperty("quancrypt.expected.dir", file("../../reference-system/expected").absolutePath)
    systemProperty("quancrypt.reference.dir", file("../../reference-system").absolutePath)
    // The QBank CBOM snapshot lives with the test sources and is written there when it is missing (P3.3).
    systemProperty("quancrypt.snapshots.dir", file("src/test/resources/snapshots").absolutePath)
    finalizedBy(tasks.jacocoTestReport)
}

checkstyle {
    toolVersion = "14.3.0"
    configFile = file("config/checkstyle/checkstyle.xml")
    maxWarnings = 0
}

spotbugs {
    toolVersion.set("4.10.4")
    excludeFilter.set(file("config/spotbugs/exclude.xml"))
}

tasks.named<com.github.spotbugs.snom.SpotBugsTask>("spotbugsTest") {
    excludeFilter.set(file("config/spotbugs/test-exclude.xml"))
}

tasks.withType<com.github.spotbugs.snom.SpotBugsTask> {
    reports {
        create("text") {
            required.set(true)
            outputLocation.set(layout.buildDirectory.file("reports/spotbugs/${name}.txt"))
        }
    }
}

jacoco {
    toolVersion = "0.8.15"
}

tasks.jacocoTestReport {
    reports {
        xml.required = true
    }
}

// At least 75 % line coverage for the domain and usecase layers (hexagonal-service, section 7).
tasks.jacocoTestCoverageVerification {
    dependsOn(tasks.test)
    classDirectories.setFrom(
        files(
            classDirectories.files.map {
                fileTree(it) {
                    include("**/domain/**", "**/usecase/**")
                }
            },
        ),
    )
    violationRules {
        rule {
            limit {
                counter = "LINE"
                minimum = BigDecimal("0.75")
            }
        }
    }
}

tasks.check {
    dependsOn(tasks.jacocoTestCoverageVerification)
}

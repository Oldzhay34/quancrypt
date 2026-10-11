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
    // Domain, port and usecase layers stay framework free; Spring is used by api, facade and infrastructure only.
    implementation("org.springframework.boot:spring-boot-starter")
    implementation("org.springframework.boot:spring-boot-starter-webmvc")
    implementation("org.springframework.boot:spring-boot-starter-validation")
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    implementation("org.springframework.boot:spring-boot-starter-jdbc")
    implementation("org.flywaydb:flyway-core")
    implementation("org.flywaydb:flyway-database-postgresql")
    implementation("tools.jackson.core:jackson-databind")
    implementation("org.yaml:snakeyaml")
    implementation("io.github.resilience4j:resilience4j-circuitbreaker:2.4.0")
    // Compile scope: constraint names of violations are read from PSQLException (SqlErrors).
    implementation("org.postgresql:postgresql")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.boot:spring-boot-starter-webmvc-test")
    testImplementation("com.networknt:json-schema-validator:3.0.8")
    testImplementation("com.tngtech.archunit:archunit-junit5:1.5.1")
    testImplementation("org.testcontainers:testcontainers")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.withType<JavaCompile> {
    options.compilerArgs.addAll(listOf("-Xlint:all", "-parameters"))
}

tasks.jar {
    enabled = false
}

tasks.bootJar {
    archiveFileName.set("core-service.jar")
}

// The redaction rules are a shared contract (guardrails-security section 5); the service reads its own copy.
tasks.processResources {
    from("../../contracts/redaction-rules.yaml") {
        into("redaction")
    }
}

tasks.test {
    useJUnitPlatform()
    exclude("**/integration/**")
    // The golden inventory lives in reference-system/expected (approved in P1.4, D-123).
    systemProperty("quancrypt.expected.dir", file("../../reference-system/expected").absolutePath)
    systemProperty("quancrypt.contracts.dir", file("../../contracts").absolutePath)
    finalizedBy(tasks.jacocoTestReport)
}

// Integration tests run against a real PostgreSQL in Testcontainers; Docker must be running (they fail, never skip).
val integrationTest by tasks.registering(Test::class) {
    description = "Runs the Testcontainers integration and JDBC contract tests."
    group = "verification"
    testClassesDirs = sourceSets.test.get().output.classesDirs
    classpath = sourceSets.test.get().runtimeClasspath
    useJUnitPlatform()
    include("**/integration/**")
    shouldRunAfter(tasks.test)
    systemProperty("quancrypt.contracts.dir", file("../../contracts").absolutePath)
    systemProperty("quancrypt.infra.dir", file("../../infra").absolutePath)
    systemProperty("quancrypt.migrations.dir", file("src/main/resources/db/migration").absolutePath)
    environment("TESTCONTAINERS_RYUK_DISABLED", "true")
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
    dependsOn(tasks.jacocoTestCoverageVerification, integrationTest)
}

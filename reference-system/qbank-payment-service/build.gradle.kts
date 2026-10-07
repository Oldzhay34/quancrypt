import java.math.BigDecimal

plugins {
    java
    jacoco
    checkstyle
    id("org.springframework.boot") version "4.1.1"
    id("com.github.spotbugs") version "6.5.12"
}

group = "com.quancrypt.qbank"
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
    implementation("org.springframework.boot:spring-boot-starter-webmvc")
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-resource-server")
    implementation("org.eclipse.paho:org.eclipse.paho.client.mqttv3:1.2.5")
    implementation("com.networknt:json-schema-validator:3.0.8")
    implementation("io.github.resilience4j:resilience4j-circuitbreaker:2.4.0")
    implementation("io.github.resilience4j:resilience4j-retry:2.4.0")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.boot:spring-boot-starter-webmvc-test")
    testImplementation("com.tngtech.archunit:archunit-junit5:1.5.1")
    testImplementation("org.testcontainers:testcontainers")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.withType<JavaCompile> {
    options.compilerArgs.addAll(listOf("-Xlint:all", "-parameters"))
}

// The MQTT message schema has a single source of truth in reference-system/contracts; it is copied onto the class path.
tasks.processResources {
    from("../contracts") {
        include("terminal-transaction.schema.json")
        into("contracts")
    }
}

tasks.jar {
    enabled = false
}

tasks.bootJar {
    archiveFileName.set("qbank-payment-service.jar")
}

tasks.test {
    useJUnitPlatform()
    // Tests use the real demo certificates (reference-system/certs/out); `make certs` generates them.
    systemProperty(
        "qbank.certs.dir",
        providers.environmentVariable("QBANK_CERTS_DIR").orElse(file("../certs/out").absolutePath).get(),
    )
    systemProperty("qbank.contracts.dir", file("../contracts").absolutePath)
    // The Testcontainers helper image (Ryuk) is not in docs/VERSIONS.md and is not pulled (D-96);
    // the MQTT test stops its container itself.
    environment("TESTCONTAINERS_RYUK_DISABLED", "true")
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

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
    // Spring Boot is used for bootstrap only (P2.2); domain, port and usecase layers are framework free.
    implementation("org.springframework.boot:spring-boot-starter")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("com.tngtech.archunit:archunit-junit5:1.5.1")
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

tasks.test {
    useJUnitPlatform()
    // The golden inventory lives in reference-system/expected (approved in P1.4, D-123).
    systemProperty("quancrypt.expected.dir", file("../../reference-system/expected").absolutePath)
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

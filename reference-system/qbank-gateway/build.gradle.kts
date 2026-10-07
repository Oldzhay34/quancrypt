plugins {
    java
    checkstyle
    // The gateway is the one QBank service on Spring Boot 4.0.x: the stable Spring Cloud 2025.1.3 (gateway 5.0.3) is
    // built against Boot 4.0.8 (D-39). The other services stay on 4.1.1.
    id("org.springframework.boot") version "4.0.8"
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
    implementation(platform("org.springframework.boot:spring-boot-dependencies:4.0.8"))
    implementation(platform("org.springframework.cloud:spring-cloud-dependencies:2025.1.3"))
    // WebFlux variant: it is the one whose HttpClient accepts an SSL bundle (D-109).
    implementation("org.springframework.cloud:spring-cloud-starter-gateway-server-webflux")
    implementation("org.springframework.boot:spring-boot-starter-actuator")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.withType<JavaCompile> {
    options.compilerArgs.addAll(listOf("-Xlint:all", "-parameters"))
}

tasks.jar {
    enabled = false
}

tasks.bootJar {
    archiveFileName.set("qbank-gateway.jar")
}

tasks.test {
    useJUnitPlatform()
    // Tests use the real certificates (reference-system/certs/out). `make certs` generates them.
    systemProperty(
        "qbank.certs.dir",
        providers.environmentVariable("QBANK_CERTS_DIR").orElse(file("../certs/out").absolutePath).get(),
    )
}

checkstyle {
    toolVersion = "14.3.0"
    configFile = file("config/checkstyle/checkstyle.xml")
    maxWarnings = 0
}

spotbugs {
    toolVersion.set("4.10.4")
}

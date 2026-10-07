package com.quancrypt.qbank.payment.architecture;

import static com.tngtech.archunit.core.domain.JavaClass.Predicates.resideInAPackage;
import static com.tngtech.archunit.core.domain.JavaClass.Predicates.resideInAnyPackage;
import static com.tngtech.archunit.core.domain.JavaClass.Predicates.resideOutsideOfPackage;
import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.classes;
import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;
import static com.tngtech.archunit.library.Architectures.layeredArchitecture;
import static com.tngtech.archunit.library.dependencies.SlicesRuleDefinition.slices;

import com.tngtech.archunit.base.DescribedPredicate;
import com.tngtech.archunit.core.domain.JavaClass;
import com.tngtech.archunit.core.importer.ImportOption;
import com.tngtech.archunit.junit.AnalyzeClasses;
import com.tngtech.archunit.junit.ArchTest;
import com.tngtech.archunit.lang.ArchRule;

/** Layer rules of hexagonal-service, section 2, the framework-free core (D-05) and the crypto boundary (P1.3). */
@AnalyzeClasses(packages = "com.quancrypt.qbank.payment", importOptions = ImportOption.DoNotIncludeTests.class)
class HexagonalArchitectureTest {

    private static final String ROOT = "com.quancrypt.qbank.payment";
    /** Every infrastructure package except config: a new adapter package is covered without editing this test. */
    private static final DescribedPredicate<JavaClass> INFRASTRUCTURE_ADAPTERS = resideInAPackage(ROOT + ".infrastructure..")
            .and(resideOutsideOfPackage(ROOT + ".infrastructure.config.."));

    @ArchTest
    static final ArchRule LAYER_DEPENDENCIES_POINT_INWARD = layeredArchitecture()
            .consideringOnlyDependenciesInLayers()
            .layer("Api").definedBy(ROOT + ".api..")
            .layer("Facade").definedBy(ROOT + ".facade..")
            .layer("PortInbound").definedBy(ROOT + ".port.inbound..")
            .layer("PortOutbound").definedBy(ROOT + ".port.outbound..")
            .layer("UseCase").definedBy(ROOT + ".usecase..")
            .layer("Domain").definedBy(ROOT + ".domain..")
            .layer("Infrastructure").definedBy(INFRASTRUCTURE_ADAPTERS)
            .layer("Config").definedBy(ROOT + ".infrastructure.config..")
            .whereLayer("Api").mayOnlyBeAccessedByLayers("Config")
            .whereLayer("Facade").mayOnlyBeAccessedByLayers("Api", "Config")
            .whereLayer("UseCase").mayOnlyBeAccessedByLayers("Config")
            .whereLayer("Infrastructure").mayOnlyBeAccessedByLayers("Config")
            .whereLayer("Config").mayNotBeAccessedByAnyLayer()
            .whereLayer("PortInbound").mayOnlyBeAccessedByLayers("Facade", "UseCase", "Config")
            .whereLayer("PortOutbound").mayOnlyBeAccessedByLayers("UseCase", "Infrastructure", "Config");

    @ArchTest
    static final ArchRule API_ONLY_DEPENDS_ON_FACADE = noClasses().that().resideInAPackage(ROOT + ".api..")
            .should().dependOnClassesThat(resideInAnyPackage(
                    ROOT + ".port..", ROOT + ".usecase..", ROOT + ".domain..", ROOT + ".infrastructure.."));

    @ArchTest
    static final ArchRule FACADE_ONLY_DEPENDS_ON_PORT_INBOUND = noClasses().that().resideInAPackage(ROOT + ".facade..")
            .should().dependOnClassesThat(resideInAnyPackage(
                    ROOT + ".port.outbound..", ROOT + ".usecase..", ROOT + ".domain..",
                    ROOT + ".infrastructure..", ROOT + ".api.."));

    @ArchTest
    static final ArchRule DOMAIN_DEPENDS_ON_NOTHING_IN_THE_SERVICE = noClasses().that().resideInAPackage(ROOT + ".domain..")
            .should().dependOnClassesThat(resideInAnyPackage(
                    ROOT + ".api..", ROOT + ".facade..", ROOT + ".port..", ROOT + ".usecase..",
                    ROOT + ".infrastructure.."));

    @ArchTest
    static final ArchRule INFRASTRUCTURE_DOES_NOT_USE_USE_CASES_OR_FACADES = noClasses()
            .that(INFRASTRUCTURE_ADAPTERS)
            .should().dependOnClassesThat(resideInAnyPackage(
                    ROOT + ".usecase..", ROOT + ".facade..", ROOT + ".api..", ROOT + ".port.inbound.."));

    @ArchTest
    static final ArchRule CORE_IS_FRAMEWORK_FREE = noClasses()
            .that().resideInAnyPackage(ROOT + ".domain..", ROOT + ".port..", ROOT + ".usecase..")
            .should().dependOnClassesThat(resideInAnyPackage(
                    "org.springframework..", "jakarta..", "com.fasterxml..", "tools.jackson..", "org.slf4j..",
                    "ch.qos.logback..", "com.nimbusds..", "org.eclipse.paho..", "io.github.resilience4j..",
                    "com.networknt.."));

    @ArchTest
    static final ArchRule DOMAIN_USES_ONLY_THE_JDK = classes().that().resideInAPackage(ROOT + ".domain..")
            .should().onlyDependOnClassesThat(resideInAnyPackage("java..", ROOT + ".domain.."));

    /** Acceptance criterion 5: cryptographic calls live only in infrastructure.crypto (stricter than the infrastructure package). */
    @ArchTest
    static final ArchRule CRYPTO_ONLY_IN_INFRASTRUCTURE = noClasses().that().resideOutsideOfPackage(ROOT + ".infrastructure.crypto..")
            .should().dependOnClassesThat(resideInAnyPackage("javax.crypto..", "java.security.."));

    @ArchTest
    static final ArchRule MQTT_CLIENT_ONLY_IN_THE_LISTENER_AND_INFRASTRUCTURE = noClasses()
            .that().resideOutsideOfPackages(ROOT + ".api.mqtt..", ROOT + ".infrastructure..")
            .should().dependOnClassesThat(resideInAnyPackage("org.eclipse.paho.."));

    @ArchTest
    static final ArchRule NO_CYCLES = slices().matching(ROOT + ".(*)..").should().beFreeOfCycles();
}

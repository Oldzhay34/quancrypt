package com.quancrypt.qbank.account.architecture;

import static com.tngtech.archunit.core.domain.JavaClass.Predicates.resideInAnyPackage;
import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;
import static com.tngtech.archunit.library.Architectures.layeredArchitecture;
import static com.tngtech.archunit.library.dependencies.SlicesRuleDefinition.slices;

import com.tngtech.archunit.core.importer.ImportOption;
import com.tngtech.archunit.junit.AnalyzeClasses;
import com.tngtech.archunit.junit.ArchTest;
import com.tngtech.archunit.lang.ArchRule;

/** Layer rules of hexagonal-service, section 2, and the framework-free core (D-05). */
@AnalyzeClasses(packages = "com.quancrypt.qbank.account", importOptions = ImportOption.DoNotIncludeTests.class)
class HexagonalArchitectureTest {

    private static final String ROOT = "com.quancrypt.qbank.account";

    @ArchTest
    static final ArchRule LAYER_DEPENDENCIES_POINT_INWARD = layeredArchitecture()
            .consideringOnlyDependenciesInLayers()
            .layer("Api").definedBy(ROOT + ".api..")
            .layer("Facade").definedBy(ROOT + ".facade..")
            .layer("PortInbound").definedBy(ROOT + ".port.inbound..")
            .layer("PortOutbound").definedBy(ROOT + ".port.outbound..")
            .layer("UseCase").definedBy(ROOT + ".usecase..")
            .layer("Domain").definedBy(ROOT + ".domain..")
            .layer("Infrastructure").definedBy(
                    ROOT + ".infrastructure.persistence..",
                    ROOT + ".infrastructure.security..",
                    ROOT + ".infrastructure.observability..",
                    ROOT + ".infrastructure.time..")
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
            .that().resideInAnyPackage(
                    ROOT + ".infrastructure.persistence..", ROOT + ".infrastructure.security..",
                    ROOT + ".infrastructure.observability..", ROOT + ".infrastructure.time..")
            .should().dependOnClassesThat(resideInAnyPackage(
                    ROOT + ".usecase..", ROOT + ".facade..", ROOT + ".api..", ROOT + ".port.inbound.."));

    @ArchTest
    static final ArchRule CORE_IS_FRAMEWORK_FREE = noClasses()
            .that().resideInAnyPackage(
                    ROOT + ".domain..", ROOT + ".port..", ROOT + ".usecase..")
            .should().dependOnClassesThat(resideInAnyPackage(
                    "org.springframework..", "jakarta..", "com.fasterxml..", "tools.jackson..", "org.slf4j..",
                    "ch.qos.logback..", "com.nimbusds.."));

    @ArchTest
    static final ArchRule DOMAIN_USES_ONLY_THE_JDK = noClasses().that().resideInAPackage(ROOT + ".domain..")
            .should().dependOnClassesThat(resideInAnyPackage(
                    "org..", "io..", "jakarta..", "tools..", "com.fasterxml..", "com.nimbusds..", "com.tngtech.."));

    @ArchTest
    static final ArchRule NO_CYCLES = slices().matching(ROOT + ".(*)..").should().beFreeOfCycles();
}

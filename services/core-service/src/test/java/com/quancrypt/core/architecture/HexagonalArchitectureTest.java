package com.quancrypt.core.architecture;

import com.tngtech.archunit.core.importer.ImportOption;
import com.tngtech.archunit.junit.AnalyzeClasses;
import com.tngtech.archunit.junit.ArchTest;
import com.tngtech.archunit.lang.ArchRule;

import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.classes;
import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;
import static com.tngtech.archunit.library.Architectures.layeredArchitecture;
import static com.tngtech.archunit.library.dependencies.SlicesRuleDefinition.slices;

/** The hexagonal rules of hexagonal-service, section 3; layers without classes yet (api, facade, infrastructure) are optional. */
@AnalyzeClasses(packages = "com.quancrypt.core", importOptions = ImportOption.DoNotIncludeTests.class)
class HexagonalArchitectureTest {

    private static final String[] FRAMEWORKS = {"org.springframework..", "jakarta..", "com.fasterxml..", "tools.jackson.."};

    @ArchTest
    static final ArchRule LAYERS_ONLY_DEPEND_IN_THE_ALLOWED_DIRECTION = layeredArchitecture()
            .consideringAllDependencies()
            .optionalLayer("Api").definedBy("com.quancrypt.core.api..")
            .optionalLayer("Facade").definedBy("com.quancrypt.core.facade..")
            .layer("PortInbound").definedBy("com.quancrypt.core.port.inbound..")
            .layer("PortOutbound").definedBy("com.quancrypt.core.port.outbound..")
            .layer("UseCase").definedBy("com.quancrypt.core.usecase..")
            .layer("Domain").definedBy("com.quancrypt.core.domain..")
            .optionalLayer("Infrastructure").definedBy("com.quancrypt.core.infrastructure..")
            .whereLayer("Api").mayNotBeAccessedByAnyLayer()
            .whereLayer("Facade").mayOnlyBeAccessedByLayers("Api")
            .whereLayer("PortInbound").mayOnlyBeAccessedByLayers("Facade", "UseCase", "Infrastructure")
            .whereLayer("PortOutbound").mayOnlyBeAccessedByLayers("UseCase", "Infrastructure")
            .whereLayer("UseCase").mayOnlyBeAccessedByLayers("Infrastructure")
            .whereLayer("Domain").mayOnlyBeAccessedByLayers("PortInbound", "PortOutbound", "UseCase", "Infrastructure")
            .whereLayer("Infrastructure").mayNotBeAccessedByAnyLayer();

    @ArchTest
    static final ArchRule API_ONLY_SEES_THE_FACADE = noClasses().that().resideInAPackage("com.quancrypt.core.api..")
            .should().dependOnClassesThat().resideInAnyPackage(
                    "com.quancrypt.core.domain..", "com.quancrypt.core.port..", "com.quancrypt.core.usecase..", "com.quancrypt.core.infrastructure..")
            .allowEmptyShould(true);

    @ArchTest
    static final ArchRule FACADE_ONLY_SEES_INBOUND_PORTS = noClasses().that().resideInAPackage("com.quancrypt.core.facade..")
            .should().dependOnClassesThat().resideInAnyPackage(
                    "com.quancrypt.core.domain..", "com.quancrypt.core.port.outbound..", "com.quancrypt.core.usecase..", "com.quancrypt.core.infrastructure..")
            .allowEmptyShould(true);

    @ArchTest
    static final ArchRule INBOUND_PORTS_DO_NOT_LEAK_DOMAIN_TYPES = noClasses().that().resideInAPackage("com.quancrypt.core.port.inbound..")
            .should().dependOnClassesThat().resideInAPackage("com.quancrypt.core.domain..");

    @ArchTest
    static final ArchRule DOMAIN_PORT_AND_USE_CASE_USE_NO_FRAMEWORK = noClasses().that().resideInAnyPackage(
                    "com.quancrypt.core.domain..", "com.quancrypt.core.port..", "com.quancrypt.core.usecase..")
            .should().dependOnClassesThat().resideInAnyPackage(FRAMEWORKS);

    @ArchTest
    static final ArchRule DOMAIN_DEPENDS_ON_THE_JDK_ONLY = classes().that().resideInAPackage("com.quancrypt.core.domain..")
            .should().onlyDependOnClassesThat().resideInAnyPackage("com.quancrypt.core.domain..", "java..");

    @ArchTest
    static final ArchRule PORTS_DEPEND_ONLY_ON_THE_DOMAIN_AND_THE_JDK = classes().that().resideInAPackage("com.quancrypt.core.port..")
            .should().onlyDependOnClassesThat().resideInAnyPackage("com.quancrypt.core.domain..", "com.quancrypt.core.port..", "java..");

    @ArchTest
    static final ArchRule NO_CYCLES = slices().matching("com.quancrypt.core.(*)..").should().beFreeOfCycles();
}

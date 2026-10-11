package com.quancrypt.analyzer.architecture;

import com.tngtech.archunit.base.DescribedPredicate;
import com.tngtech.archunit.core.domain.JavaClass;
import com.tngtech.archunit.core.importer.ImportOption;
import com.tngtech.archunit.junit.AnalyzeClasses;
import com.tngtech.archunit.junit.ArchTest;
import com.tngtech.archunit.lang.ArchRule;

import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.classes;
import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;
import static com.tngtech.archunit.library.Architectures.layeredArchitecture;
import static com.tngtech.archunit.library.dependencies.SlicesRuleDefinition.slices;

/**
 * The hexagonal rules of hexagonal-service, sections 2 and 3, as in core-service. Only the composition root
 * (infrastructure.config, empty in P3.1) may see every layer.
 */
@AnalyzeClasses(packages = "com.quancrypt.analyzer", importOptions = ImportOption.DoNotIncludeTests.class)
class HexagonalArchitectureTest {

    private static final String[] FRAMEWORKS = {"org.springframework..", "jakarta..", "com.fasterxml..", "tools.jackson.."};

    @ArchTest
    static final ArchRule LAYERS_ONLY_DEPEND_IN_THE_ALLOWED_DIRECTION = layeredArchitecture()
            .consideringAllDependencies()
            .optionalLayer("Api").definedBy("com.quancrypt.analyzer.api..")
            .optionalLayer("Facade").definedBy("com.quancrypt.analyzer.facade..")
            .layer("PortInbound").definedBy("com.quancrypt.analyzer.port.inbound..")
            .layer("PortOutbound").definedBy("com.quancrypt.analyzer.port.outbound..")
            .layer("UseCase").definedBy("com.quancrypt.analyzer.usecase..")
            .layer("Domain").definedBy("com.quancrypt.analyzer.domain..")
            .optionalLayer("Infrastructure").definedBy("com.quancrypt.analyzer.infrastructure..")
            .whereLayer("Api").mayNotBeAccessedByAnyLayer()
            .whereLayer("Facade").mayOnlyBeAccessedByLayers("Api")
            .whereLayer("PortInbound").mayOnlyBeAccessedByLayers("Facade", "UseCase", "Infrastructure")
            .whereLayer("PortOutbound").mayOnlyBeAccessedByLayers("UseCase", "Infrastructure")
            .whereLayer("UseCase").mayOnlyBeAccessedByLayers("Infrastructure")
            .whereLayer("Domain").mayOnlyBeAccessedByLayers("PortInbound", "PortOutbound", "UseCase", "Infrastructure")
            .whereLayer("Infrastructure").mayNotBeAccessedByAnyLayer()
            .ignoreDependency(JavaClass.Predicates.resideInAPackage("com.quancrypt.analyzer.infrastructure.config.."),
                    DescribedPredicate.alwaysTrue());

    @ArchTest
    static final ArchRule ADAPTERS_DO_NOT_DRIVE_USE_CASES = noClasses().that().resideInAPackage("com.quancrypt.analyzer.infrastructure..")
            .and().resideOutsideOfPackage("com.quancrypt.analyzer.infrastructure.config..")
            .should().dependOnClassesThat().resideInAnyPackage("com.quancrypt.analyzer.usecase..",
                    "com.quancrypt.analyzer.port.inbound..", "com.quancrypt.analyzer.facade..", "com.quancrypt.analyzer.api..");

    @ArchTest
    static final ArchRule INBOUND_PORTS_DO_NOT_LEAK_DOMAIN_TYPES = noClasses().that().resideInAPackage("com.quancrypt.analyzer.port.inbound..")
            .should().dependOnClassesThat().resideInAPackage("com.quancrypt.analyzer.domain..");

    @ArchTest
    static final ArchRule DOMAIN_PORT_AND_USE_CASE_USE_NO_FRAMEWORK = noClasses().that().resideInAnyPackage(
                    "com.quancrypt.analyzer.domain..", "com.quancrypt.analyzer.port..", "com.quancrypt.analyzer.usecase..")
            .should().dependOnClassesThat().resideInAnyPackage(FRAMEWORKS);

    @ArchTest
    static final ArchRule DOMAIN_DEPENDS_ON_THE_JDK_ONLY = classes().that().resideInAPackage("com.quancrypt.analyzer.domain..")
            .should().onlyDependOnClassesThat().resideInAnyPackage("com.quancrypt.analyzer.domain..", "java..");

    @ArchTest
    static final ArchRule PORTS_DEPEND_ONLY_ON_THE_DOMAIN_AND_THE_JDK = classes().that().resideInAPackage("com.quancrypt.analyzer.port..")
            .should().onlyDependOnClassesThat().resideInAnyPackage("com.quancrypt.analyzer.domain..", "com.quancrypt.analyzer.port..", "java..");

    @ArchTest
    static final ArchRule USE_CASES_DO_NOT_TOUCH_THE_FILE_SYSTEM = noClasses().that().resideInAnyPackage(
                    "com.quancrypt.analyzer.domain..", "com.quancrypt.analyzer.port..", "com.quancrypt.analyzer.usecase..")
            .should().dependOnClassesThat().resideInAnyPackage("java.nio.file..", "java.io..")
            .because("files are read only through the SourceTreeReader port, whose adapter enforces path safety");

    @ArchTest
    static final ArchRule LANGUAGE_PLUGINS_ARE_ADAPTERS = classes().that().implement(com.quancrypt.analyzer.port.outbound.LanguagePlugin.class)
            .should().resideInAPackage("com.quancrypt.analyzer.infrastructure..")
            .allowEmptyShould(true);

    @ArchTest
    static final ArchRule NO_CYCLES = slices().matching("com.quancrypt.analyzer.(*)..").should().beFreeOfCycles();
}

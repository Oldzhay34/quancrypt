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
 * (infrastructure.config) may see every layer.
 */
@AnalyzeClasses(packages = "com.quancrypt.analyzer", importOptions = {ImportOption.DoNotIncludeTests.class,
        HexagonalArchitectureTest.WithoutEvaluationTooling.class})
class HexagonalArchitectureTest {

    /** The evaluation code (eval source set, on the test class path) is tooling around the service, not a part of it. */
    static final class WithoutEvaluationTooling implements ImportOption {

        @Override
        public boolean includes(com.tngtech.archunit.core.importer.Location location) {
            return !location.contains("/evaluation/");
        }
    }

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
            .should().resideInAPackage("com.quancrypt.analyzer.infrastructure..");

    @ArchTest
    static final ArchRule DETECTORS_LIVE_IN_THE_PLUGIN = classes().that().implement(
                    com.quancrypt.analyzer.infrastructure.plugin.javaspring.CryptoDetector.class)
            .should().resideInAnyPackage("com.quancrypt.analyzer.infrastructure.plugin.javaspring.code..",
                    "com.quancrypt.analyzer.infrastructure.plugin.javaspring.file..");

    @ArchTest
    static final ArchRule SOURCE_PARSERS_ARE_ADAPTER_DETAILS = noClasses().that().resideOutsideOfPackage("com.quancrypt.analyzer.infrastructure..")
            .should().dependOnClassesThat().resideInAnyPackage("com.github.javaparser..", "org.yaml..", "javax.xml..")
            .because("parsing Java, YAML and XML belongs to the language plugin");

    @ArchTest
    static final ArchRule NOTHING_WRITES_TO_THE_ANALYZED_PROJECT = noClasses().should().callMethod(java.nio.file.Files.class, "write",
            java.nio.file.Path.class, byte[].class, java.nio.file.OpenOption[].class)
            .orShould().callMethod(java.nio.file.Files.class, "delete", java.nio.file.Path.class)
            .orShould().callMethod(java.nio.file.Files.class, "writeString", java.nio.file.Path.class, CharSequence.class,
                    java.nio.file.OpenOption[].class)
            .because("the analyzer only reads the project (read-only mount, D-176)");

    @ArchTest
    static final ArchRule CYCLONEDX_STAYS_IN_THE_CBOM_ADAPTER = noClasses().that()
            .resideOutsideOfPackage("com.quancrypt.analyzer.infrastructure.cbom..")
            .should().dependOnClassesThat().resideInAPackage("org.cyclonedx..")
            .because("the CBOM library is a detail of the CycloneDxCbomWriter (D-202)");

    @ArchTest
    static final ArchRule USE_CASES_DEPEND_ONLY_ON_DOMAIN_PORTS_AND_THE_JDK = classes().that()
            .resideInAPackage("com.quancrypt.analyzer.usecase..")
            .should().onlyDependOnClassesThat().resideInAnyPackage("com.quancrypt.analyzer.usecase..", "com.quancrypt.analyzer.domain..",
                    "com.quancrypt.analyzer.port..", "java..");

    @ArchTest
    static final ArchRule FACADE_USES_NO_FRAMEWORK = noClasses().that().resideInAPackage("com.quancrypt.analyzer.facade..")
            .should().dependOnClassesThat().resideInAnyPackage(FRAMEWORKS);

    @ArchTest
    static final ArchRule NO_CYCLES = slices().matching("com.quancrypt.analyzer.(*)..").should().beFreeOfCycles();
}

package com.quancrypt.analyzer.unit.usecase;

import static com.quancrypt.analyzer.unit.usecase.Fixtures.GRADLE_ROOT;
import static com.quancrypt.analyzer.unit.usecase.Fixtures.MAVEN_ROOT;
import static com.quancrypt.analyzer.unit.usecase.Fixtures.assertProblem;
import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.analyzer.fake.InMemorySourceTreeReader;
import com.quancrypt.analyzer.port.inbound.DetectProjectTypeCommand;
import com.quancrypt.analyzer.port.inbound.ProblemCode;
import com.quancrypt.analyzer.port.inbound.ProjectView;
import com.quancrypt.analyzer.usecase.DetectProjectTypeService;
import org.junit.jupiter.api.Test;

class DetectProjectTypeServiceTest {

    private final InMemorySourceTreeReader reader = Fixtures.projects();
    private final DetectProjectTypeService service = new DetectProjectTypeService(Fixtures.opener(reader));

    @Test
    void detectsMavenAndGradle() {
        assertThat(service.detect(new DetectProjectTypeCommand(MAVEN_ROOT))).isEqualTo(new ProjectView(MAVEN_ROOT, "MAVEN"));
        assertThat(service.detect(new DetectProjectTypeCommand(GRADLE_ROOT))).isEqualTo(new ProjectView(GRADLE_ROOT, "GRADLE"));
    }

    @Test
    void twoBuildSystemsOrNoneAreUnsupported() {
        reader.file("/workspace/both", "pom.xml", "").file("/workspace/both", "settings.gradle", "")
                .file("/workspace/none", "package.json", "{}");

        assertProblem(() -> service.detect(new DetectProjectTypeCommand("/workspace/both")), ProblemCode.UNSUPPORTED_PROJECT);
        assertProblem(() -> service.detect(new DetectProjectTypeCommand("/workspace/none")), ProblemCode.UNSUPPORTED_PROJECT);
    }

    @Test
    void rootsOutsideTheAllowedDirectoriesOrWithDotsAreRefused() {
        assertProblem(() -> service.detect(new DetectProjectTypeCommand("/etc")), ProblemCode.PATH_NOT_ALLOWED);
        assertProblem(() -> service.detect(new DetectProjectTypeCommand("/workspace/../etc")), ProblemCode.PATH_NOT_ALLOWED);
        assertProblem(() -> service.detect(new DetectProjectTypeCommand("workspace/maven")), ProblemCode.PATH_NOT_ALLOWED);
        assertProblem(() -> service.detect(new DetectProjectTypeCommand(null)), ProblemCode.PATH_NOT_ALLOWED);
    }

    @Test
    void aMissingOrLinkedRootIsRefused() {
        reader.file("/workspace/linked", "pom.xml", "").linkedRoot("/workspace/linked");

        assertProblem(() -> service.detect(new DetectProjectTypeCommand("/workspace/nothing")), ProblemCode.PATH_NOT_ALLOWED);
        assertProblem(() -> service.detect(new DetectProjectTypeCommand("/workspace/linked")), ProblemCode.PATH_NOT_ALLOWED);
    }

    @Test
    void aBuildFileThatIsASymbolicLinkIsRefused() {
        reader.file("/workspace/trap", "pom.xml", "").link("/workspace/trap", "pom.xml");

        assertProblem(() -> service.detect(new DetectProjectTypeCommand("/workspace/trap")), ProblemCode.PATH_NOT_ALLOWED);
    }
}

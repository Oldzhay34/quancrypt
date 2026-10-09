package com.quancrypt.core.unit.usecase;

import com.quancrypt.core.domain.model.AuditAction;
import com.quancrypt.core.domain.model.ScanArtifact;
import com.quancrypt.core.fake.World;
import com.quancrypt.core.port.inbound.ClarificationAnswerInput;
import com.quancrypt.core.port.inbound.GetProjectProfileQuery;
import com.quancrypt.core.port.inbound.GetScanArtifactQuery;
import com.quancrypt.core.port.inbound.ProblemCode;
import com.quancrypt.core.port.inbound.RecordScanArtifactCommand;
import com.quancrypt.core.port.inbound.SaveClarificationAnswersCommand;
import com.quancrypt.core.port.inbound.view.ProjectProfileView;
import com.quancrypt.core.port.inbound.view.ScanArtifactContentView;
import com.quancrypt.core.port.inbound.view.ScanArtifactView;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.Test;

import static com.quancrypt.core.fake.Problems.assertProblem;
import static org.assertj.core.api.Assertions.assertThat;

class ArtifactAndClarificationTest {

    private final World w = new World();

    private RecordScanArtifactCommand artifact(UUID scanId, String type, byte[] content) {
        return new RecordScanArtifactCommand(scanId, type, content, "INTERNAL");
    }

    @Test
    void theCbomIsStoredWithItsSha256AndReplacedByTheNextOne() {
        UUID scanId = w.runningScan(w.project());
        byte[] cbom = "{\"bomFormat\":\"CycloneDX\"}".getBytes(StandardCharsets.UTF_8);
        ScanArtifactView stored = w.recordScanArtifact.execute(artifact(scanId, "application/vnd.cyclonedx+json", cbom));
        assertThat(stored.sha256()).isEqualTo(ScanArtifact.sha256Hex(cbom));
        w.recordScanArtifact.execute(artifact(scanId, "application/json", "{}".getBytes(StandardCharsets.UTF_8)));
        assertThat(w.db.artifacts).hasSize(1);
        ScanArtifactContentView read = w.getScanArtifact.execute(new GetScanArtifactQuery(scanId));
        assertThat(read.content()).isEqualTo("{}".getBytes(StandardCharsets.UTF_8));
        assertThat(read.contentType()).isEqualTo("application/json");
        assertThat(w.auditActions().stream().filter(a -> a == AuditAction.SCAN_ARTIFACT_RECORDED)).hasSize(2);
        assertThat(w.db.lockLog).contains("scan:noKeyUpdate");
    }

    @Test
    void sizeTypeAndScanStateAreChecked() {
        UUID scanId = w.runningScan(w.project());
        assertProblem(() -> w.recordScanArtifact.execute(artifact(scanId, "application/json", new byte[ScanArtifact.MAX_BYTES + 1])), ProblemCode.PAYLOAD_TOO_LARGE);
        assertThat(w.recordScanArtifact.execute(artifact(scanId, "application/json", new byte[ScanArtifact.MAX_BYTES])).sha256()).hasSize(64);
        assertProblem(() -> w.recordScanArtifact.execute(artifact(scanId, "text/plain", new byte[1])), ProblemCode.UNSUPPORTED_MEDIA_TYPE);
        assertProblem(() -> w.recordScanArtifact.execute(artifact(scanId, null, new byte[1])), ProblemCode.UNSUPPORTED_MEDIA_TYPE);
        w.complete(scanId);
        assertProblem(() -> w.recordScanArtifact.execute(artifact(scanId, "application/json", new byte[1])), ProblemCode.SCAN_NOT_RUNNING);
        assertProblem(() -> w.recordScanArtifact.execute(artifact(new UUID(9, 9), "application/json", new byte[1])), ProblemCode.NOT_FOUND);
        assertProblem(() -> w.getScanArtifact.execute(new GetScanArtifactQuery(new UUID(9, 9))), ProblemCode.NOT_FOUND);
    }

    private SaveClarificationAnswersCommand answers(UUID projectId, ClarificationAnswerInput... answers) {
        return new SaveClarificationAnswersCommand(projectId, List.of(answers), "UI");
    }

    @Test
    void clarificationAnswersAreSavedPerQuestionAndReadBackWithTheProfile() {
        UUID projectId = w.project();
        ProjectProfileView saved = w.saveClarificationAnswers.execute(answers(projectId,
                new ClarificationAnswerInput("TLS_TERMINATION", Optional.of("INGRESS"), Optional.empty()),
                new ClarificationAnswerInput("COMPLIANCE_REQUIREMENT", Optional.of("YES"), Optional.of("FIPS 140")),
                new ClarificationAnswerInput("DEVICE_HARDWARE_OPENSSL", Optional.empty(), Optional.of("PYNQ-Z2, OpenSSL 3.5"))));
        assertThat(saved.answers()).hasSize(3);
        w.saveClarificationAnswers.execute(answers(projectId, new ClarificationAnswerInput("TLS_TERMINATION", Optional.of("APPLICATION"), Optional.empty())));
        ProjectProfileView profile = w.getProjectProfile.execute(new GetProjectProfileQuery(projectId));
        assertThat(profile.answers()).hasSize(3).anySatisfy(a -> {
            assertThat(a.questionCode()).isEqualTo("TLS_TERMINATION");
            assertThat(a.optionCode()).hasValue("APPLICATION");
        });
        assertThat(w.auditActions().stream().filter(a -> a == AuditAction.CLARIFICATION_ANSWERS_SAVED)).hasSize(2);
        assertThat(w.db.lockLog).contains("project:keyShare");
    }

    @Test
    void clarificationAnswersMustFitTheirQuestion() {
        UUID projectId = w.project();
        assertProblem(() -> w.saveClarificationAnswers.execute(answers(projectId)), ProblemCode.VALIDATION_FAILED);
        assertProblem(() -> w.saveClarificationAnswers.execute(answers(projectId,
                new ClarificationAnswerInput("NO_SUCH_QUESTION", Optional.of("YES"), Optional.empty()))), ProblemCode.VALIDATION_FAILED);
        assertProblem(() -> w.saveClarificationAnswers.execute(answers(projectId,
                new ClarificationAnswerInput("TLS_TERMINATION", Optional.of("MOON"), Optional.empty()))), ProblemCode.VALIDATION_FAILED);
        assertProblem(() -> w.saveClarificationAnswers.execute(answers(projectId,
                new ClarificationAnswerInput("TLS_TERMINATION", Optional.of("INGRESS"), Optional.empty()),
                new ClarificationAnswerInput("TLS_TERMINATION", Optional.of("APPLICATION"), Optional.empty()))), ProblemCode.VALIDATION_FAILED);
        assertProblem(() -> w.saveClarificationAnswers.execute(answers(new UUID(9, 9),
                new ClarificationAnswerInput("TLS_TERMINATION", Optional.of("INGRESS"), Optional.empty()))), ProblemCode.NOT_FOUND);
        assertProblem(() -> w.getProjectProfile.execute(new GetProjectProfileQuery(new UUID(9, 9))), ProblemCode.NOT_FOUND);
        assertThat(w.db.answers).isEmpty();
    }
}

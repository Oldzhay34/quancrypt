package com.quancrypt.core.unit.domain;

import com.quancrypt.core.domain.model.AlgorithmFamily;
import com.quancrypt.core.domain.model.AuditAction;
import com.quancrypt.core.domain.model.AuditEntry;
import com.quancrypt.core.domain.model.CallSite;
import com.quancrypt.core.domain.model.CallerKind;
import com.quancrypt.core.domain.model.ClarificationAnswer;
import com.quancrypt.core.domain.model.ClarificationQuestion;
import com.quancrypt.core.domain.model.ClassifiedBy;
import com.quancrypt.core.domain.model.Consent;
import com.quancrypt.core.domain.model.ConsentType;
import com.quancrypt.core.domain.model.EventType;
import com.quancrypt.core.domain.model.Finding;
import com.quancrypt.core.domain.model.IdempotencyRecord;
import com.quancrypt.core.domain.model.JavaVersion;
import com.quancrypt.core.domain.model.LocationKind;
import com.quancrypt.core.domain.model.NodeKind;
import com.quancrypt.core.domain.model.PageResult;
import com.quancrypt.core.domain.model.Priority;
import com.quancrypt.core.domain.model.PrivacyNotice;
import com.quancrypt.core.domain.model.Project;
import com.quancrypt.core.domain.model.ProjectKey;
import com.quancrypt.core.domain.model.Protocol;
import com.quancrypt.core.domain.model.QuantumStatus;
import com.quancrypt.core.domain.model.RiskFactor;
import com.quancrypt.core.domain.model.RiskScore;
import com.quancrypt.core.domain.model.RuntimeProfile;
import com.quancrypt.core.domain.model.Scan;
import com.quancrypt.core.domain.model.ScanArtifact;
import com.quancrypt.core.domain.model.ScanStatus;
import com.quancrypt.core.domain.model.ServiceLink;
import com.quancrypt.core.domain.model.ServiceNode;
import com.quancrypt.core.domain.model.SourceFile;
import com.quancrypt.core.domain.model.Topology;
import com.quancrypt.core.domain.model.UsageContext;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class ModelValidationTest {

    private static final Instant NOW = Instant.parse("2026-10-09T10:00:00Z");

    @Test
    void javaVersionsAreParsedFromRealWorldStrings() {
        assertThat(JavaVersion.parse("25.0.4.1")).hasValue(new JavaVersion(25));
        assertThat(JavaVersion.parse("17.0.2+8")).hasValue(new JavaVersion(17));
        assertThat(JavaVersion.parse("1.8.0_302")).hasValue(new JavaVersion(8));
        assertThat(JavaVersion.parse("21")).hasValue(new JavaVersion(21));
        assertThat(JavaVersion.parse("nonsense")).isEmpty();
        assertThat(JavaVersion.parse(null)).isEmpty();
        assertThat(new JavaVersion(24).isAtLeast(24)).isTrue();
        assertThat(new JavaVersion(23).isAtLeast(24)).isFalse();
        assertThatThrownBy(() -> new JavaVersion(0)).isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void aProjectKeyIsExactly64LowercaseHexCharacters() {
        assertThat(new ProjectKey("a".repeat(64)).value()).hasSize(64);
        assertThatThrownBy(() -> new ProjectKey("A".repeat(64))).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new ProjectKey("abc")).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new ProjectKey(null)).isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void projectsRuntimeProfilesAndSourceFilesCheckTheirFields() {
        ProjectKey key = new ProjectKey("a".repeat(64));
        assertThatThrownBy(() -> new Project(new UUID(0, 1), key, " ", NOW)).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new Project(new UUID(0, 1), key, "x".repeat(201), NOW)).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new RuntimeProfile(0, "25", Optional.empty(), NOW)).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new RuntimeProfile(1, "not a version!", Optional.empty(), NOW)).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new RuntimeProfile(1, "25", Optional.of("bad version"), NOW)).isInstanceOf(IllegalArgumentException.class);
        assertThat(new RuntimeProfile(1, "25.0.4.1", Optional.of("4.1.1"), NOW).java()).hasValue(new JavaVersion(25));
        assertThat(new RuntimeProfile(1, "25", Optional.empty(), NOW).sameVersionsAs("25", Optional.empty())).isTrue();
        assertThatThrownBy(() -> new SourceFile(new UUID(0, 1), new UUID(0, 2), "", LocationKind.CODE)).isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void findingsCheckConfidenceKeySizeAndLines() {
        UUID id = new UUID(0, 1);
        assertThat(new Finding(id, id, "A#b", AlgorithmFamily.RSA, UsageContext.SIGNATURE, Priority.P2, Optional.empty(), Optional.of(3), Optional.of(3), 1.0,
                ClassifiedBy.LLM).cryptoUsage(LocationKind.CODE).algorithm()).isEqualTo(AlgorithmFamily.RSA);
        assertThatThrownBy(() -> new Finding(id, id, "", AlgorithmFamily.RSA, UsageContext.SIGNATURE, Priority.P2, Optional.empty(), Optional.empty(), Optional.empty(), 0.5, ClassifiedBy.STATIC))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new Finding(id, id, "A", AlgorithmFamily.RSA, UsageContext.SIGNATURE, Priority.P2, Optional.empty(), Optional.empty(), Optional.empty(), 1.5, ClassifiedBy.STATIC))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new Finding(id, id, "A", AlgorithmFamily.RSA, UsageContext.SIGNATURE, Priority.P2, Optional.of(0), Optional.empty(), Optional.empty(), 0.5, ClassifiedBy.STATIC))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new Finding(id, id, "A", AlgorithmFamily.RSA, UsageContext.SIGNATURE, Priority.P2, Optional.empty(), Optional.of(5), Optional.empty(), 0.5, ClassifiedBy.STATIC))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new Finding(id, id, "A", AlgorithmFamily.RSA, UsageContext.SIGNATURE, Priority.P2, Optional.empty(), Optional.of(5), Optional.of(4), 0.5, ClassifiedBy.STATIC))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void consentsRevokeAndRegrantWithAVersionBump() {
        PrivacyNotice notice = new PrivacyNotice(new UUID(0, 9), 1, "tr", "en", NOW);
        Consent granted = Consent.firstGrant(new UUID(0, 1), new UUID(0, 2), ConsentType.WAREHOUSE_ANALYTICS, notice, NOW);
        assertThat(granted.isActive()).isTrue();
        assertThat(granted.version()).isZero();
        Consent revoked = granted.revoke(NOW.plusSeconds(1));
        assertThat(revoked.isActive()).isFalse();
        assertThat(revoked.version()).isEqualTo(1);
        assertThatThrownBy(() -> revoked.revoke(NOW)).isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(() -> granted.regrant(notice, NOW)).isInstanceOf(IllegalStateException.class);
        Consent again = revoked.regrant(notice, NOW.plusSeconds(2));
        assertThat(again.isActive()).isTrue();
        assertThat(again.version()).isEqualTo(2);
    }

    @Test
    void scansFinishOnlyOnceAndOnlyWithAFinalStatus() {
        Scan running = Scan.start(new UUID(0, 1), new UUID(0, 2), Optional.of(1), NOW);
        assertThat(running.isRunning()).isTrue();
        Scan done = running.finish(ScanStatus.COMPLETED, NOW.plusSeconds(5));
        assertThat(done.completedAt()).hasValue(NOW.plusSeconds(5));
        assertThatThrownBy(() -> done.finish(ScanStatus.FAILED, NOW)).isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(() -> running.finish(ScanStatus.RUNNING, NOW)).isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(() -> new Scan(new UUID(0, 1), new UUID(0, 2), Optional.empty(), ScanStatus.RUNNING, NOW, Optional.of(NOW)))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void topologiesKeepTheirNodesAndLinksConsistent() {
        ServiceNode gateway = new ServiceNode(new UUID(0, 1), "gateway", NodeKind.GATEWAY);
        ServiceNode device = new ServiceNode(new UUID(0, 2), "terminal", NodeKind.DEVICE);
        ServiceNode broker = new ServiceNode(new UUID(0, 3), "broker", NodeKind.BROKER);
        ServiceLink deviceLink = new ServiceLink(new UUID(0, 10), device.id(), broker.id(), Protocol.MQTT, true, true, List.of(), Set.of());
        ServiceLink plain = new ServiceLink(new UUID(0, 11), gateway.id(), broker.id(), Protocol.HTTP, true, false, List.of(), Set.of());
        Topology topology = new Topology(new UUID(0, 20), new UUID(0, 21), NOW, List.of(gateway, device, broker), List.of(deviceLink, plain));
        assertThat(topology.isDeviceLink(deviceLink)).isTrue();
        assertThat(topology.isDeviceLink(plain)).isFalse();
        assertThatThrownBy(() -> new Topology(new UUID(0, 20), new UUID(0, 21), NOW, List.of(gateway, gateway), List.of()))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new Topology(new UUID(0, 20), new UUID(0, 21), NOW, List.of(gateway), List.of(plain)))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new Topology(new UUID(0, 20), new UUID(0, 21), NOW, List.of(gateway, broker), List.of(plain, plain)))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new ServiceLink(new UUID(0, 12), gateway.id(), gateway.id(), Protocol.HTTP, true, false, List.of(), Set.of()))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new ServiceLink(new UUID(0, 12), gateway.id(), broker.id(), Protocol.HTTP, false, true, List.of(), Set.of()))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new CallSite(new UUID(0, 1), 5, 4)).isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void clarificationAnswersMustHaveTheShapeTheirQuestionNeeds() {
        assertThat(new ClarificationAnswer(ClarificationQuestion.TLS_TERMINATION, Optional.of("INGRESS"), Optional.empty(), NOW).option()).hasValue("INGRESS");
        assertThatThrownBy(() -> new ClarificationAnswer(ClarificationQuestion.TLS_TERMINATION, Optional.of("MOON"), Optional.empty(), NOW))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new ClarificationAnswer(ClarificationQuestion.TLS_TERMINATION, Optional.empty(), Optional.empty(), NOW))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new ClarificationAnswer(ClarificationQuestion.JDK_UPGRADE_POSSIBLE, Optional.of("YES"), Optional.of("why"), NOW))
                .isInstanceOf(IllegalArgumentException.class);
        assertThat(new ClarificationAnswer(ClarificationQuestion.COMPLIANCE_REQUIREMENT, Optional.of("YES"), Optional.of("FIPS 140"), NOW).freeText()).hasValue("FIPS 140");
        assertThat(new ClarificationAnswer(ClarificationQuestion.DEVICE_HARDWARE_OPENSSL, Optional.empty(), Optional.of("PYNQ-Z2, OpenSSL 3.5"), NOW).option()).isEmpty();
        assertThatThrownBy(() -> new ClarificationAnswer(ClarificationQuestion.DEVICE_HARDWARE_OPENSSL, Optional.of("YES"), Optional.of("x"), NOW))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new ClarificationAnswer(ClarificationQuestion.COMPLIANCE_REQUIREMENT, Optional.of("YES"), Optional.of("x".repeat(501)), NOW))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void riskScoresFactorsArtifactsAuditAndPagesCheckTheirRanges() {
        assertThat(RiskScore.of(0.12345).value()).isEqualByComparingTo("0.1235");
        assertThatThrownBy(() -> RiskScore.of(1.01)).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> RiskScore.of(-0.1)).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> RiskScore.of(Double.NaN)).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new RiskFactor(0, "feature", BigDecimal.ONE)).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new RiskFactor(1, "Bad Name", BigDecimal.ONE)).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new RiskFactor(1, "feature", new BigDecimal("1000"))).isInstanceOf(IllegalArgumentException.class);
        byte[] bytes = "{}".getBytes(StandardCharsets.UTF_8);
        ScanArtifact artifact = ScanArtifact.of(new UUID(0, 1), "application/json", bytes, NOW);
        bytes[0] = 0;
        assertThat(artifact.content()).isEqualTo("{}".getBytes(StandardCharsets.UTF_8));
        assertThat(artifact.sha256()).hasSize(64);
        assertThatThrownBy(() -> ScanArtifact.of(new UUID(0, 1), "", bytes, NOW)).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new AuditEntry(new UUID(0, 1), NOW, AuditAction.SCAN_STARTED, Optional.empty(), Optional.empty(), CallerKind.UI))
                .isInstanceOf(IllegalArgumentException.class);
        assertThat(new AuditEntry(new UUID(0, 1), NOW, AuditAction.OUTBOX_EVENTS_RELAYED, Optional.empty(), Optional.empty(), CallerKind.INTERNAL).action())
                .isEqualTo(AuditAction.OUTBOX_EVENTS_RELAYED);
        assertThatThrownBy(() -> new PageResult<>(List.of(), -1, 10, 0)).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new PageResult<>(List.of(), 0, 201, 0)).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new IdempotencyRecord(" ", AuditAction.SCAN_STARTED, "d", 202, Optional.empty(), NOW)).isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void algorithmFamiliesKnowTheirQuantumStatus() {
        assertThat(AlgorithmFamily.RSA.quantumStatus()).hasValue(QuantumStatus.VULNERABLE);
        assertThat(AlgorithmFamily.ML_KEM.quantumStatus()).hasValue(QuantumStatus.RESISTANT);
        assertThat(AlgorithmFamily.AES.quantumStatus()).hasValue(QuantumStatus.SYMMETRIC_OR_HASH);
        assertThat(AlgorithmFamily.UNKNOWN.quantumStatus()).isEmpty();
        assertThat(EventType.FINDING_DETECTED.code()).isEqualTo("finding_detected");
    }
}

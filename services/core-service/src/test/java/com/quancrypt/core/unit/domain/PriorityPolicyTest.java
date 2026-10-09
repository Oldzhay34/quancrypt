package com.quancrypt.core.unit.domain;

import com.quancrypt.core.domain.exception.FindingRejectedException;
import com.quancrypt.core.domain.model.AlgorithmFamily;
import com.quancrypt.core.domain.model.CryptoUsage;
import com.quancrypt.core.domain.model.LocationKind;
import com.quancrypt.core.domain.model.Priority;
import com.quancrypt.core.domain.model.UsageContext;
import com.quancrypt.core.domain.policy.PriorityClassifier;
import com.quancrypt.core.domain.policy.PriorityPolicy;
import java.util.Optional;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class PriorityPolicyTest {

    private final PriorityPolicy policy = new PriorityPolicy(new PriorityClassifier());

    private static CryptoUsage usage(AlgorithmFamily algorithm, UsageContext context) {
        return new CryptoUsage(algorithm, context, Optional.of(2048), LocationKind.CODE);
    }

    @Test
    void aPriorityThatAgreesWithTheTableIsAccepted() {
        assertThat(policy.accept(usage(AlgorithmFamily.RSA, UsageContext.TLS_KEY_EXCHANGE), Priority.P1)).isEqualTo(Priority.P1);
    }

    @Test
    void aPriorityThatDisagreesWithTheTableIsRejected() {
        assertThatThrownBy(() -> policy.accept(usage(AlgorithmFamily.RSA, UsageContext.TLS_KEY_EXCHANGE), Priority.P3))
                .isInstanceOfSatisfying(FindingRejectedException.class, e -> assertThat(e.reason()).isEqualTo(FindingRejectedException.Reason.PRIORITY_MISMATCH));
    }

    @Test
    void aFindingThatNeedsNoMigrationIsRejected() {
        assertThatThrownBy(() -> policy.accept(usage(AlgorithmFamily.SHA2, UsageContext.HASH), Priority.P3))
                .isInstanceOfSatisfying(FindingRejectedException.class, e -> assertThat(e.reason()).isEqualTo(FindingRejectedException.Reason.NO_MIGRATION_NEEDED));
    }

    @Test
    void anUndeterminedUsageKeepsTheSuppliedPriority() {
        assertThat(policy.accept(usage(AlgorithmFamily.UNKNOWN, UsageContext.TLS_KEY_EXCHANGE), Priority.P2)).isEqualTo(Priority.P2);
    }

    @Test
    void p0IsAcceptedForAesAndRsaBecauseEcbAndPkcs1V15CannotBeDerived() {
        assertThat(policy.accept(usage(AlgorithmFamily.AES, UsageContext.ENCRYPTION), Priority.P0)).isEqualTo(Priority.P0);
        assertThat(policy.accept(usage(AlgorithmFamily.RSA, UsageContext.ENCRYPTION), Priority.P0)).isEqualTo(Priority.P0);
    }

    @Test
    void p0IsNotAcceptedForOtherAlgorithmsThatTheTableMapsElsewhere() {
        assertThatThrownBy(() -> policy.accept(usage(AlgorithmFamily.ECDSA, UsageContext.SIGNATURE), Priority.P0))
                .isInstanceOf(FindingRejectedException.class);
        assertThatThrownBy(() -> policy.accept(usage(AlgorithmFamily.SHA3, UsageContext.HASH), Priority.P0))
                .isInstanceOf(FindingRejectedException.class);
    }
}

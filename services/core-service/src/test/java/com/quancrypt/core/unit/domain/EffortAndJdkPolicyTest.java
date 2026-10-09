package com.quancrypt.core.unit.domain;

import com.quancrypt.core.domain.model.Effort;
import com.quancrypt.core.domain.model.JavaVersion;
import com.quancrypt.core.domain.model.RiskClass;
import com.quancrypt.core.domain.model.RiskScore;
import com.quancrypt.core.domain.model.StrategyCode;
import com.quancrypt.core.domain.policy.EffortPolicy;
import com.quancrypt.core.domain.policy.JdkRequirementPolicy;
import com.quancrypt.core.domain.policy.RiskClassPolicy;
import java.math.BigDecimal;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.EnumSource;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class EffortAndJdkPolicyTest {

    private final EffortPolicy effort = new EffortPolicy();
    private final JdkRequirementPolicy jdk = new JdkRequirementPolicy();

    @ParameterizedTest
    @EnumSource(StrategyCode.class)
    void baseEffortComesFromTheStrategyAndFourCallSitesDoNotRaiseIt(StrategyCode code) {
        assertThat(effort.estimate(code, 0)).isEqualTo(code.baseEffort());
        assertThat(effort.estimate(code, 4)).isEqualTo(code.baseEffort());
    }

    @Test
    void theBaseEffortsAreTheOnesTheUserApproved() {
        assertThat(StrategyCode.FIX_WEAK_CLASSIC.baseEffort()).isEqualTo(Effort.S);
        assertThat(StrategyCode.KEEP_SHORT_LIVED_TOKEN.baseEffort()).isEqualTo(Effort.S);
        assertThat(StrategyCode.HYBRID_KEX_CLASSIC_CERT.baseEffort()).isEqualTo(Effort.S);
        assertThat(StrategyCode.HYBRID_TLS_KEX.baseEffort()).isEqualTo(Effort.M);
        assertThat(StrategyCode.JDK_UPGRADE.baseEffort()).isEqualTo(Effort.M);
        assertThat(StrategyCode.KEM_DEM_ENCRYPTION.baseEffort()).isEqualTo(Effort.L);
        assertThat(StrategyCode.DEVICE_HYBRID_TLS.baseEffort()).isEqualTo(Effort.L);
        assertThat(StrategyCode.PQ_SIGNATURE.baseEffort()).isEqualTo(Effort.L);
    }

    @Test
    void fiveOrMoreCallSitesRaiseTheEffortOneGradeAndLargeStaysLarge() {
        assertThat(effort.estimate(StrategyCode.FIX_WEAK_CLASSIC, 5)).isEqualTo(Effort.M);
        assertThat(effort.estimate(StrategyCode.HYBRID_TLS_KEX, 9)).isEqualTo(Effort.L);
        assertThat(effort.estimate(StrategyCode.PQ_SIGNATURE, 50)).isEqualTo(Effort.L);
        assertThat(Effort.S.raised()).isEqualTo(Effort.M);
        assertThat(Effort.M.raised()).isEqualTo(Effort.L);
        assertThat(Effort.L.raised()).isEqualTo(Effort.L);
    }

    @Test
    void onlyKemDemAndPqSignatureNeedJdk24() {
        assertThat(jdk.requiredMajor(StrategyCode.KEM_DEM_ENCRYPTION)).hasValue(24);
        assertThat(jdk.requiredMajor(StrategyCode.PQ_SIGNATURE)).hasValue(24);
        for (StrategyCode code : StrategyCode.values()) {
            if (code != StrategyCode.KEM_DEM_ENCRYPTION && code != StrategyCode.PQ_SIGNATURE) {
                assertThat(jdk.requiredMajor(code)).isEmpty();
            }
        }
    }

    @Test
    void anOldJavaVersionIsUnmetAndAnUnknownOneIsTreatedAsMet() {
        assertThat(jdk.unmet(StrategyCode.KEM_DEM_ENCRYPTION, Optional.of(new JavaVersion(21)))).isPresent();
        assertThat(jdk.unmet(StrategyCode.KEM_DEM_ENCRYPTION, Optional.of(new JavaVersion(24)))).isEmpty();
        assertThat(jdk.unmet(StrategyCode.KEM_DEM_ENCRYPTION, Optional.empty())).isEmpty();
        assertThat(jdk.unmet(StrategyCode.HYBRID_TLS_KEX, Optional.of(new JavaVersion(8)))).isEmpty();
    }

    @Test
    void riskClassesFollowTheThresholdsAtTheirBoundaries() {
        RiskClassPolicy policy = new RiskClassPolicy(Map.of(RiskClass.CRITICAL, new BigDecimal("0.8"), RiskClass.HIGH, new BigDecimal("0.6"),
                RiskClass.MEDIUM, new BigDecimal("0.35"), RiskClass.LOW, BigDecimal.ZERO));
        assertThat(policy.classify(RiskScore.of(1.0))).isEqualTo(RiskClass.CRITICAL);
        assertThat(policy.classify(RiskScore.of(0.8))).isEqualTo(RiskClass.CRITICAL);
        assertThat(policy.classify(RiskScore.of(0.7999))).isEqualTo(RiskClass.HIGH);
        assertThat(policy.classify(RiskScore.of(0.6))).isEqualTo(RiskClass.HIGH);
        assertThat(policy.classify(RiskScore.of(0.35))).isEqualTo(RiskClass.MEDIUM);
        assertThat(policy.classify(RiskScore.of(0.3499))).isEqualTo(RiskClass.LOW);
        assertThat(policy.classify(RiskScore.of(0.0))).isEqualTo(RiskClass.LOW);
    }

    @Test
    void riskThresholdsNeedEveryClassAndLowStartsAtZero() {
        assertThatThrownBy(() -> new RiskClassPolicy(Map.of(RiskClass.LOW, BigDecimal.ZERO))).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new RiskClassPolicy(Map.of(RiskClass.CRITICAL, new BigDecimal("0.8"), RiskClass.HIGH, new BigDecimal("0.6"),
                RiskClass.MEDIUM, new BigDecimal("0.35"), RiskClass.LOW, new BigDecimal("0.1")))).isInstanceOf(IllegalArgumentException.class);
    }
}

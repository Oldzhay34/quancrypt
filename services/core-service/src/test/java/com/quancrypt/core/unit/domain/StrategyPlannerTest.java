package com.quancrypt.core.unit.domain;

import com.quancrypt.core.domain.exception.NoStrategyException;
import com.quancrypt.core.domain.model.AlgorithmFamily;
import com.quancrypt.core.domain.model.CryptoUsage;
import com.quancrypt.core.domain.model.Effort;
import com.quancrypt.core.domain.model.JavaVersion;
import com.quancrypt.core.domain.model.LocationKind;
import com.quancrypt.core.domain.model.Priority;
import com.quancrypt.core.domain.model.StrategyCode;
import com.quancrypt.core.domain.model.UsageContext;
import com.quancrypt.core.domain.policy.EffortPolicy;
import com.quancrypt.core.domain.policy.JdkRequirementPolicy;
import com.quancrypt.core.domain.service.PlannedStrategy;
import com.quancrypt.core.domain.service.StrategyPlanner;
import com.quancrypt.core.domain.service.StrategyRegistry;
import com.quancrypt.core.domain.service.strategy.DeviceHybridTlsStrategy;
import com.quancrypt.core.domain.service.strategy.FindingFacts;
import com.quancrypt.core.domain.service.strategy.FixWeakClassicStrategy;
import com.quancrypt.core.domain.service.strategy.HybridKexClassicCertStrategy;
import com.quancrypt.core.domain.service.strategy.HybridTlsKexStrategy;
import com.quancrypt.core.domain.service.strategy.JdkUpgradeStrategy;
import com.quancrypt.core.domain.service.strategy.KeepShortLivedTokenStrategy;
import com.quancrypt.core.domain.service.strategy.KemDemEncryptionStrategy;
import com.quancrypt.core.domain.service.strategy.PlanNote;
import com.quancrypt.core.domain.service.strategy.PqSignatureStrategy;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class StrategyPlannerTest {

    private final StrategyRegistry registry = new StrategyRegistry(List.of(
            new FixWeakClassicStrategy(), new HybridTlsKexStrategy(), new DeviceHybridTlsStrategy(), new KemDemEncryptionStrategy(),
            new PqSignatureStrategy(), new KeepShortLivedTokenStrategy(), new HybridKexClassicCertStrategy(), new JdkUpgradeStrategy()));
    private final StrategyPlanner planner = new StrategyPlanner(registry, new JdkRequirementPolicy(), new EffortPolicy());

    private static FindingFacts facts(AlgorithmFamily algorithm, UsageContext usage, Priority priority, boolean device, int callSites, Integer java) {
        return new FindingFacts(new CryptoUsage(algorithm, usage, Optional.of(2048), LocationKind.CODE), priority, device, callSites,
                Optional.ofNullable(java).map(JavaVersion::new));
    }

    @Test
    void tlsKeyExchangeBetweenServicesGetsHybridTlsAndNotesThatJdk27ShipsTheHybridGroup() {
        PlannedStrategy planned = planner.plan(facts(AlgorithmFamily.RSA, UsageContext.TLS_KEY_EXCHANGE, Priority.P1, false, 0, 25));
        assertThat(planned.code()).isEqualTo(StrategyCode.HYBRID_TLS_KEX);
        assertThat(planned.effort()).isEqualTo(Effort.M);
        assertThat(planned.notes()).containsExactly(PlanNote.HYBRID_TLS_DEFAULT_ARRIVES_IN_JDK_27, PlanNote.BOUNCY_CASTLE_ALTERNATIVE);
        assertThat(planned.replacedStrategy()).isEmpty();
    }

    @Test
    void jdk27NeedsNoNotes() {
        assertThat(planner.plan(facts(AlgorithmFamily.RSA, UsageContext.TLS_KEY_EXCHANGE, Priority.P1, false, 0, 27)).notes()).isEmpty();
    }

    @Test
    void aDeviceLinkGetsDeviceHybridTlsEvenOnAnOldJdk() {
        PlannedStrategy planned = planner.plan(facts(AlgorithmFamily.RSA, UsageContext.TLS_KEY_EXCHANGE, Priority.P1, true, 0, 8));
        assertThat(planned.code()).isEqualTo(StrategyCode.DEVICE_HYBRID_TLS);
        assertThat(planned.effort()).isEqualTo(Effort.L);
    }

    @Test
    void kemDemOnJdk25StaysKemDem() {
        PlannedStrategy planned = planner.plan(facts(AlgorithmFamily.RSA, UsageContext.ENCRYPTION, Priority.P1, false, 0, 25));
        assertThat(planned.code()).isEqualTo(StrategyCode.KEM_DEM_ENCRYPTION);
        assertThat(planned.requiredJavaMajor()).isEmpty();
    }

    @Test
    void kemDemOnJdk17BecomesAJdkUpgradeThatRemembersWhatItReplaced() {
        PlannedStrategy planned = planner.plan(facts(AlgorithmFamily.RSA, UsageContext.ENCRYPTION, Priority.P1, false, 0, 17));
        assertThat(planned.code()).isEqualTo(StrategyCode.JDK_UPGRADE);
        assertThat(planned.effort()).isEqualTo(Effort.M);
        assertThat(planned.replacedStrategy()).hasValue(StrategyCode.KEM_DEM_ENCRYPTION);
        assertThat(planned.requiredJavaMajor()).hasValue(24);
        assertThat(planned.notes()).contains(PlanNote.BOUNCY_CASTLE_ALTERNATIVE);
    }

    @Test
    void pqSignatureOnJdk21BecomesAJdkUpgrade() {
        PlannedStrategy planned = planner.plan(facts(AlgorithmFamily.ECDSA, UsageContext.SIGNATURE, Priority.P2, false, 0, 21));
        assertThat(planned.code()).isEqualTo(StrategyCode.JDK_UPGRADE);
        assertThat(planned.replacedStrategy()).hasValue(StrategyCode.PQ_SIGNATURE);
    }

    @Test
    void anUnknownJavaVersionKeepsTheStrategyAndLeavesANote() {
        PlannedStrategy planned = planner.plan(facts(AlgorithmFamily.RSA, UsageContext.ENCRYPTION, Priority.P1, false, 0, null));
        assertThat(planned.code()).isEqualTo(StrategyCode.KEM_DEM_ENCRYPTION);
        assertThat(planned.notes()).contains(PlanNote.JAVA_VERSION_UNKNOWN);
    }

    @Test
    void fiveCallSitesRaiseTheEffort() {
        assertThat(planner.plan(facts(AlgorithmFamily.SHA1, UsageContext.SIGNATURE, Priority.P0, false, 5, 25)).effort()).isEqualTo(Effort.M);
        assertThat(planner.plan(facts(AlgorithmFamily.SHA1, UsageContext.SIGNATURE, Priority.P0, false, 4, 25)).effort()).isEqualTo(Effort.S);
    }

    @Test
    void everyStrategyHasOneFindingKindItSupports() {
        assertThat(planner.plan(facts(AlgorithmFamily.DES, UsageContext.ENCRYPTION, Priority.P0, false, 0, 25)).code()).isEqualTo(StrategyCode.FIX_WEAK_CLASSIC);
        assertThat(planner.plan(facts(AlgorithmFamily.RSA, UsageContext.TOKEN_SIGNATURE, Priority.P3, false, 0, 25)).code()).isEqualTo(StrategyCode.KEEP_SHORT_LIVED_TOKEN);
        assertThat(planner.plan(facts(AlgorithmFamily.RSA, UsageContext.MTLS_CLIENT_AUTH, Priority.P3, false, 0, 25)).code()).isEqualTo(StrategyCode.HYBRID_KEX_CLASSIC_CERT);
        assertThat(planner.plan(facts(AlgorithmFamily.ECDSA, UsageContext.SIGNATURE, Priority.P2, false, 0, 25)).code()).isEqualTo(StrategyCode.PQ_SIGNATURE);
    }

    @Test
    void aKeystoreAssetGetsTheNoteThatItsContentWasNotInspected() {
        FindingFacts keystore = new FindingFacts(
                new CryptoUsage(AlgorithmFamily.UNKNOWN, UsageContext.KEYSTORE, Optional.empty(), LocationKind.KEYSTORE_FILE), Priority.P3, false, 0,
                Optional.of(new JavaVersion(25)));
        PlannedStrategy planned = planner.plan(keystore);
        assertThat(planned.code()).isEqualTo(StrategyCode.HYBRID_KEX_CLASSIC_CERT);
        assertThat(planned.notes()).containsExactly(PlanNote.KEYSTORE_CONTENT_NOT_INSPECTED);
    }

    @Test
    void aTokenKeyKeptInAKeystoreIsAKeystoreAssetAndNotAShortLivedTokenAsD151cSays() {
        FindingFacts tokenInKeystore = new FindingFacts(
                new CryptoUsage(AlgorithmFamily.RSA, UsageContext.TOKEN_SIGNATURE, Optional.of(2048), LocationKind.KEYSTORE_FILE), Priority.P3, false, 0,
                Optional.of(new JavaVersion(25)));
        PlannedStrategy planned = planner.plan(tokenInKeystore);
        assertThat(planned.code()).isEqualTo(StrategyCode.HYBRID_KEX_CLASSIC_CERT);
        assertThat(planned.notes()).containsExactly(PlanNote.KEYSTORE_CONTENT_NOT_INSPECTED);
    }

    @Test
    void aFindingNoStrategySupportsIsAnError() {
        assertThatThrownBy(() -> planner.plan(facts(AlgorithmFamily.UNKNOWN, UsageContext.UNKNOWN, Priority.P2, false, 0, 25)))
                .isInstanceOf(NoStrategyException.class);
    }

    @Test
    void severalSupportingStrategiesAreAConfigurationError() {
        StrategyRegistry doubled = new StrategyRegistry(List.of(new FixWeakClassicStrategy(), new FixWeakClassicStrategy()));
        assertThatThrownBy(() -> doubled.select(facts(AlgorithmFamily.DES, UsageContext.ENCRYPTION, Priority.P0, false, 0, 25)))
                .isInstanceOf(NoStrategyException.class).hasMessageContaining("several");
        assertThat(registry.isRegistered(StrategyCode.JDK_UPGRADE)).isTrue();
        assertThat(doubled.isRegistered(StrategyCode.PQ_SIGNATURE)).isFalse();
    }
}

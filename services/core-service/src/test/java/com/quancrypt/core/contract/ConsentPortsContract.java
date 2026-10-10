package com.quancrypt.core.contract;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.quancrypt.core.domain.exception.ConcurrentModificationException;
import com.quancrypt.core.domain.exception.DuplicateConsentException;
import com.quancrypt.core.domain.model.Consent;
import com.quancrypt.core.domain.model.ConsentType;
import com.quancrypt.core.domain.model.PrivacyNotice;
import com.quancrypt.core.domain.model.Project;
import org.junit.jupiter.api.Test;

/** ConsentReader, ConsentWriter, ConsentLock and PrivacyNoticeReader. */
public abstract class ConsentPortsContract extends PortContract {

    private PrivacyNotice notice() {
        return ports.privacyNotices().latest().orElseThrow();
    }

    @Test
    void latestPrivacyNoticeIsVersionOne() {
        assertThat(notice().version()).isEqualTo(1);
    }

    @Test
    void insertedConsentIsReadBackWithItsNoticeVersion() {
        Project project = project("Demo", T0);
        Consent consent = Consent.firstGrant(ids.next(), project.id(), ConsentType.WAREHOUSE_ANALYTICS, notice(), at(1));

        ports.consentWriter().insert(consent);

        assertThat(ports.consentReader().find(project.id(), ConsentType.WAREHOUSE_ANALYTICS)).contains(consent);
        assertThat(ports.consentReader().find(project.id(), ConsentType.MODEL_TRAINING)).isEmpty();
        assertThat(ports.consentReader().list(project.id())).containsExactly(consent);
        assertThat(ports.consentLock().share(project.id(), ConsentType.WAREHOUSE_ANALYTICS)).contains(consent);
        assertThat(ports.consentLock().updateAll(project.id())).containsExactly(consent);
    }

    @Test
    void secondConsentOfTheSameTypeIsADuplicate() {
        Project project = project("Demo", T0);
        ports.consentWriter().insert(Consent.firstGrant(ids.next(), project.id(), ConsentType.MODEL_TRAINING, notice(), at(1)));

        assertThatThrownBy(() -> ports.consentWriter().insert(
                Consent.firstGrant(ids.next(), project.id(), ConsentType.MODEL_TRAINING, notice(), at(2))))
                .isInstanceOf(DuplicateConsentException.class);
    }

    @Test
    void updateNeedsTheStoredVersion() {
        Project project = project("Demo", T0);
        Consent granted = Consent.firstGrant(ids.next(), project.id(), ConsentType.WAREHOUSE_ANALYTICS, notice(), at(1));
        ports.consentWriter().insert(granted);
        Consent revoked = granted.revoke(at(2));

        ports.consentWriter().update(revoked, granted.version());

        assertThat(ports.consentReader().find(project.id(), ConsentType.WAREHOUSE_ANALYTICS)).contains(revoked);
        assertThatThrownBy(() -> ports.consentWriter().update(revoked.regrant(notice(), at(3)), granted.version()))
                .isInstanceOf(ConcurrentModificationException.class);
    }
}

package com.quancrypt.core.contract;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.core.domain.event.DomainEvent;
import com.quancrypt.core.port.outbound.EventAnonymizer;
import com.quancrypt.core.port.outbound.ProjectKeyHasher;
import org.junit.jupiter.api.Test;

/**
 * ProjectKeyHasher and EventAnonymizer contract shared by the fakes and HmacEventAnonymizer: the project key is a
 * deterministic 64-hex digest that differs per identity, and coded event payloads (every payload the domain produces)
 * come out unchanged. Redaction of free text and the salt are adapter-specific (HmacEventAnonymizerTest,
 * RedactorVectorsTest); the fakes neither redact nor salt, which the unit tests do not need.
 */
public abstract class AnonymizationContract {

    protected abstract ProjectKeyHasher hasher();

    protected abstract EventAnonymizer anonymizer();

    @Test
    void projectKeysAreDeterministicAndDifferPerIdentity() {
        ProjectKeyHasher hasher = hasher();

        assertThat(hasher.hash("/work/demo")).isEqualTo(hasher.hash("/work/demo"));
        assertThat(hasher.hash("/work/demo")).isNotEqualTo(hasher.hash("/work/other"));
        assertThat(hasher.hash("git@example.com:bank/payments.git").value()).matches("[0-9a-f]{64}");
    }

    @Test
    void codedPayloadsComeOutUnchanged() {
        for (DomainEvent event : SampleEvents.all()) {
            assertThat(anonymizer().anonymize(event)).as(event.toString()).isEqualTo(event.payload());
        }
    }
}

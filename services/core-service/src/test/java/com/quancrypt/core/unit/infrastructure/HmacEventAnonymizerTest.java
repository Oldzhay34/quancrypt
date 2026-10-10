package com.quancrypt.core.unit.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.quancrypt.core.domain.event.ProjectRuntimeChanged;
import com.quancrypt.core.domain.event.TopologyRecorded;
import com.quancrypt.core.domain.model.Protocol;
import com.quancrypt.core.infrastructure.anonymization.HmacEventAnonymizer;
import com.quancrypt.core.infrastructure.anonymization.RedactionRules;
import com.quancrypt.core.infrastructure.anonymization.Redactor;
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.junit.jupiter.api.Test;

/** HmacEventAnonymizer: salt checks, HMAC-SHA256 project keys and redaction of every string in a payload. */
class HmacEventAnonymizerTest {

    private static final String SALT = "0123456789abcdef0123456789abcdef0123456789abcdef";
    private final Redactor redactor = new Redactor(RedactionRules.fromClasspath());

    @Test
    void weakOrPlaceholderSaltsStopTheService() {
        for (String salt : new String[] {null, "", "   ", "CHANGE_ME", "short-salt", "CHANGE_ME-" + SALT}) {
            assertThatThrownBy(() -> new HmacEventAnonymizer(salt, redactor)).isInstanceOf(IllegalStateException.class)
                    .hasMessageNotContaining(SALT);
        }
    }

    @Test
    void projectKeyIsHmacSha256OfTheIdentityUnderTheSalt() throws Exception {
        HmacEventAnonymizer anonymizer = new HmacEventAnonymizer(SALT, redactor);
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(SALT.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
        String expected = HexFormat.of().formatHex(mac.doFinal("/work/demo".getBytes(StandardCharsets.UTF_8)));

        assertThat(anonymizer.hash("/work/demo").value()).isEqualTo(expected);
        assertThat(new HmacEventAnonymizer(SALT + "x", redactor).hash("/work/demo").value()).isNotEqualTo(expected);
    }

    @Test
    void everyStringIsRedactedAndOtherValuesStay() {
        HmacEventAnonymizer anonymizer = new HmacEventAnonymizer(SALT, redactor);
        ProjectRuntimeChanged leaky = new ProjectRuntimeChanged(Optional.empty(),
                new ProjectRuntimeChanged.Snapshot("password=hunter2-demo", Optional.of("demo.user@example.com")));

        Map<String, Object> payload = anonymizer.anonymize(leaky);

        assertThat(payload).containsEntry("previous", null);
        @SuppressWarnings("unchecked")
        Map<String, Object> current = (Map<String, Object>) payload.get("current");
        assertThat(current).containsEntry("java_version", "password=[REDACTED:secret_assignment]")
                .containsEntry("spring_boot_version", "[REDACTED:email]");
        Map<String, Object> topology = anonymizer.anonymize(new TopologyRecorded(2, 1, List.of(new TopologyRecorded.LinkSummary(Protocol.HTTP, true, false))));
        assertThat(topology).isEqualTo(new TopologyRecorded(2, 1, List.of(new TopologyRecorded.LinkSummary(Protocol.HTTP, true, false))).payload());
    }
}

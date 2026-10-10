package com.quancrypt.core.contract;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.core.domain.model.ClarificationAnswer;
import com.quancrypt.core.domain.model.ClarificationQuestion;
import com.quancrypt.core.domain.model.Project;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.Test;

/** ClarificationReader and ClarificationWriter. */
public abstract class ClarificationPortsContract extends PortContract {

    @Test
    void answersAreUpsertedAndListedInQuestionOrder() {
        Project project = project("Demo", T0);
        ClarificationAnswer device = new ClarificationAnswer(ClarificationQuestion.DEVICE_HARDWARE_OPENSSL, Optional.empty(),
                Optional.of("PYNQ-Z2, OpenSSL 3.0"), at(1));
        ClarificationAnswer tls = new ClarificationAnswer(ClarificationQuestion.TLS_TERMINATION, Optional.of("INGRESS"), Optional.empty(), at(1));
        ports.clarificationWriter().upsertAll(project.id(), List.of(device, tls));
        ClarificationAnswer tlsChanged = new ClarificationAnswer(ClarificationQuestion.TLS_TERMINATION, Optional.of("APPLICATION"),
                Optional.empty(), at(2));
        ClarificationAnswer compliance = new ClarificationAnswer(ClarificationQuestion.COMPLIANCE_REQUIREMENT, Optional.of("YES"),
                Optional.of("BDDK"), at(2));

        ports.clarificationWriter().upsertAll(project.id(), List.of(tlsChanged, compliance));

        assertThat(ports.clarificationReader().list(project.id())).containsExactly(tlsChanged, compliance, device);
    }
}

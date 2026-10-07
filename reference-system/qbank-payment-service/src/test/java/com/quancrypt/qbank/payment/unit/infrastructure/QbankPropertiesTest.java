package com.quancrypt.qbank.payment.unit.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.quancrypt.qbank.payment.infrastructure.config.QbankProperties;
import org.junit.jupiter.api.Test;

/** The service refuses to start with a plain-text URL for the account service or the broker. */
class QbankPropertiesTest {

    private static final QbankProperties.AccountClient TIMEOUTS = new QbankProperties.AccountClient(2000, 3000);
    private static final QbankProperties.Mqtt MQTT =
            new QbankProperties.Mqtt("ssl://mosquitto:8883", "client", "terminal/+/transactions", 1, 10);

    @Test
    void secureUrlsAreAccepted() {
        QbankProperties properties = new QbankProperties("certs", "https://account:9444", TIMEOUTS, MQTT);

        assertThat(properties.accountServiceUrl()).isEqualTo("https://account:9444");
    }

    @Test
    void aPlainHttpAccountServiceUrlIsRefused() {
        assertThatThrownBy(() -> new QbankProperties("certs", "http://account:9444", TIMEOUTS, MQTT))
                .isInstanceOf(IllegalArgumentException.class).hasMessageContaining("https://");
        assertThatThrownBy(() -> new QbankProperties("certs", null, TIMEOUTS, MQTT))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void aBrokerUrlWithoutTlsIsRefused() {
        assertThatThrownBy(() -> new QbankProperties.Mqtt("tcp://mosquitto:1883", "client", "t", 1, 10))
                .isInstanceOf(IllegalArgumentException.class).hasMessageContaining("ssl://");
        assertThatThrownBy(() -> new QbankProperties.Mqtt(null, "client", "t", 1, 10))
                .isInstanceOf(IllegalArgumentException.class);
    }
}

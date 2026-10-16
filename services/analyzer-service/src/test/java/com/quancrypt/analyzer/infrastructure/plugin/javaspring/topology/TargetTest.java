package com.quancrypt.analyzer.infrastructure.plugin.javaspring.topology;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.analyzer.domain.model.Protocol;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

/** Where a connection goes, read from the text of a URL or an address (the topology {@link Target}). */
class TargetTest {

    @Test
    void aUrlGivesHostPortAndSchemeAndDropsUserInformation() {
        Target target = Target.ofUrl("https://user:secret@Pay.Example.com:8443/v1?x=1").orElseThrow();

        assertThat(target.host()).isEqualTo("pay.example.com");
        assertThat(target.port()).isEqualTo(8443);
        assertThat(target.scheme()).isEqualTo("https");
        assertThat(target.toString()).doesNotContain("secret");
    }

    @Test
    void theSchemeDecidesTheProtocolAndWhetherItIsSecure() {
        assertThat(Target.ofUrl("ssl://broker:8883").orElseThrow().protocol()).isEqualTo(Optional.of(Protocol.MQTT));
        assertThat(Target.ofUrl("ssl://broker:8883").orElseThrow().secureScheme()).isTrue();
        assertThat(Target.ofUrl("tcp://broker:1883").orElseThrow().secureScheme()).isFalse();
        assertThat(Target.ofUrl("amqps://mq").orElseThrow().protocol()).isEqualTo(Optional.of(Protocol.AMQP));
        assertThat(Target.ofUrl("grpc://svc:50051").orElseThrow().protocol()).isEqualTo(Optional.of(Protocol.GRPC));
        assertThat(Target.ofUrl("http://svc").orElseThrow().port()).isEqualTo(-1);
    }

    @Test
    void aJdbcUrlIsADatabaseAddress() {
        Target target = Target.ofUrl("jdbc:postgresql://db:5432/app").orElseThrow();

        assertThat(target.host()).isEqualTo("db");
        assertThat(target.port()).isEqualTo(5432);
        assertThat(target.scheme()).isEqualTo("jdbc");
    }

    @Test
    void hostAndPortAndPlainNamesAreAddressesToo() {
        assertThat(Target.ofHostPort("kafka-1:9092").orElseThrow().port()).isEqualTo(9092);
        assertThat(Target.ofName("Inventory").orElseThrow().host()).isEqualTo("inventory");
        assertThat(Target.ofHostPort("not an address")).isEmpty();
    }

    @ParameterizedTest
    @ValueSource(strings = {"", "file:///certs/x.pem", "classpath:/x", "just text", "mailto:a@b.c", "://x", "http://", "plain"})
    void textThatIsNotAConnectionIsNotATarget(String text) {
        assertThat(Target.ofUrl(text).filter(t -> t.protocol().isPresent())).isEmpty();
    }

    @Test
    void aLocalAddressIsRecognised() {
        assertThat(Target.ofUrl("https://localhost:9444").orElseThrow().local()).isTrue();
        assertThat(Target.ofUrl("https://127.0.0.1:9444").orElseThrow().local()).isTrue();
        assertThat(Target.ofUrl("https://svc:9444").orElseThrow().local()).isFalse();
    }

    @Test
    void aPasswordWithAnUnescapedAtSignNeverReachesTheHost() {
        assertThat(Target.ofUrl("https://admin:P@ssw0rd@db.internal/x").orElseThrow().host()).isEqualTo("db.internal");
        assertThat(Target.ofUrl("amqps://ruser:Rp@ssw0rd@rabbit.internal:5671").orElseThrow().host()).isEqualTo("rabbit.internal");
        assertThat(Target.ofUrl("jdbc:postgresql://u:p@ss@db:5432/app").orElseThrow().host()).isEqualTo("db");
        assertThat(Target.ofHostPort("u:p@ss@kafka:9092").orElseThrow().host()).isEqualTo("kafka");
        assertThat(Target.ofUrl("https://host@evil@/x")).as("no host is left once the user information is taken off").isEmpty();
    }

    @Test
    void aTextAboveTheLimitIsNotATarget() {
        assertThat(Target.ofUrl("https://" + "a".repeat(3000))).isEmpty();
        assertThat(Target.ofHostPort("a".repeat(3000) + ":80")).isEmpty();
    }

    @Test
    void anOutOfRangePortIsDroppedNotParsedIntoNonsense() {
        assertThat(Target.ofUrl("https://host:99999").map(Target::port)).isEqualTo(Optional.of(-1));
    }

    @Test
    void aLongAdversarialHostIsAnsweredQuickly() {
        String text = "https://" + "a".repeat(5000) + ":" + "9".repeat(5000);

        long start = System.nanoTime();
        Target.ofUrl(text);
        assertThat((System.nanoTime() - start) / 1_000_000).isLessThan(1000);
    }
}

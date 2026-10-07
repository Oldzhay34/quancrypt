package com.quancrypt.qbank.payment.contract;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.qbank.payment.domain.model.AccountId;
import com.quancrypt.qbank.payment.domain.model.CardToken;
import com.quancrypt.qbank.payment.domain.model.Payment;
import com.quancrypt.qbank.payment.domain.model.TerminalTransaction;
import com.quancrypt.qbank.payment.infrastructure.persistence.InMemoryPaymentRepository;
import com.quancrypt.qbank.payment.infrastructure.persistence.InMemoryTerminalTransactionRepository;
import com.quancrypt.qbank.payment.port.outbound.PaymentRepository;
import com.quancrypt.qbank.payment.port.outbound.TerminalTransactionRepository;
import com.quancrypt.qbank.payment.support.Fakes.FakePaymentRepository;
import com.quancrypt.qbank.payment.support.Fakes.FakeTerminalTransactionRepository;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.Test;

/** Contract of PaymentRepository: every implementation must pass (Liskov substitution). */
abstract class PaymentRepositoryContractTest {

    private static final Instant NOW = Instant.parse("2026-10-07T10:00:00Z");

    abstract PaymentRepository create();

    private static Payment payment(long id, String amount) {
        return new Payment(new UUID(0, id), new AccountId("acc-001"), new BigDecimal(amount), "TRY", new CardToken("t"), NOW);
    }

    @Test
    void findsASavedPaymentById() {
        PaymentRepository repository = create();
        repository.save(payment(1, "1.00"));

        assertThat(repository.findById(new UUID(0, 1))).contains(payment(1, "1.00"));
    }

    @Test
    void returnsEmptyForAnUnknownId() {
        assertThat(create().findById(new UUID(0, 9))).isEmpty();
    }

    @Test
    void savingAgainWithTheSameIdReplacesThePayment() {
        PaymentRepository repository = create();
        repository.save(payment(1, "1.00"));
        repository.save(payment(1, "2.00"));

        assertThat(repository.findById(new UUID(0, 1)).orElseThrow().amount().toPlainString()).isEqualTo("2.00");
    }
}

class FakePaymentRepositoryContractTest extends PaymentRepositoryContractTest {

    @Override
    PaymentRepository create() {
        return new FakePaymentRepository();
    }
}

class InMemoryPaymentRepositoryContractTest extends PaymentRepositoryContractTest {

    @Override
    PaymentRepository create() {
        return new InMemoryPaymentRepository();
    }
}

/** Contract of TerminalTransactionRepository. */
abstract class TerminalTransactionRepositoryContractTest {

    private static final Instant NOW = Instant.parse("2026-10-07T10:00:00Z");

    abstract TerminalTransactionRepository create();

    private static TerminalTransaction transaction(long id, String amount) {
        return new TerminalTransaction(new UUID(0, id), "terminal-001", new AccountId("acc-001"), new BigDecimal(amount), "TRY", NOW);
    }

    @Test
    void storesAnUnknownTransaction() {
        TerminalTransactionRepository repository = create();

        assertThat(repository.saveIfAbsent(transaction(1, "5.00"))).isTrue();
        assertThat(repository.findById(new UUID(0, 1))).contains(transaction(1, "5.00"));
    }

    @Test
    void doesNotReplaceAnExistingTransactionId() {
        TerminalTransactionRepository repository = create();
        repository.saveIfAbsent(transaction(1, "5.00"));

        assertThat(repository.saveIfAbsent(transaction(1, "99.00"))).isFalse();
        assertThat(repository.findById(new UUID(0, 1)).orElseThrow().amount().toPlainString()).isEqualTo("5.00");
    }

    @Test
    void returnsEmptyForAnUnknownId() {
        assertThat(create().findById(new UUID(0, 9))).isEmpty();
    }
}

class FakeTerminalTransactionRepositoryContractTest extends TerminalTransactionRepositoryContractTest {

    @Override
    TerminalTransactionRepository create() {
        return new FakeTerminalTransactionRepository();
    }
}

class InMemoryTerminalTransactionRepositoryContractTest extends TerminalTransactionRepositoryContractTest {

    @Override
    TerminalTransactionRepository create() {
        return new InMemoryTerminalTransactionRepository();
    }
}

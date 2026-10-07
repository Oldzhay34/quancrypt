package com.quancrypt.qbank.payment.contract;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.qbank.payment.domain.model.AccountId;
import com.quancrypt.qbank.payment.domain.model.CardToken;
import com.quancrypt.qbank.payment.domain.model.IssuedReceipt;
import com.quancrypt.qbank.payment.domain.model.Payment;
import com.quancrypt.qbank.payment.domain.model.Receipt;
import com.quancrypt.qbank.payment.domain.model.ReceiptSignature;
import com.quancrypt.qbank.payment.infrastructure.persistence.InMemoryIdempotencyStore;
import com.quancrypt.qbank.payment.port.outbound.IdempotencyStore;
import com.quancrypt.qbank.payment.port.outbound.IdempotencyStore.Lookup;
import com.quancrypt.qbank.payment.support.Fakes.FakeIdempotencyStore;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.Test;

/** Contract of IdempotencyStore: every implementation must pass (Liskov substitution). */
abstract class IdempotencyStoreContractTest {

    private static final Instant NOW = Instant.parse("2026-10-07T10:00:00Z");
    private static final Payment PAYMENT = new Payment(
            new UUID(0, 1), new AccountId("acc-001"), new BigDecimal("1.00"), "TRY", new CardToken("t"), NOW);
    private static final IssuedReceipt RECEIPT = new IssuedReceipt(
            new Receipt(new UUID(0, 1), new AccountId("acc-001"), new BigDecimal("1.00"), "TRY", NOW),
            new ReceiptSignature("SHA1withRSA", "kid", "sig"));

    abstract IdempotencyStore create();

    @Test
    void anUnknownScopeIsAbsent() {
        assertThat(create().findPayment("demo1|payment.create|k", "request")).isInstanceOf(Lookup.Absent.class);
        assertThat(create().findReceipt("demo1|receipt.issue|k", "request")).isInstanceOf(Lookup.Absent.class);
    }

    @Test
    void theSameScopeAndDescriptionReplaysThePayment() {
        IdempotencyStore store = create();
        store.savePayment("s", "request", PAYMENT);

        assertThat(store.findPayment("s", "request")).isEqualTo(new Lookup.Replay<>(PAYMENT));
    }

    @Test
    void theSameScopeWithAnotherDescriptionIsAConflict() {
        IdempotencyStore store = create();
        store.savePayment("s", "request", PAYMENT);

        assertThat(store.findPayment("s", "another request")).isInstanceOf(Lookup.Conflict.class);
    }

    @Test
    void anotherScopeIsIndependent() {
        IdempotencyStore store = create();
        store.savePayment("s1", "request", PAYMENT);

        assertThat(store.findPayment("s2", "request")).isInstanceOf(Lookup.Absent.class);
    }

    @Test
    void theFirstOutcomeOfAScopeIsKept() {
        IdempotencyStore store = create();
        Payment other = new Payment(
                new UUID(0, 2), new AccountId("acc-001"), BigDecimal.TEN, "TRY", new CardToken("t"), NOW);
        store.savePayment("s", "request", PAYMENT);
        store.savePayment("s", "request", other);

        assertThat(store.findPayment("s", "request")).isEqualTo(new Lookup.Replay<>(PAYMENT));
    }

    @Test
    void receiptsReplayLikePayments() {
        IdempotencyStore store = create();
        store.saveReceipt("s", "payment-1", RECEIPT);

        assertThat(store.findReceipt("s", "payment-1")).isEqualTo(new Lookup.Replay<>(RECEIPT));
        assertThat(store.findReceipt("s", "payment-2")).isInstanceOf(Lookup.Conflict.class);
    }

    @Test
    void aScopeUsedForAPaymentIsAConflictWhenLookedUpAsAReceipt() {
        IdempotencyStore store = create();
        store.savePayment("s", "request", PAYMENT);

        assertThat(store.findReceipt("s", "request")).isInstanceOf(Lookup.Conflict.class);
    }
}

class FakeIdempotencyStoreContractTest extends IdempotencyStoreContractTest {

    @Override
    IdempotencyStore create() {
        return new FakeIdempotencyStore();
    }
}

class InMemoryIdempotencyStoreContractTest extends IdempotencyStoreContractTest {

    @Override
    IdempotencyStore create() {
        return new InMemoryIdempotencyStore();
    }
}

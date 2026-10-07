package com.quancrypt.qbank.payment.support;

import com.quancrypt.qbank.payment.domain.model.AccountId;
import com.quancrypt.qbank.payment.domain.model.AccountSummary;
import com.quancrypt.qbank.payment.domain.model.Caller;
import com.quancrypt.qbank.payment.domain.model.CardToken;
import com.quancrypt.qbank.payment.domain.model.IssuedReceipt;
import com.quancrypt.qbank.payment.domain.model.Payment;
import com.quancrypt.qbank.payment.domain.model.ReceiptSignature;
import com.quancrypt.qbank.payment.domain.model.TerminalTransaction;
import com.quancrypt.qbank.payment.port.outbound.AccountDirectory;
import com.quancrypt.qbank.payment.port.outbound.AccountLookupException;
import com.quancrypt.qbank.payment.port.outbound.CardTokenizer;
import com.quancrypt.qbank.payment.port.outbound.Clock;
import com.quancrypt.qbank.payment.port.outbound.IdGenerator;
import com.quancrypt.qbank.payment.port.outbound.IdempotencyStore;
import com.quancrypt.qbank.payment.port.outbound.PaymentRepository;
import com.quancrypt.qbank.payment.port.outbound.ReceiptSigner;
import com.quancrypt.qbank.payment.port.outbound.TerminalTransactionRepository;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;

/** Test doubles for the outbound ports. */
public final class Fakes {

    private Fakes() {
    }

    /** Programmable account directory: accounts it knows, failures it raises, and every call it received. */
    public static final class FakeAccountDirectory implements AccountDirectory {

        /** One received call. */
        public record Call(AccountId accountId, Caller caller) {
        }

        private final Map<String, AccountLookupException.Reason> failures = new HashMap<>();
        private final List<Call> calls = new ArrayList<>();

        public FakeAccountDirectory failFor(String accountId, AccountLookupException.Reason reason) {
            failures.put(accountId, reason);
            return this;
        }

        public List<Call> calls() {
            return List.copyOf(calls);
        }

        @Override
        public AccountSummary findAccount(AccountId accountId, Caller caller) {
            calls.add(new Call(accountId, caller));
            AccountLookupException.Reason reason = failures.get(accountId.value());
            if (reason != null) {
                throw new AccountLookupException(reason);
            }
            return new AccountSummary(accountId, "TRY");
        }
    }

    /** Test double: the token is a reversible text, never used with real keys. */
    public static final class FakeCardTokenizer implements CardTokenizer {

        @Override
        public CardToken tokenize(String cardNumber) {
            if (cardNumber == null || cardNumber.isBlank()) {
                throw new IllegalArgumentException("card number must not be blank");
            }
            return new CardToken("fake-token:" + new StringBuilder(cardNumber).reverse());
        }
    }

    /** Test double: the signature is the signing input with a prefix; it records what was signed. */
    public static final class FakeReceiptSigner implements ReceiptSigner {

        private final List<String> signed = new ArrayList<>();

        public List<String> signed() {
            return List.copyOf(signed);
        }

        @Override
        public ReceiptSignature sign(String signingInput) {
            if (signingInput == null || signingInput.isBlank()) {
                throw new IllegalArgumentException("the text to sign must not be blank");
            }
            signed.add(signingInput);
            return new ReceiptSignature("SHA1withRSA", "fake-key-id", "sig:" + signingInput.hashCode());
        }
    }

    /** Test double: always the same instant. */
    public static final class FixedClock implements Clock {

        private final Instant instant;

        public FixedClock(Instant instant) {
            this.instant = instant;
        }

        @Override
        public Instant now() {
            return instant;
        }
    }

    /** Test double: ids 00000000-0000-0000-0000-000000000001, ...002 and so on. */
    public static final class SequentialIdGenerator implements IdGenerator {

        private long next = 1;

        @Override
        public UUID newId() {
            return new UUID(0, next++);
        }
    }

    /** Test double backed by a map. */
    public static final class FakePaymentRepository implements PaymentRepository {

        private final Map<UUID, Payment> payments = new HashMap<>();

        @Override
        public void save(Payment payment) {
            payments.put(payment.paymentId(), payment);
        }

        @Override
        public Optional<Payment> findById(UUID paymentId) {
            return Optional.ofNullable(payments.get(paymentId));
        }

        public int size() {
            return payments.size();
        }
    }

    /** Test double backed by a map. */
    public static final class FakeTerminalTransactionRepository implements TerminalTransactionRepository {

        private final Map<UUID, TerminalTransaction> transactions = new HashMap<>();

        @Override
        public boolean saveIfAbsent(TerminalTransaction transaction) {
            return transactions.putIfAbsent(transaction.transactionId(), transaction) == null;
        }

        @Override
        public Optional<TerminalTransaction> findById(UUID transactionId) {
            return Optional.ofNullable(transactions.get(transactionId));
        }
    }

    /** Test double that keeps descriptions in clear text (acceptable in a test, forbidden in the real adapter). */
    public static final class FakeIdempotencyStore implements IdempotencyStore {

        private record Entry(String description, Object outcome) {
        }

        private final Map<String, Entry> entries = new HashMap<>();

        @Override
        public Lookup<Payment> findPayment(String scope, String requestDescription) {
            return lookup(scope, requestDescription, Payment.class);
        }

        @Override
        public void savePayment(String scope, String requestDescription, Payment payment) {
            entries.putIfAbsent(scope, new Entry(requestDescription, payment));
        }

        @Override
        public Lookup<IssuedReceipt> findReceipt(String scope, String requestDescription) {
            return lookup(scope, requestDescription, IssuedReceipt.class);
        }

        @Override
        public void saveReceipt(String scope, String requestDescription, IssuedReceipt receipt) {
            entries.putIfAbsent(scope, new Entry(requestDescription, receipt));
        }

        private <T> Lookup<T> lookup(String scope, String requestDescription, Class<T> type) {
            Entry entry = entries.get(scope);
            if (entry == null) {
                return new Lookup.Absent<>();
            }
            if (!entry.description().equals(requestDescription) || !type.isInstance(entry.outcome())) {
                return new Lookup.Conflict<>();
            }
            return new Lookup.Replay<>(type.cast(entry.outcome()));
        }
    }
}

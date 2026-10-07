package com.quancrypt.qbank.payment.infrastructure.persistence;

import com.quancrypt.qbank.payment.domain.model.IssuedReceipt;
import com.quancrypt.qbank.payment.domain.model.Payment;
import com.quancrypt.qbank.payment.infrastructure.crypto.RequestFingerprint;
import com.quancrypt.qbank.payment.port.outbound.IdempotencyStore;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Keeps idempotent outcomes in memory. Request descriptions are reduced to a SHA-256 fingerprint before they are
 * stored, so a card number inside a description is never retained. Concurrent first requests with the same key are
 * not serialized (QBank demo).
 */
public final class InMemoryIdempotencyStore implements IdempotencyStore {

    private record Entry(String fingerprint, Object outcome) {
    }

    private final Map<String, Entry> entries = new ConcurrentHashMap<>();

    @Override
    public Lookup<Payment> findPayment(String scope, String requestDescription) {
        return lookup(scope, requestDescription, Payment.class);
    }

    @Override
    public void savePayment(String scope, String requestDescription, Payment payment) {
        entries.putIfAbsent(scope, new Entry(RequestFingerprint.of(requestDescription), payment));
    }

    @Override
    public Lookup<IssuedReceipt> findReceipt(String scope, String requestDescription) {
        return lookup(scope, requestDescription, IssuedReceipt.class);
    }

    @Override
    public void saveReceipt(String scope, String requestDescription, IssuedReceipt receipt) {
        entries.putIfAbsent(scope, new Entry(RequestFingerprint.of(requestDescription), receipt));
    }

    private <T> Lookup<T> lookup(String scope, String requestDescription, Class<T> type) {
        Entry entry = entries.get(scope);
        if (entry == null) {
            return new Lookup.Absent<>();
        }
        if (!entry.fingerprint().equals(RequestFingerprint.of(requestDescription)) || !type.isInstance(entry.outcome())) {
            return new Lookup.Conflict<>();
        }
        return new Lookup.Replay<>(type.cast(entry.outcome()));
    }
}

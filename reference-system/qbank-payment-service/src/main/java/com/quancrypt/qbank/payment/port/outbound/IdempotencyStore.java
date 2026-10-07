package com.quancrypt.qbank.payment.port.outbound;

import com.quancrypt.qbank.payment.domain.model.IssuedReceipt;
import com.quancrypt.qbank.payment.domain.model.Payment;

/**
 * Remembers the outcome of requests that carried an idempotency key. The scope identifies the caller, the operation
 * and the key. The request description is compared by fingerprint only: an implementation must not keep it in
 * clear text, because it may contain a card number.
 */
public interface IdempotencyStore {

    /** What an earlier request with the same scope left behind. */
    sealed interface Lookup<T> {

        /** No earlier request with this scope. */
        record Absent<T>() implements Lookup<T> {
        }

        /** An earlier request with the same scope and the same description; its outcome. */
        record Replay<T>(T outcome) implements Lookup<T> {
        }

        /** An earlier request with the same scope but a different description. */
        record Conflict<T>() implements Lookup<T> {
        }
    }

    Lookup<Payment> findPayment(String scope, String requestDescription);

    void savePayment(String scope, String requestDescription, Payment payment);

    Lookup<IssuedReceipt> findReceipt(String scope, String requestDescription);

    void saveReceipt(String scope, String requestDescription, IssuedReceipt receipt);
}

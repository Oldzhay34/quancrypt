package com.quancrypt.qbank.payment.domain.model;

import java.util.Objects;

/** A receipt together with its signature. */
public record IssuedReceipt(Receipt receipt, ReceiptSignature signature) {

    public IssuedReceipt {
        Objects.requireNonNull(receipt, "receipt");
        Objects.requireNonNull(signature, "signature");
    }
}

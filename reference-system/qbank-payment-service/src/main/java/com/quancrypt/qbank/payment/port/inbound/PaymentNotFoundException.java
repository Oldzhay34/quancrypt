package com.quancrypt.qbank.payment.port.inbound;

/** The requested payment does not exist. */
public class PaymentNotFoundException extends RuntimeException {

    private static final long serialVersionUID = 1L;

    public PaymentNotFoundException() {
        super("payment not found");
    }
}

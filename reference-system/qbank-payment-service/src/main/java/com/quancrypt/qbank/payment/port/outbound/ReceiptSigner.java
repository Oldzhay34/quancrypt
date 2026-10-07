package com.quancrypt.qbank.payment.port.outbound;

import com.quancrypt.qbank.payment.domain.model.ReceiptSignature;

/** Signs the text of a receipt. */
public interface ReceiptSigner {

    /**
     * Signs the UTF-8 bytes of the text.
     *
     * @param signingInput the text to sign; must not be blank
     * @throws IllegalArgumentException when the text is blank
     */
    ReceiptSignature sign(String signingInput);
}

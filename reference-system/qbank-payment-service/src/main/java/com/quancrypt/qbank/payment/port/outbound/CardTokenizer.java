package com.quancrypt.qbank.payment.port.outbound;

import com.quancrypt.qbank.payment.domain.model.CardToken;

/** Protects a card number; the token cannot be reversed by this service (D-97). */
public interface CardTokenizer {

    /**
     * Returns the token of the card number.
     *
     * @param cardNumber the digits of a test card number; must not be blank
     * @throws IllegalArgumentException when the card number is blank
     */
    CardToken tokenize(String cardNumber);
}

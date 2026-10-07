package com.quancrypt.qbank.account.port.inbound;

import java.math.BigDecimal;

/** Account data as returned to the caller. */
public record AccountResult(String accountId, String ownerName, String currency, BigDecimal balance) {
}

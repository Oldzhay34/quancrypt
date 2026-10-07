package com.quancrypt.qbank.account.port.inbound;

/** Request for an account by a verified requester. */
public record GetAccountQuery(String accountId, String requesterUsername) {
}

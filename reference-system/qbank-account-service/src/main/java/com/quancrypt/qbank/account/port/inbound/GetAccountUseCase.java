package com.quancrypt.qbank.account.port.inbound;

/** Returns an account to its owner. */
public interface GetAccountUseCase {

    /**
     * Returns the account.
     *
     * @throws InvalidRequestException when the account id is malformed
     * @throws AccountNotFoundException when the account does not exist
     * @throws AccountAccessDeniedException when the requester does not own the account
     */
    AccountResult getAccount(GetAccountQuery query);
}

package com.quancrypt.qbank.payment.port.outbound;

import com.quancrypt.qbank.payment.domain.model.AccountId;
import com.quancrypt.qbank.payment.domain.model.AccountSummary;
import com.quancrypt.qbank.payment.domain.model.Caller;

/** Looks an account up in the account service on behalf of the caller. */
public interface AccountDirectory {

    /**
     * Returns the account when it exists and the caller owns it.
     *
     * @throws AccountLookupException with the reason NOT_FOUND, FORBIDDEN, UNAUTHORIZED or UNAVAILABLE
     */
    AccountSummary findAccount(AccountId accountId, Caller caller);
}

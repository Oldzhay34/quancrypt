package com.quancrypt.qbank.account.port.outbound;

import com.quancrypt.qbank.account.domain.model.Account;
import com.quancrypt.qbank.account.domain.model.AccountId;
import java.util.Optional;

/** Read access to accounts. */
public interface AccountRepository {

    Optional<Account> findById(AccountId accountId);
}

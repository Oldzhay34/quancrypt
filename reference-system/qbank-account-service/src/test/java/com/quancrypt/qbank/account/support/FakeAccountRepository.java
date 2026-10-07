package com.quancrypt.qbank.account.support;

import com.quancrypt.qbank.account.domain.model.Account;
import com.quancrypt.qbank.account.domain.model.AccountId;
import com.quancrypt.qbank.account.port.outbound.AccountRepository;
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;

/** Test double backed by a map. */
public final class FakeAccountRepository implements AccountRepository {

    private final Map<AccountId, Account> accounts = new HashMap<>();

    public FakeAccountRepository(Account... initial) {
        for (Account account : initial) {
            accounts.put(account.accountId(), account);
        }
    }

    @Override
    public Optional<Account> findById(AccountId accountId) {
        return Optional.ofNullable(accounts.get(accountId));
    }
}

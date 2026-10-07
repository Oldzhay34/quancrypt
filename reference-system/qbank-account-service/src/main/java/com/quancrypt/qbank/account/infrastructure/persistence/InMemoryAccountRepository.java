package com.quancrypt.qbank.account.infrastructure.persistence;

import com.quancrypt.qbank.account.domain.model.Account;
import com.quancrypt.qbank.account.domain.model.AccountId;
import com.quancrypt.qbank.account.port.outbound.AccountRepository;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;

/** Holds accounts in memory; the contents are fixed at construction time. */
public final class InMemoryAccountRepository implements AccountRepository {

    private final Map<AccountId, Account> accounts = new LinkedHashMap<>();

    public InMemoryAccountRepository(Collection<Account> initialAccounts) {
        for (Account account : initialAccounts) {
            if (accounts.putIfAbsent(account.accountId(), account) != null) {
                throw new IllegalArgumentException("duplicate account id");
            }
        }
    }

    @Override
    public Optional<Account> findById(AccountId accountId) {
        return Optional.ofNullable(accounts.get(accountId));
    }
}

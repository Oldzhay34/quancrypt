package com.quancrypt.qbank.account.usecase;

import com.quancrypt.qbank.account.domain.model.Account;
import com.quancrypt.qbank.account.domain.model.AccountId;
import com.quancrypt.qbank.account.domain.model.UserCredential;
import com.quancrypt.qbank.account.port.inbound.AccountAccessDeniedException;
import com.quancrypt.qbank.account.port.inbound.AccountNotFoundException;
import com.quancrypt.qbank.account.port.inbound.AccountResult;
import com.quancrypt.qbank.account.port.inbound.GetAccountQuery;
import com.quancrypt.qbank.account.port.inbound.GetAccountUseCase;
import com.quancrypt.qbank.account.port.inbound.InvalidRequestException;
import com.quancrypt.qbank.account.port.outbound.AccountRepository;
import com.quancrypt.qbank.account.port.outbound.CredentialRepository;
import java.util.Objects;

/** Returns an account to its owner. */
public final class GetAccountService implements GetAccountUseCase {

    private final AccountRepository accounts;
    private final CredentialRepository credentials;

    public GetAccountService(AccountRepository accounts, CredentialRepository credentials) {
        this.accounts = Objects.requireNonNull(accounts, "accounts");
        this.credentials = Objects.requireNonNull(credentials, "credentials");
    }

    @Override
    public AccountResult getAccount(GetAccountQuery query) {
        if (query == null || query.requesterUsername() == null) {
            throw new InvalidRequestException("account id and requester are required");
        }
        AccountId accountId = toAccountId(query.accountId());
        Account account = accounts.findById(accountId).orElseThrow(AccountNotFoundException::new);
        UserCredential requester = credentials.findByUsername(query.requesterUsername())
                .orElseThrow(AccountAccessDeniedException::new);
        if (!requester.owns(accountId)) {
            throw new AccountAccessDeniedException();
        }
        return new AccountResult(
                account.accountId().value(), account.ownerName(), account.currency(), account.balance());
    }

    private static AccountId toAccountId(String raw) {
        if (raw == null) {
            throw new InvalidRequestException("account id is required");
        }
        try {
            return new AccountId(raw);
        } catch (IllegalArgumentException e) {
            throw new InvalidRequestException("account id is malformed");
        }
    }
}

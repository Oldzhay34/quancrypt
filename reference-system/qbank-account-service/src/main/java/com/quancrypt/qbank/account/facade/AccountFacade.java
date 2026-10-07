package com.quancrypt.qbank.account.facade;

import com.quancrypt.qbank.account.facade.dto.AccountView;
import com.quancrypt.qbank.account.facade.error.BadRequestException;
import com.quancrypt.qbank.account.facade.error.ForbiddenException;
import com.quancrypt.qbank.account.facade.error.ResourceNotFoundException;
import com.quancrypt.qbank.account.port.inbound.AccountAccessDeniedException;
import com.quancrypt.qbank.account.port.inbound.AccountNotFoundException;
import com.quancrypt.qbank.account.port.inbound.AccountResult;
import com.quancrypt.qbank.account.port.inbound.GetAccountQuery;
import com.quancrypt.qbank.account.port.inbound.GetAccountUseCase;
import com.quancrypt.qbank.account.port.inbound.InvalidRequestException;
import java.util.Objects;

/** Entry point of the api layer for account data. */
public final class AccountFacade {

    private final GetAccountUseCase getAccount;

    public AccountFacade(GetAccountUseCase getAccount) {
        this.getAccount = Objects.requireNonNull(getAccount, "getAccount");
    }

    /**
     * Returns an account to a verified requester.
     *
     * @throws BadRequestException when the account id is malformed
     * @throws ResourceNotFoundException when the account does not exist
     * @throws ForbiddenException when the requester does not own the account
     */
    public AccountView getAccount(String accountId, String requesterUsername) {
        try {
            AccountResult result = getAccount.getAccount(new GetAccountQuery(accountId, requesterUsername));
            return new AccountView(
                    result.accountId(), result.ownerName(), result.currency(), result.balance().toPlainString());
        } catch (InvalidRequestException e) {
            throw new BadRequestException(e.getMessage());
        } catch (AccountNotFoundException e) {
            throw new ResourceNotFoundException();
        } catch (AccountAccessDeniedException e) {
            throw new ForbiddenException();
        }
    }
}

package com.quancrypt.qbank.account.unit.usecase;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.quancrypt.qbank.account.port.inbound.AccountAccessDeniedException;
import com.quancrypt.qbank.account.port.inbound.AccountNotFoundException;
import com.quancrypt.qbank.account.port.inbound.AccountResult;
import com.quancrypt.qbank.account.port.inbound.GetAccountQuery;
import com.quancrypt.qbank.account.port.inbound.InvalidRequestException;
import com.quancrypt.qbank.account.support.FakeAccountRepository;
import com.quancrypt.qbank.account.support.FakeCredentialRepository;
import com.quancrypt.qbank.account.support.TestData;
import com.quancrypt.qbank.account.usecase.GetAccountService;
import org.junit.jupiter.api.Test;

class GetAccountServiceTest {

    private final GetAccountService service = new GetAccountService(
            new FakeAccountRepository(TestData.ACCOUNT_1, TestData.ACCOUNT_2),
            new FakeCredentialRepository(TestData.USER_1, TestData.USER_2));

    @Test
    void theOwnerGetsTheAccount() {
        AccountResult result = service.getAccount(new GetAccountQuery("acc-001", "demo1"));

        assertThat(result.accountId()).isEqualTo("acc-001");
        assertThat(result.ownerName()).isEqualTo("Demo User 1");
        assertThat(result.currency()).isEqualTo("TRY");
        assertThat(result.balance().toPlainString()).isEqualTo("1000.00");
    }

    @Test
    void anotherUsersAccountIsDenied() {
        assertThatThrownBy(() -> service.getAccount(new GetAccountQuery("acc-002", "demo1")))
                .isInstanceOf(AccountAccessDeniedException.class);
    }

    @Test
    void aRequesterWithoutCredentialIsDenied() {
        assertThatThrownBy(() -> service.getAccount(new GetAccountQuery("acc-001", "ghost")))
                .isInstanceOf(AccountAccessDeniedException.class);
    }

    @Test
    void anUnknownAccountIsNotFoundBeforeOwnershipIsChecked() {
        assertThatThrownBy(() -> service.getAccount(new GetAccountQuery("acc-999", "demo1")))
                .isInstanceOf(AccountNotFoundException.class);
        assertThatThrownBy(() -> service.getAccount(new GetAccountQuery("acc-999", "ghost")))
                .isInstanceOf(AccountNotFoundException.class);
    }

    @Test
    void aMalformedAccountIdIsAnInvalidRequest() {
        assertThatThrownBy(() -> service.getAccount(new GetAccountQuery(" ", "demo1")))
                .isInstanceOf(InvalidRequestException.class);
        assertThatThrownBy(() -> service.getAccount(new GetAccountQuery("a".repeat(65), "demo1")))
                .isInstanceOf(InvalidRequestException.class);
        assertThatThrownBy(() -> service.getAccount(new GetAccountQuery(null, "demo1")))
                .isInstanceOf(InvalidRequestException.class);
    }

    @Test
    void aMissingQueryOrRequesterIsAnInvalidRequest() {
        assertThatThrownBy(() -> service.getAccount(null)).isInstanceOf(InvalidRequestException.class);
        assertThatThrownBy(() -> service.getAccount(new GetAccountQuery("acc-001", null)))
                .isInstanceOf(InvalidRequestException.class);
    }
}

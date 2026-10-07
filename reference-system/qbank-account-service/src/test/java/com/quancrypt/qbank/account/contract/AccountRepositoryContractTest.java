package com.quancrypt.qbank.account.contract;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.quancrypt.qbank.account.domain.model.Account;
import com.quancrypt.qbank.account.domain.model.AccountId;
import com.quancrypt.qbank.account.infrastructure.persistence.InMemoryAccountRepository;
import com.quancrypt.qbank.account.port.outbound.AccountRepository;
import com.quancrypt.qbank.account.support.FakeAccountRepository;
import com.quancrypt.qbank.account.support.TestData;
import java.util.List;
import org.junit.jupiter.api.Test;

/** Every AccountRepository implementation must pass these tests (Liskov substitution). */
abstract class AccountRepositoryContractTest {

    abstract AccountRepository create(List<Account> accounts);

    @Test
    void findsAnExistingAccountById() {
        AccountRepository repository = create(List.of(TestData.ACCOUNT_1, TestData.ACCOUNT_2));

        assertThat(repository.findById(TestData.ACC_2)).contains(TestData.ACCOUNT_2);
    }

    @Test
    void returnsEmptyForAnUnknownId() {
        AccountRepository repository = create(List.of(TestData.ACCOUNT_1));

        assertThat(repository.findById(new AccountId("unknown"))).isEmpty();
    }

    @Test
    void anEmptyRepositoryFindsNothing() {
        assertThat(create(List.of()).findById(TestData.ACC_1)).isEmpty();
    }
}

class FakeAccountRepositoryContractTest extends AccountRepositoryContractTest {

    @Override
    AccountRepository create(List<Account> accounts) {
        return new FakeAccountRepository(accounts.toArray(Account[]::new));
    }
}

class InMemoryAccountRepositoryContractTest extends AccountRepositoryContractTest {

    @Override
    AccountRepository create(List<Account> accounts) {
        return new InMemoryAccountRepository(accounts);
    }

    @Test
    void rejectsDuplicateAccountIds() {
        assertThatThrownBy(() -> new InMemoryAccountRepository(List.of(TestData.ACCOUNT_1, TestData.ACCOUNT_1)))
                .isInstanceOf(IllegalArgumentException.class);
    }
}

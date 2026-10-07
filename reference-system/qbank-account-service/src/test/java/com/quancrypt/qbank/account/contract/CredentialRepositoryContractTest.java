package com.quancrypt.qbank.account.contract;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.quancrypt.qbank.account.domain.model.UserCredential;
import com.quancrypt.qbank.account.infrastructure.persistence.InMemoryCredentialRepository;
import com.quancrypt.qbank.account.port.outbound.CredentialRepository;
import com.quancrypt.qbank.account.support.FakeCredentialRepository;
import com.quancrypt.qbank.account.support.TestData;
import java.util.List;
import org.junit.jupiter.api.Test;

/** Every CredentialRepository implementation must pass these tests (Liskov substitution). */
abstract class CredentialRepositoryContractTest {

    abstract CredentialRepository create(List<UserCredential> credentials);

    @Test
    void findsAnExistingCredentialByUsername() {
        CredentialRepository repository = create(List.of(TestData.USER_1, TestData.USER_2));

        assertThat(repository.findByUsername("demo2")).contains(TestData.USER_2);
    }

    @Test
    void returnsEmptyForAnUnknownUsername() {
        CredentialRepository repository = create(List.of(TestData.USER_1));

        assertThat(repository.findByUsername("nobody")).isEmpty();
    }

    @Test
    void usernamesAreCaseSensitive() {
        CredentialRepository repository = create(List.of(TestData.USER_1));

        assertThat(repository.findByUsername("DEMO1")).isEmpty();
    }
}

class FakeCredentialRepositoryContractTest extends CredentialRepositoryContractTest {

    @Override
    CredentialRepository create(List<UserCredential> credentials) {
        return new FakeCredentialRepository(credentials.toArray(UserCredential[]::new));
    }
}

class InMemoryCredentialRepositoryContractTest extends CredentialRepositoryContractTest {

    @Override
    CredentialRepository create(List<UserCredential> credentials) {
        return new InMemoryCredentialRepository(credentials);
    }

    @Test
    void rejectsDuplicateUsernames() {
        assertThatThrownBy(() -> new InMemoryCredentialRepository(List.of(TestData.USER_1, TestData.USER_1)))
                .isInstanceOf(IllegalArgumentException.class);
    }
}

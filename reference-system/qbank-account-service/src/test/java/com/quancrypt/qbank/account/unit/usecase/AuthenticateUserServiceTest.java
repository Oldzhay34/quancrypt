package com.quancrypt.qbank.account.unit.usecase;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.assertj.core.api.Assertions.catchThrowable;

import com.quancrypt.qbank.account.port.inbound.AuthenticateUserCommand;
import com.quancrypt.qbank.account.port.inbound.AuthenticationResult;
import com.quancrypt.qbank.account.port.inbound.InvalidCredentialsException;
import com.quancrypt.qbank.account.port.inbound.InvalidRequestException;
import com.quancrypt.qbank.account.support.FakeCredentialRepository;
import com.quancrypt.qbank.account.support.FakePasswordVerifier;
import com.quancrypt.qbank.account.support.FakeTokenIssuer;
import com.quancrypt.qbank.account.support.FixedClock;
import com.quancrypt.qbank.account.support.TestData;
import com.quancrypt.qbank.account.usecase.AuthenticateUserService;
import java.time.Duration;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class AuthenticateUserServiceTest {

    private static final Duration LIFETIME = Duration.ofMinutes(15);

    private FakeTokenIssuer tokenIssuer;
    private AuthenticateUserService service;

    @BeforeEach
    void setUp() {
        tokenIssuer = new FakeTokenIssuer();
        service = new AuthenticateUserService(
                new FakeCredentialRepository(TestData.USER_1, TestData.USER_2),
                new FakePasswordVerifier(),
                tokenIssuer,
                new FixedClock(TestData.NOW),
                LIFETIME);
    }

    @Test
    void correctCredentialsIssueATokenForTheUser() {
        AuthenticationResult result = service.authenticate(new AuthenticateUserCommand("demo1", "pw-1"));

        assertThat(result.accessToken()).isEqualTo("fake-token-for-demo1");
        assertThat(result.expiresInSeconds()).isEqualTo(900);
        assertThat(tokenIssuer.calls()).containsExactly(
                new FakeTokenIssuer.Call("demo1", TestData.NOW, LIFETIME));
    }

    @Test
    void wrongPasswordIsRejectedAndNoTokenIsIssued() {
        assertThatThrownBy(() -> service.authenticate(new AuthenticateUserCommand("demo1", "wrong")))
                .isInstanceOf(InvalidCredentialsException.class);
        assertThat(tokenIssuer.calls()).isEmpty();
    }

    @Test
    void unknownUserIsIndistinguishableFromWrongPassword() {
        Throwable unknownUser = catchThrowable(
                () -> service.authenticate(new AuthenticateUserCommand("nobody", "pw-1")));
        Throwable wrongPassword = catchThrowable(
                () -> service.authenticate(new AuthenticateUserCommand("demo1", "wrong")));

        assertThat(unknownUser).isInstanceOf(InvalidCredentialsException.class);
        assertThat(unknownUser.getClass()).isEqualTo(wrongPassword.getClass());
        assertThat(unknownUser.getMessage()).isEqualTo(wrongPassword.getMessage());
        assertThat(tokenIssuer.calls()).isEmpty();
    }

    @Test
    void missingOrBlankInputIsAnInvalidRequest() {
        assertThatThrownBy(() -> service.authenticate(null)).isInstanceOf(InvalidRequestException.class);
        assertThatThrownBy(() -> service.authenticate(new AuthenticateUserCommand(null, "pw-1")))
                .isInstanceOf(InvalidRequestException.class);
        assertThatThrownBy(() -> service.authenticate(new AuthenticateUserCommand("demo1", " ")))
                .isInstanceOf(InvalidRequestException.class);
        assertThatThrownBy(() -> service.authenticate(new AuthenticateUserCommand(" ", "pw-1")))
                .isInstanceOf(InvalidRequestException.class);
    }

    @Test
    void theCommandAndResultNeverPrintSecrets() {
        assertThat(new AuthenticateUserCommand("demo1", "pw-1").toString()).doesNotContain("pw-1");
        assertThat(new AuthenticationResult("secret-token", 900).toString()).doesNotContain("secret-token");
    }

    @Test
    void theTokenLifetimeMustBePositive() {
        FakeCredentialRepository credentials = new FakeCredentialRepository();
        FakePasswordVerifier verifier = new FakePasswordVerifier();
        FixedClock clock = new FixedClock(TestData.NOW);
        assertThatThrownBy(() -> new AuthenticateUserService(credentials, verifier, tokenIssuer, clock, Duration.ZERO))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new AuthenticateUserService(
                credentials, verifier, tokenIssuer, clock, Duration.ofSeconds(-1)))
                .isInstanceOf(IllegalArgumentException.class);
    }
}

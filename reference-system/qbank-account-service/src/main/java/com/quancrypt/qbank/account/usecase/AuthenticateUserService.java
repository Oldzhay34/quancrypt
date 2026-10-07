package com.quancrypt.qbank.account.usecase;

import com.quancrypt.qbank.account.domain.model.UserCredential;
import com.quancrypt.qbank.account.port.inbound.AuthenticateUserCommand;
import com.quancrypt.qbank.account.port.inbound.AuthenticateUserUseCase;
import com.quancrypt.qbank.account.port.inbound.AuthenticationResult;
import com.quancrypt.qbank.account.port.inbound.InvalidCredentialsException;
import com.quancrypt.qbank.account.port.inbound.InvalidRequestException;
import com.quancrypt.qbank.account.port.outbound.Clock;
import com.quancrypt.qbank.account.port.outbound.CredentialRepository;
import com.quancrypt.qbank.account.port.outbound.PasswordVerifier;
import com.quancrypt.qbank.account.port.outbound.TokenIssuer;
import java.time.Duration;
import java.util.Objects;

/** Verifies a username and password and issues an access token. */
public final class AuthenticateUserService implements AuthenticateUserUseCase {

    private final CredentialRepository credentials;
    private final PasswordVerifier passwordVerifier;
    private final TokenIssuer tokenIssuer;
    private final Clock clock;
    private final Duration tokenLifetime;

    public AuthenticateUserService(
            CredentialRepository credentials,
            PasswordVerifier passwordVerifier,
            TokenIssuer tokenIssuer,
            Clock clock,
            Duration tokenLifetime) {
        this.credentials = Objects.requireNonNull(credentials, "credentials");
        this.passwordVerifier = Objects.requireNonNull(passwordVerifier, "passwordVerifier");
        this.tokenIssuer = Objects.requireNonNull(tokenIssuer, "tokenIssuer");
        this.clock = Objects.requireNonNull(clock, "clock");
        this.tokenLifetime = Objects.requireNonNull(tokenLifetime, "tokenLifetime");
        if (tokenLifetime.isZero() || tokenLifetime.isNegative()) {
            throw new IllegalArgumentException("token lifetime must be positive");
        }
    }

    @Override
    public AuthenticationResult authenticate(AuthenticateUserCommand command) {
        if (command == null || isBlank(command.username()) || isBlank(command.password())) {
            throw new InvalidRequestException("username and password are required");
        }
        UserCredential credential = credentials.findByUsername(command.username())
                .orElseThrow(InvalidCredentialsException::new);
        if (!passwordVerifier.matches(command.password(), credential.passwordHash())) {
            throw new InvalidCredentialsException();
        }
        String token = tokenIssuer.issue(credential.username(), clock.now(), tokenLifetime);
        return new AuthenticationResult(token, tokenLifetime.toSeconds());
    }

    private static boolean isBlank(String value) {
        return value == null || value.isBlank();
    }
}

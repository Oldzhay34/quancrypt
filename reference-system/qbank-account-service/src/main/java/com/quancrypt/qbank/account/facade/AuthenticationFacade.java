package com.quancrypt.qbank.account.facade;

import com.quancrypt.qbank.account.facade.dto.LoginView;
import com.quancrypt.qbank.account.facade.error.BadRequestException;
import com.quancrypt.qbank.account.facade.error.UnauthorizedException;
import com.quancrypt.qbank.account.port.inbound.AuthenticateUserCommand;
import com.quancrypt.qbank.account.port.inbound.AuthenticateUserUseCase;
import com.quancrypt.qbank.account.port.inbound.AuthenticationResult;
import com.quancrypt.qbank.account.port.inbound.InvalidCredentialsException;
import com.quancrypt.qbank.account.port.inbound.InvalidRequestException;
import java.util.Objects;

/** Entry point of the api layer for authentication. */
public final class AuthenticationFacade {

    private static final String TOKEN_TYPE = "Bearer";

    private final AuthenticateUserUseCase authenticateUser;

    public AuthenticationFacade(AuthenticateUserUseCase authenticateUser) {
        this.authenticateUser = Objects.requireNonNull(authenticateUser, "authenticateUser");
    }

    /**
     * Logs a user in.
     *
     * @throws BadRequestException when username or password is missing
     * @throws UnauthorizedException when the credentials are wrong
     */
    public LoginView login(String username, String password) {
        try {
            AuthenticationResult result = authenticateUser.authenticate(new AuthenticateUserCommand(username, password));
            return new LoginView(result.accessToken(), TOKEN_TYPE, result.expiresInSeconds());
        } catch (InvalidRequestException e) {
            throw new BadRequestException(e.getMessage());
        } catch (InvalidCredentialsException e) {
            throw new UnauthorizedException();
        }
    }
}

package com.quancrypt.qbank.account.port.inbound;

/** Authenticates a user with username and password and issues an access token. */
public interface AuthenticateUserUseCase {

    /**
     * Authenticates the user.
     *
     * @throws InvalidRequestException when username or password is missing
     * @throws InvalidCredentialsException when the username is unknown or the password is wrong
     */
    AuthenticationResult authenticate(AuthenticateUserCommand command);
}

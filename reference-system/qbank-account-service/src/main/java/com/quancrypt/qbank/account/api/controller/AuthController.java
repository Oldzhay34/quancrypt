package com.quancrypt.qbank.account.api.controller;

import com.quancrypt.qbank.account.api.dto.LoginRequest;
import com.quancrypt.qbank.account.api.dto.LoginResponse;
import com.quancrypt.qbank.account.facade.AuthenticationFacade;
import com.quancrypt.qbank.account.facade.dto.LoginView;
import com.quancrypt.qbank.account.facade.error.BadRequestException;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

/** POST /api/v1/auth/login. */
@RestController
public class AuthController {

    private static final int MAX_USERNAME_LENGTH = 64;
    private static final int MAX_PASSWORD_LENGTH = 128;

    private final AuthenticationFacade facade;

    public AuthController(AuthenticationFacade facade) {
        this.facade = facade;
    }

    @PostMapping("/api/v1/auth/login")
    public LoginResponse login(@RequestBody(required = false) LoginRequest request) {
        validate(request);
        LoginView view = facade.login(request.username(), request.password());
        return new LoginResponse(view.accessToken(), view.tokenType(), view.expiresIn());
    }

    private static void validate(LoginRequest request) {
        if (request == null
                || isInvalid(request.username(), MAX_USERNAME_LENGTH)
                || isInvalid(request.password(), MAX_PASSWORD_LENGTH)) {
            throw new BadRequestException("username and password are required");
        }
    }

    private static boolean isInvalid(String value, int maxLength) {
        return value == null || value.isEmpty() || value.length() > maxLength;
    }
}

package com.quancrypt.qbank.account.api.controller;

import com.quancrypt.qbank.account.api.dto.AccountResponse;
import com.quancrypt.qbank.account.facade.AccountFacade;
import com.quancrypt.qbank.account.facade.dto.AccountView;
import com.quancrypt.qbank.account.facade.error.UnauthorizedException;
import jakarta.servlet.http.HttpServletRequest;
import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

/** GET /api/v1/accounts/{accountId}. The requester is the user the access token filter verified. */
@RestController
public class AccountController {

    private final AccountFacade facade;

    public AccountController(AccountFacade facade) {
        this.facade = facade;
    }

    @GetMapping("/api/v1/accounts/{accountId}")
    public AccountResponse account(@PathVariable String accountId, HttpServletRequest request) {
        Principal requester = request.getUserPrincipal();
        if (requester == null) {
            throw new UnauthorizedException();
        }
        AccountView view = facade.getAccount(accountId, requester.getName());
        return new AccountResponse(view.accountId(), view.ownerName(), view.currency(), view.balance());
    }
}

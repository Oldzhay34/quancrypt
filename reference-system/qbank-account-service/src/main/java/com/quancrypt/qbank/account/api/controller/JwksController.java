package com.quancrypt.qbank.account.api.controller;

import com.quancrypt.qbank.account.api.dto.JwkResponse;
import com.quancrypt.qbank.account.api.dto.JwksResponse;
import com.quancrypt.qbank.account.facade.JwksFacade;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

/** GET /.well-known/jwks.json. */
@RestController
public class JwksController {

    private final JwksFacade facade;

    public JwksController(JwksFacade facade) {
        this.facade = facade;
    }

    @GetMapping("/.well-known/jwks.json")
    public JwksResponse jwks() {
        return new JwksResponse(facade.getJwks().keys().stream()
                .map(key -> new JwkResponse(key.kty(), key.use(), key.alg(), key.kid(), key.n(), key.e()))
                .toList());
    }
}

package com.quancrypt.qbank.account.api.dto;

import java.util.List;

/** Response body of GET /.well-known/jwks.json. */
public record JwksResponse(List<JwkResponse> keys) {

    public JwksResponse {
        keys = List.copyOf(keys);
    }
}

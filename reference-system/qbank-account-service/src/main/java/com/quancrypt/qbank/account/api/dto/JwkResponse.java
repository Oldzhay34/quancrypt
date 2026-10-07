package com.quancrypt.qbank.account.api.dto;

/** One RSA public key of GET /.well-known/jwks.json. */
public record JwkResponse(String kty, String use, String alg, String kid, String n, String e) {
}

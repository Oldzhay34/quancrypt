package com.quancrypt.qbank.account.facade.dto;

/** An RSA public key in JWK form (RFC 7517); modulus and exponent are base64url encoded. */
public record JwkView(String kty, String use, String alg, String kid, String n, String e) {
}

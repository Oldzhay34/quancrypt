package com.quancrypt.qbank.payment.support;

import com.nimbusds.jose.JOSEException;
import com.nimbusds.jose.JOSEObjectType;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.JWSSigner;
import com.nimbusds.jose.crypto.MACSigner;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.PlainJWT;
import com.nimbusds.jwt.SignedJWT;
import com.quancrypt.qbank.payment.infrastructure.crypto.JwkThumbprint;
import com.quancrypt.qbank.payment.infrastructure.crypto.PemKeyLoader;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.Date;

/** Builds valid and deliberately forged account-service tokens for tests, using the real jwt-signing demo key. */
public final class TokenFactory {

    private final RSAPrivateKey privateKey = PemKeyLoader.loadPrivateKey(TestCertificates.file("jwt-signing.key.pem"));
    private final RSAPublicKey publicKey = PemKeyLoader.loadPublicKey(TestCertificates.file("jwt-signing.pub.pem"));
    private final String keyId = JwkThumbprint.of(publicKey);

    /** A correctly signed token for the subject, valid for five minutes. */
    public String valid(String subject) {
        Instant now = Instant.now();
        return sign(privateKey, keyId, claims(subject, now, now.plusSeconds(300)));
    }

    public String expired(String subject) {
        Instant now = Instant.now();
        return sign(privateKey, keyId, claims(subject, now.minusSeconds(900), now.minusSeconds(600)));
    }

    public String withoutSubject() {
        Instant now = Instant.now();
        JWTClaimsSet claims = new JWTClaimsSet.Builder()
                .issueTime(Date.from(now)).expirationTime(Date.from(now.plusSeconds(300))).build();
        return sign(privateKey, keyId, claims);
    }

    public String withoutExpiry(String subject) {
        return sign(privateKey, keyId, new JWTClaimsSet.Builder().subject(subject).issueTime(new Date()).build());
    }

    /** Signed with a different RSA key (the card token key) but carrying the account service's key id. */
    public String signedByAnotherKey(String subject) {
        Instant now = Instant.now();
        RSAPrivateKey other = PemKeyLoader.loadPrivateKey(TestCertificates.file("card-token.key.pem"));
        return sign(other, keyId, claims(subject, now, now.plusSeconds(300)));
    }

    /** An unsecured token (alg none). */
    public String unsecured(String subject) {
        Instant now = Instant.now();
        return new PlainJWT(claims(subject, now, now.plusSeconds(300))).serialize();
    }

    /** HS256 token whose secret is the public key's bytes: the classic algorithm confusion attack. */
    public String hs256WithPublicKeyAsSecret(String subject) {
        Instant now = Instant.now();
        JWSHeader header = new JWSHeader.Builder(JWSAlgorithm.HS256).keyID(keyId).type(JOSEObjectType.JWT).build();
        try {
            return sign(header, claims(subject, now, now.plusSeconds(300)), new MACSigner(publicKey.getEncoded()));
        } catch (JOSEException e) {
            throw new IllegalStateException("cannot create MAC signer", e);
        }
    }

    private static JWTClaimsSet claims(String subject, Instant issuedAt, Instant expiresAt) {
        return new JWTClaimsSet.Builder()
                .subject(subject).issueTime(Date.from(issuedAt)).expirationTime(Date.from(expiresAt)).build();
    }

    private static String sign(RSAPrivateKey key, String keyId, JWTClaimsSet claims) {
        JWSHeader header = new JWSHeader.Builder(JWSAlgorithm.RS256).keyID(keyId).type(JOSEObjectType.JWT).build();
        return sign(header, claims, new RSASSASigner(key));
    }

    private static String sign(JWSHeader header, JWTClaimsSet claims, JWSSigner signer) {
        try {
            SignedJWT jwt = new SignedJWT(header, claims);
            jwt.sign(signer);
            return jwt.serialize();
        } catch (JOSEException e) {
            throw new IllegalStateException("cannot sign test token", e);
        }
    }
}

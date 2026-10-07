package com.quancrypt.qbank.account.support;

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
import com.quancrypt.qbank.account.infrastructure.security.JwtKeyMaterial;
import com.quancrypt.qbank.account.infrastructure.security.PemKeyLoader;
import java.security.interfaces.RSAPrivateKey;
import java.time.Instant;
import java.util.Date;

/** Builds valid and deliberately forged tokens for tests, using the real demo keys. */
public final class TokenFactory {

    private final JwtKeyMaterial keys;

    public TokenFactory(JwtKeyMaterial keys) {
        this.keys = keys;
    }

    public static JwtKeyMaterial realKeys() {
        return JwtKeyMaterial.load(
                TestCertificates.file("jwt-signing.key.pem"), TestCertificates.file("jwt-signing.pub.pem"));
    }

    /** A correctly signed token for the subject, valid for one minute. */
    public String valid(String subject) {
        Instant now = Instant.now();
        return rs256(subject, keys.keyId(), now, now.plusSeconds(60));
    }

    public String expired(String subject) {
        Instant now = Instant.now();
        return rs256(subject, keys.keyId(), now.minusSeconds(120), now.minusSeconds(1));
    }

    public String withKeyId(String subject, String keyId) {
        Instant now = Instant.now();
        return rs256(subject, keyId, now, now.plusSeconds(60));
    }

    public String rs256(String subject, String keyId, Instant issuedAt, Instant expiresAt) {
        return sign(keys.privateKey(), keyId, claims(subject, issuedAt, expiresAt));
    }

    /** Signed with a different RSA key (the card token key) but carrying this service's key id. */
    public String signedByAnotherKey(String subject) {
        RSAPrivateKey other = PemKeyLoader.loadPrivateKey(TestCertificates.file("card-token.key.pem"));
        Instant now = Instant.now();
        return sign(other, keys.keyId(), claims(subject, now, now.plusSeconds(60)));
    }

    public String withoutExpiry(String subject) {
        JWTClaimsSet claims = new JWTClaimsSet.Builder().subject(subject).issueTime(new Date()).build();
        return sign(keys.privateKey(), keys.keyId(), claims);
    }

    public String withoutSubject() {
        Instant now = Instant.now();
        JWTClaimsSet claims = new JWTClaimsSet.Builder()
                .issueTime(Date.from(now)).expirationTime(Date.from(now.plusSeconds(60))).build();
        return sign(keys.privateKey(), keys.keyId(), claims);
    }

    /** An unsecured token (alg none). */
    public String unsecured(String subject) {
        Instant now = Instant.now();
        return new PlainJWT(claims(subject, now, now.plusSeconds(60))).serialize();
    }

    /** HS256 token whose secret is the public key's bytes: the classic algorithm confusion attack. */
    public String hs256WithPublicKeyAsSecret(String subject) {
        Instant now = Instant.now();
        JWSHeader header = new JWSHeader.Builder(JWSAlgorithm.HS256).keyID(keys.keyId()).type(JOSEObjectType.JWT).build();
        return sign(header, claims(subject, now, now.plusSeconds(60)), macSigner(keys.publicKey().getEncoded()));
    }

    /**
     * A valid token with one character inside the signature altered. The last character is deliberately avoided:
     * its low bits are base64 padding bits that decoders ignore, so changing it can leave the signature intact.
     */
    public String withTamperedSignature(String subject) {
        String token = valid(subject);
        int index = token.lastIndexOf('.') + 11;
        char original = token.charAt(index);
        return token.substring(0, index) + (original == 'A' ? 'B' : 'A') + token.substring(index + 1);
    }

    private static JWTClaimsSet claims(String subject, Instant issuedAt, Instant expiresAt) {
        return new JWTClaimsSet.Builder()
                .subject(subject).issueTime(Date.from(issuedAt)).expirationTime(Date.from(expiresAt)).build();
    }

    private static String sign(RSAPrivateKey key, String keyId, JWTClaimsSet claims) {
        JWSHeader header = new JWSHeader.Builder(JWSAlgorithm.RS256).keyID(keyId).type(JOSEObjectType.JWT).build();
        try {
            return sign(header, claims, new RSASSASigner(key));
        } catch (RuntimeException e) {
            throw new IllegalStateException("cannot sign test token", e);
        }
    }

    private static MACSigner macSigner(byte[] secret) {
        try {
            return new MACSigner(secret);
        } catch (JOSEException e) {
            throw new IllegalStateException("cannot create MAC signer", e);
        }
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

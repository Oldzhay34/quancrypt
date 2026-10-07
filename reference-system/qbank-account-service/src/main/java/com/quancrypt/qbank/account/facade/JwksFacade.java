package com.quancrypt.qbank.account.facade;

import com.quancrypt.qbank.account.facade.dto.JwkView;
import com.quancrypt.qbank.account.facade.dto.JwksView;
import com.quancrypt.qbank.account.port.inbound.GetJwksUseCase;
import com.quancrypt.qbank.account.port.inbound.JwksResult;
import java.math.BigInteger;
import java.util.Arrays;
import java.util.Base64;
import java.util.Objects;

/** Entry point of the api layer for the JSON Web Key Set. */
public final class JwksFacade {

    private static final Base64.Encoder BASE64_URL = Base64.getUrlEncoder().withoutPadding();

    private final GetJwksUseCase getJwks;

    public JwksFacade(GetJwksUseCase getJwks) {
        this.getJwks = Objects.requireNonNull(getJwks, "getJwks");
    }

    public JwksView getJwks() {
        return new JwksView(getJwks.getJwks().keys().stream().map(JwksFacade::toView).toList());
    }

    private static JwkView toView(JwksResult.Key key) {
        return new JwkView("RSA", "sig", "RS256", key.keyId(), encode(key.modulus()), encode(key.exponent()));
    }

    /** Unsigned big-endian bytes without leading zero bytes, base64url encoded without padding (RFC 7518, section 6.3). */
    private static String encode(BigInteger value) {
        byte[] bytes = value.toByteArray();
        int start = bytes.length > 1 && bytes[0] == 0 ? 1 : 0;
        return BASE64_URL.encodeToString(Arrays.copyOfRange(bytes, start, bytes.length));
    }
}

package com.quancrypt.qbank.account.unit.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.qbank.account.infrastructure.security.AccessTokenFilter;
import com.quancrypt.qbank.account.infrastructure.security.JwtKeyMaterial;
import com.quancrypt.qbank.account.support.TokenFactory;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import java.io.IOException;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockFilterChain;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

class AccessTokenFilterTest {

    private final JwtKeyMaterial keys = TokenFactory.realKeys();
    private final TokenFactory tokens = new TokenFactory(keys);
    private final AccessTokenFilter filter = new AccessTokenFilter(keys);

    private record Outcome(MockHttpServletResponse response, MockFilterChain chain) {

        boolean passedThrough() {
            return chain.getRequest() != null;
        }
    }

    private Outcome call(String authorizationHeader) throws ServletException, IOException {
        MockHttpServletRequest request = new MockHttpServletRequest("GET", "/api/v1/accounts/acc-001");
        if (authorizationHeader != null) {
            request.addHeader("Authorization", authorizationHeader);
        }
        MockHttpServletResponse response = new MockHttpServletResponse();
        MockFilterChain chain = new MockFilterChain();
        filter.doFilter(request, response, chain);
        return new Outcome(response, chain);
    }

    private void assertRejected(String authorizationHeader) throws Exception {
        Outcome outcome = call(authorizationHeader);

        assertThat(outcome.passedThrough()).as("request must not reach the controller").isFalse();
        MockHttpServletResponse response = outcome.response();
        assertThat(response.getStatus()).isEqualTo(401);
        assertThat(response.getContentType()).startsWith("application/problem+json");
        JsonNode body = JsonMapper.builder().build().readTree(response.getContentAsString());
        assertThat(body.get("type").asString()).isEqualTo("https://quancrypt.local/problems/unauthorized");
        assertThat(body.get("title").asString()).isEqualTo("Unauthorized");
        assertThat(body.get("status").asInt()).isEqualTo(401);
    }

    @Test
    void aValidTokenPassesAndExposesTheSubjectAsUserPrincipal() throws Exception {
        Outcome outcome = call("Bearer " + tokens.valid("demo1"));

        assertThat(outcome.passedThrough()).isTrue();
        HttpServletRequest forwarded = (HttpServletRequest) outcome.chain().getRequest();
        assertThat(forwarded.getUserPrincipal().getName()).isEqualTo("demo1");
        assertThat(forwarded.getRemoteUser()).isEqualTo("demo1");
        assertThat(outcome.response().getStatus()).isEqualTo(200);
    }

    @Test
    void theBearerSchemeIsCaseInsensitive() throws Exception {
        assertThat(call("bearer " + tokens.valid("demo1")).passedThrough()).isTrue();
    }

    @Test
    void aMissingOrMalformedAuthorizationHeaderIsRejected() throws Exception {
        assertRejected(null);
        assertRejected("");
        assertRejected("Bearer");
        assertRejected("Bearer ");
        assertRejected("Basic " + tokens.valid("demo1"));
        assertRejected(tokens.valid("demo1"));
        assertRejected("Bearer not-a-jwt");
    }

    @Test
    void anExpiredTokenIsRejected() throws Exception {
        assertRejected("Bearer " + tokens.expired("demo1"));
    }

    @Test
    void aTokenWithAnotherKeyIdIsRejected() throws Exception {
        assertRejected("Bearer " + tokens.withKeyId("demo1", "some-other-key-id"));
    }

    @Test
    void aTokenSignedByAnotherKeyIsRejectedEvenWithTheRightKeyId() throws Exception {
        assertRejected("Bearer " + tokens.signedByAnotherKey("demo1"));
    }

    @Test
    void aTamperedSignatureIsRejected() throws Exception {
        assertRejected("Bearer " + tokens.withTamperedSignature("demo1"));
    }

    @Test
    void unsecuredTokensAreRejected() throws Exception {
        assertRejected("Bearer " + tokens.unsecured("demo1"));
    }

    @Test
    void anHs256TokenSignedWithThePublicKeyAsSecretIsRejected() throws Exception {
        assertRejected("Bearer " + tokens.hs256WithPublicKeyAsSecret("demo1"));
    }

    @Test
    void aTokenWithoutExpiryOrSubjectIsRejected() throws Exception {
        assertRejected("Bearer " + tokens.withoutExpiry("demo1"));
        assertRejected("Bearer " + tokens.withoutSubject());
    }
}

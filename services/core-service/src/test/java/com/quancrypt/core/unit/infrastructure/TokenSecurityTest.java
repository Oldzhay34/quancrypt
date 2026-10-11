package com.quancrypt.core.unit.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.quancrypt.core.infrastructure.security.OperationPolicy;
import com.quancrypt.core.infrastructure.security.OperationPolicy.Scheme;
import com.quancrypt.core.infrastructure.security.TokenAuthenticationFilter;
import com.quancrypt.core.integration.support.OpenApiContract;
import com.quancrypt.core.integration.support.OpenApiContract.Operation;
import jakarta.servlet.FilterChain;
import java.util.ArrayList;
import java.util.EnumSet;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

/** The token filter and the operation policy: weak tokens stop the service, schemes follow the contract, answers are fixed problems. */
class TokenSecurityTest {

    private static final String SESSION = "s".repeat(40);
    private static final String INTERNAL = "i".repeat(40);

    private final OperationPolicy policy = new OperationPolicy();
    private final TokenAuthenticationFilter filter = new TokenAuthenticationFilter(SESSION, INTERNAL, policy);

    /** Runs a request through the filter; returns the authorities seen inside the chain (empty when the chain was not reached). */
    private record Outcome(int status, List<String> authorities, String body) {
    }

    private Outcome run(String method, String uri, String authorization, String internal) throws Exception {
        MockHttpServletRequest request = new MockHttpServletRequest(method, uri);
        if (authorization != null) {
            request.addHeader("Authorization", authorization);
        }
        if (internal != null) {
            request.addHeader("X-Internal-Token", internal);
        }
        MockHttpServletResponse response = new MockHttpServletResponse();
        List<String> seen = new ArrayList<>();
        FilterChain chain = (req, res) -> {
            Authentication auth = SecurityContextHolder.getContext().getAuthentication();
            if (auth != null) {
                auth.getAuthorities().forEach(a -> seen.add(a.getAuthority()));
            }
            seen.add("CHAIN");
        };
        filter.doFilter(request, response, chain);
        return new Outcome(response.getStatus(), seen, response.getContentAsString());
    }

    @Test
    void weakOrPlaceholderTokensStopTheService() {
        for (String weak : new String[] {null, "", "  ", "CHANGE_ME", "short-token", "CHANGE_ME" + "x".repeat(40)}) {
            assertThatThrownBy(() -> new TokenAuthenticationFilter(weak, INTERNAL, policy)).isInstanceOf(IllegalStateException.class)
                    .hasMessageContaining("QUANCRYPT_SESSION_TOKEN").hasMessageNotContaining(INTERNAL);
            assertThatThrownBy(() -> new TokenAuthenticationFilter(SESSION, weak, policy)).isInstanceOf(IllegalStateException.class)
                    .hasMessageContaining("INTERNAL_SERVICE_TOKEN").hasMessageNotContaining(SESSION);
        }
        assertThatThrownBy(() -> new TokenAuthenticationFilter(SESSION, SESSION, policy)).isInstanceOf(IllegalStateException.class)
                .hasMessageNotContaining(SESSION);
    }

    @Test
    void theUiTokenIsTheUiCallerAndTheServiceTokenTheInternalCaller() throws Exception {
        assertThat(run("GET", "/api/v1/projects", "Bearer " + SESSION, null).authorities()).containsExactly("ROLE_UI", "CHAIN");
        assertThat(run("GET", "/api/v1/projects", null, INTERNAL).authorities()).containsExactly("ROLE_INTERNAL", "CHAIN");
        assertThat(SecurityContextHolder.getContext().getAuthentication()).as("context is cleared after the request").isNull();
    }

    @Test
    void missingWrongOrMisplacedTokensAreRefusedWithAFixedProblem() throws Exception {
        UUID id = UUID.randomUUID();
        for (Outcome refused : List.of(
                run("GET", "/api/v1/projects", null, null),
                run("GET", "/api/v1/projects", "Bearer nope", null),
                run("GET", "/api/v1/projects", SESSION, null),
                run("GET", "/api/v1/projects", "Bearer " + INTERNAL, null),
                run("GET", "/api/v1/projects", null, SESSION),
                run("GET", "/api/v1/projects", "Bearer nope", INTERNAL),
                run("DELETE", "/api/v1/projects/" + id, null, INTERNAL))) {
            assertThat(refused.status()).isEqualTo(401);
            assertThat(refused.authorities()).isEmpty();
            assertThat(refused.body()).contains("https://quancrypt.local/problems/unauthorized").doesNotContain(SESSION).doesNotContain(INTERNAL);
        }
        Outcome forbidden = run("POST", "/api/v1/internal/outbox/relay", "Bearer " + SESSION, null);
        assertThat(forbidden.status()).isEqualTo(403);
        assertThat(forbidden.body()).contains("https://quancrypt.local/problems/forbidden");
    }

    @Test
    void healthPathsPassWithoutACredential() throws Exception {
        assertThat(run("GET", "/health/liveness", null, null).authorities()).containsExactly("CHAIN");
        assertThat(run("GET", "/health/readiness", null, null).authorities()).containsExactly("CHAIN");
        assertThat(run("GET", "/health", null, null).status()).isEqualTo(401);
    }

    /** The table of OperationPolicy is the `security` of the contract, operation by operation. */
    @Test
    void thePolicyMatchesTheSecurityOfTheContract() {
        for (Operation op : new OpenApiContract().operations()) {
            Set<Scheme> expected = EnumSet.noneOf(Scheme.class);
            if (op.securitySchemes().contains("bearerAuth")) {
                expected.add(Scheme.BEARER);
            }
            if (op.securitySchemes().contains("internalToken")) {
                expected.add(Scheme.INTERNAL);
            }
            String path = op.path().replaceAll("\\{consentType}", "WAREHOUSE_ANALYTICS").replaceAll("\\{[A-Za-z]+}", UUID.randomUUID().toString());
            assertThat(policy.accepted(op.method(), path)).as(op.id()).isEqualTo(expected);
        }
    }
}

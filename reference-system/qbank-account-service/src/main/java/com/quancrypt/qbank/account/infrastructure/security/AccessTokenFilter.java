package com.quancrypt.qbank.account.infrastructure.security;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletRequestWrapper;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.security.Principal;
import java.time.Duration;
import java.util.Locale;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtException;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * Verifies the Bearer access token: only RS256 signed by this service's key, with a matching key id, a subject and
 * an unexpired exp claim. On success the request's user principal is the token subject; otherwise the response is a
 * 401 problem.
 */
public class AccessTokenFilter extends OncePerRequestFilter {

    private static final String BEARER_PREFIX = "bearer ";
    private static final String UNAUTHORIZED_BODY = "{\"type\":\"https://quancrypt.local/problems/unauthorized\","
            + "\"title\":\"Unauthorized\",\"status\":401,"
            + "\"detail\":\"Missing, invalid or expired credentials.\"}";

    private final NimbusJwtDecoder decoder;

    public AccessTokenFilter(JwtKeyMaterial keys) {
        this.decoder = NimbusJwtDecoder.withPublicKey(keys.publicKey())
                .signatureAlgorithm(SignatureAlgorithm.RS256)
                .build();
        this.decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
                new JwtTimestampValidator(Duration.ZERO),
                requiredClaims(),
                keyIdValidator(keys.keyId())));
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        String subject = verifiedSubject(request.getHeader("Authorization"));
        if (subject == null) {
            response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            response.setContentType("application/problem+json");
            response.setCharacterEncoding("UTF-8");
            response.getWriter().write(UNAUTHORIZED_BODY);
            return;
        }
        chain.doFilter(new AuthenticatedRequest(request, subject), response);
    }

    private String verifiedSubject(String authorization) {
        if (authorization == null || !authorization.toLowerCase(Locale.ROOT).startsWith(BEARER_PREFIX)) {
            return null;
        }
        String token = authorization.substring(BEARER_PREFIX.length()).strip();
        if (token.isEmpty()) {
            return null;
        }
        try {
            return decoder.decode(token).getSubject();
        } catch (JwtException e) {
            return null;
        }
    }

    private static OAuth2TokenValidator<Jwt> requiredClaims() {
        OAuth2Error error = new OAuth2Error("invalid_token", "required claims are missing", null);
        return jwt -> {
            String subject = jwt.getSubject();
            boolean complete = jwt.getExpiresAt() != null && subject != null && !subject.isBlank();
            return complete ? OAuth2TokenValidatorResult.success() : OAuth2TokenValidatorResult.failure(error);
        };
    }

    private static OAuth2TokenValidator<Jwt> keyIdValidator(String expectedKeyId) {
        OAuth2Error error = new OAuth2Error("invalid_token", "unknown key id", null);
        return jwt -> expectedKeyId.equals(jwt.getHeaders().get("kid"))
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(error);
    }

    /** Exposes the verified token subject as the user principal. */
    private static final class AuthenticatedRequest extends HttpServletRequestWrapper {

        private final Principal principal;

        AuthenticatedRequest(HttpServletRequest request, String subject) {
            super(request);
            this.principal = () -> subject;
        }

        @Override
        public Principal getUserPrincipal() {
            return principal;
        }

        @Override
        public String getRemoteUser() {
            return principal.getName();
        }
    }
}

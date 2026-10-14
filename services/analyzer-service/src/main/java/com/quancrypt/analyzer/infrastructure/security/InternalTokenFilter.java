package com.quancrypt.analyzer.infrastructure.security;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.List;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * Authenticates a request by the service token in {@code X-Internal-Token} (guardrails-security, section 6): every
 * operation of the analyzer contract is for service to service calls only. The token is compared in constant time and is
 * never logged or echoed. A weak or placeholder token stops the service at start-up.
 */
public final class InternalTokenFilter extends OncePerRequestFilter {

    static final int MIN_TOKEN_LENGTH = 32;
    static final String PLACEHOLDER = "CHANGE_ME";
    static final String HEADER = "X-Internal-Token";

    private static final String UNAUTHORIZED_BODY = "{\"type\":\"https://quancrypt.local/problems/unauthorized\","
            + "\"title\":\"Unauthorized\",\"status\":401,\"detail\":\"Missing or invalid credentials.\"}";

    private final byte[] tokenDigest;

    public InternalTokenFilter(String internalToken) {
        if (internalToken == null || internalToken.isBlank() || internalToken.contains(PLACEHOLDER)
                || internalToken.length() < MIN_TOKEN_LENGTH) {
            throw new IllegalStateException("INTERNAL_SERVICE_TOKEN must be set to a secret of at least " + MIN_TOKEN_LENGTH + " characters");
        }
        this.tokenDigest = sha256(internalToken);
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        String path = request.getRequestURI();
        return "/health/liveness".equals(path) || "/health/readiness".equals(path);
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        String presented = request.getHeader(HEADER);
        if (presented == null || !MessageDigest.isEqual(sha256(presented), tokenDigest)) {
            response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            response.setContentType("application/problem+json");
            response.setCharacterEncoding("UTF-8");
            response.getWriter().write(UNAUTHORIZED_BODY);
            return;
        }
        SecurityContextHolder.getContext().setAuthentication(
                new UsernamePasswordAuthenticationToken("internal", null, List.of(new SimpleGrantedAuthority("ROLE_INTERNAL"))));
        try {
            chain.doFilter(request, response);
        } finally {
            SecurityContextHolder.clearContext();
        }
    }

    /** Digests are compared, so the time does not depend on where the values differ or on their length. */
    private static byte[] sha256(String value) {
        try {
            return MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 is mandatory in every JDK", e);
        }
    }
}

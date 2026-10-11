package com.quancrypt.core.infrastructure.security;

import com.quancrypt.core.infrastructure.security.OperationPolicy.Scheme;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * Authenticates a request by its token: `Authorization: Bearer` (the UI session token, caller UI) or `X-Internal-Token`
 * (the service token, caller INTERNAL). When an Authorization header is present only it counts; there is no fallback to
 * the internal header. A token the operation does not accept is 401, except that the UI token on an internal-only
 * operation is 403 (D-168). Tokens are compared in constant time and never logged or echoed.
 */
public final class TokenAuthenticationFilter extends OncePerRequestFilter {

    static final int MIN_TOKEN_LENGTH = 32;
    static final String PLACEHOLDER = "CHANGE_ME";
    private static final String BEARER_PREFIX = "Bearer ";

    private static final String UNAUTHORIZED_BODY = "{\"type\":\"https://quancrypt.local/problems/unauthorized\","
            + "\"title\":\"Unauthorized\",\"status\":401,\"detail\":\"Missing or invalid credentials.\"}";
    private static final String FORBIDDEN_BODY = "{\"type\":\"https://quancrypt.local/problems/forbidden\","
            + "\"title\":\"Forbidden\",\"status\":403,\"detail\":\"This operation is for service to service calls only.\"}";

    private final byte[] sessionDigest;
    private final byte[] internalDigest;
    private final OperationPolicy policy;

    public TokenAuthenticationFilter(String sessionToken, String internalToken, OperationPolicy policy) {
        requireStrong("QUANCRYPT_SESSION_TOKEN", sessionToken);
        requireStrong("INTERNAL_SERVICE_TOKEN", internalToken);
        if (sessionToken.equals(internalToken)) {
            throw new IllegalStateException("QUANCRYPT_SESSION_TOKEN and INTERNAL_SERVICE_TOKEN must be different secrets");
        }
        this.sessionDigest = sha256(sessionToken);
        this.internalDigest = sha256(internalToken);
        this.policy = policy;
    }

    private static void requireStrong(String name, String value) {
        if (value == null || value.isBlank() || value.contains(PLACEHOLDER) || value.length() < MIN_TOKEN_LENGTH) {
            throw new IllegalStateException(name + " must be set to a secret of at least " + MIN_TOKEN_LENGTH + " characters");
        }
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        String path = request.getRequestURI();
        return "/health/liveness".equals(path) || "/health/readiness".equals(path);
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        Optional<Scheme> presented = authenticate(request);
        if (presented.isEmpty()) {
            write(response, HttpServletResponse.SC_UNAUTHORIZED, UNAUTHORIZED_BODY);
            return;
        }
        Scheme scheme = presented.get();
        Set<Scheme> accepted = policy.accepted(request.getMethod(), request.getRequestURI());
        if (!accepted.contains(scheme)) {
            boolean uiOnInternalOperation = scheme == Scheme.BEARER && accepted.equals(Set.of(Scheme.INTERNAL));
            write(response, uiOnInternalOperation ? HttpServletResponse.SC_FORBIDDEN : HttpServletResponse.SC_UNAUTHORIZED,
                    uiOnInternalOperation ? FORBIDDEN_BODY : UNAUTHORIZED_BODY);
            return;
        }
        String role = scheme == Scheme.INTERNAL ? "ROLE_INTERNAL" : "ROLE_UI";
        SecurityContextHolder.getContext().setAuthentication(new UsernamePasswordAuthenticationToken(
                scheme == Scheme.INTERNAL ? "internal" : "ui", null, List.of(new SimpleGrantedAuthority(role))));
        try {
            chain.doFilter(request, response);
        } finally {
            SecurityContextHolder.clearContext();
        }
    }

    private Optional<Scheme> authenticate(HttpServletRequest request) {
        String authorization = request.getHeader("Authorization");
        if (authorization != null) {
            if (authorization.startsWith(BEARER_PREFIX) && matches(authorization.substring(BEARER_PREFIX.length()), sessionDigest)) {
                return Optional.of(Scheme.BEARER);
            }
            return Optional.empty();
        }
        String internal = request.getHeader("X-Internal-Token");
        if (internal != null && matches(internal, internalDigest)) {
            return Optional.of(Scheme.INTERNAL);
        }
        return Optional.empty();
    }

    /** Compares the digests of both values, so the comparison time does not depend on where the values differ or on their length. */
    private static boolean matches(String presented, byte[] expectedDigest) {
        return MessageDigest.isEqual(sha256(presented), expectedDigest);
    }

    private static byte[] sha256(String value) {
        try {
            return MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 is mandatory in every JDK", e);
        }
    }

    private static void write(HttpServletResponse response, int status, String body) throws IOException {
        response.setStatus(status);
        response.setContentType("application/problem+json");
        response.setCharacterEncoding("UTF-8");
        response.getWriter().write(body);
    }
}

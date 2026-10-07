package com.quancrypt.qbank.payment.infrastructure.security;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.access.AccessDeniedHandler;

/** Answers authentication and authorization failures of the resource server with fixed problem+json bodies. */
public final class ProblemEntryPoint implements AuthenticationEntryPoint, AccessDeniedHandler {

    private static final String UNAUTHORIZED_BODY = "{\"type\":\"https://quancrypt.local/problems/unauthorized\","
            + "\"title\":\"Unauthorized\",\"status\":401,"
            + "\"detail\":\"Missing, invalid or expired credentials.\"}";
    private static final String FORBIDDEN_BODY = "{\"type\":\"https://quancrypt.local/problems/forbidden\","
            + "\"title\":\"Forbidden\",\"status\":403,"
            + "\"detail\":\"The caller is not allowed to access this resource.\"}";

    @Override
    public void commence(HttpServletRequest request, HttpServletResponse response, AuthenticationException ex)
            throws IOException {
        write(response, HttpServletResponse.SC_UNAUTHORIZED, UNAUTHORIZED_BODY);
    }

    @Override
    public void handle(HttpServletRequest request, HttpServletResponse response, AccessDeniedException ex)
            throws IOException {
        write(response, HttpServletResponse.SC_FORBIDDEN, FORBIDDEN_BODY);
    }

    private static void write(HttpServletResponse response, int status, String body) throws IOException {
        response.setStatus(status);
        response.setContentType("application/problem+json");
        response.setCharacterEncoding("UTF-8");
        response.getWriter().write(body);
    }
}

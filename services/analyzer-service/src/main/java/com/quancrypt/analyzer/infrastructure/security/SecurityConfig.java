package com.quancrypt.analyzer.infrastructure.security;

import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.WebSecurityCustomizer;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.AuthorizationFilter;

/**
 * Stateless token security (guardrails-security section 6): no session, no cookies, so no CSRF protection is needed.
 * Only /health/liveness and /health/readiness are open; every other path needs the service token. There is no CORS
 * configuration: the browser never calls this service, the agent and core services do.
 */
@Configuration(proxyBeanMethods = false)
public class SecurityConfig {

    private static final String REJECTED_BODY = "{\"type\":\"https://quancrypt.local/problems/validation-failed\","
            + "\"title\":\"Validation failed\",\"status\":400,\"detail\":\"the request is not acceptable\"}";

    @Bean
    InternalTokenFilter internalTokenFilter(@Value("${quancrypt.internal-token}") String internalToken) {
        return new InternalTokenFilter(internalToken);
    }

    /** The token filter is added to the security chain only; it must not also be registered as a plain servlet filter. */
    @Bean
    FilterRegistrationBean<InternalTokenFilter> tokenFilterRegistration(InternalTokenFilter filter) {
        FilterRegistrationBean<InternalTokenFilter> registration = new FilterRegistrationBean<>(filter);
        registration.setEnabled(false);
        return registration;
    }

    /** There are no users: this keeps Spring Boot from creating one with a generated password (P3.3 security review). */
    @Bean
    UserDetailsService noUsers() {
        return username -> {
            throw new UsernameNotFoundException("there are no users");
        };
    }

    /** A request the firewall refuses (a semicolon or double slash in the path, say) gets the 400 problem of the contract. */
    @Bean
    WebSecurityCustomizer rejectedRequests() {
        return web -> web.requestRejectedHandler((request, response, rejected) -> write(response));
    }

    private static void write(HttpServletResponse response) throws IOException {
        response.setStatus(HttpServletResponse.SC_BAD_REQUEST);
        response.setContentType("application/problem+json");
        response.setCharacterEncoding("UTF-8");
        response.getWriter().write(REJECTED_BODY);
    }

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http, InternalTokenFilter tokenFilter) throws Exception {
        http.csrf(AbstractHttpConfigurer::disable)
                .sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .httpBasic(AbstractHttpConfigurer::disable)
                .formLogin(AbstractHttpConfigurer::disable)
                .logout(AbstractHttpConfigurer::disable)
                .requestCache(AbstractHttpConfigurer::disable)
                .anonymous(AbstractHttpConfigurer::disable)
                .headers(Customizer.withDefaults())
                .authorizeHttpRequests(requests -> requests
                        .requestMatchers("/health/liveness", "/health/readiness").permitAll()
                        .anyRequest().authenticated())
                .addFilterBefore(tokenFilter, AuthorizationFilter.class);
        return http.build();
    }
}

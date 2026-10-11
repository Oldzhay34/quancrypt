package com.quancrypt.core.infrastructure.security;

import java.util.List;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.AuthorizationFilter;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

/**
 * Stateless token security (guardrails-security section 6): no session, no cookies, so no CSRF protection is needed.
 * Only /health/liveness and /health/readiness are open; every other path needs the UI session token or the service
 * token, as the contract says per operation. CORS allows the UI origin only.
 */
@Configuration(proxyBeanMethods = false)
public class SecurityConfig {

    static final List<String> UI_ORIGINS = List.of("http://127.0.0.1:8080", "http://localhost:8080");

    @Bean
    OperationPolicy operationPolicy() {
        return new OperationPolicy();
    }

    @Bean
    TokenAuthenticationFilter tokenAuthenticationFilter(
            @Value("${quancrypt.session-token}") String sessionToken,
            @Value("${quancrypt.internal-token}") String internalToken,
            OperationPolicy policy) {
        return new TokenAuthenticationFilter(sessionToken, internalToken, policy);
    }

    /** The token filter is added to the security chain only; it must not also be registered as a plain servlet filter. */
    @Bean
    FilterRegistrationBean<TokenAuthenticationFilter> tokenFilterRegistration(TokenAuthenticationFilter filter) {
        FilterRegistrationBean<TokenAuthenticationFilter> registration = new FilterRegistrationBean<>(filter);
        registration.setEnabled(false);
        return registration;
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(UI_ORIGINS);
        cors.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE", "OPTIONS"));
        cors.setAllowedHeaders(List.of("Authorization", "Content-Type", "Idempotency-Key", "If-Match", "X-Trace-Id", "Accept-Language"));
        cors.setExposedHeaders(List.of("X-Trace-Id", "ETag"));
        cors.setAllowCredentials(false);
        cors.setMaxAge(600L);
        UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", cors);
        return source;
    }

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http, TokenAuthenticationFilter tokenFilter,
            @Qualifier("corsConfigurationSource") CorsConfigurationSource corsSource) throws Exception {
        http.csrf(AbstractHttpConfigurer::disable)
                .cors(cors -> cors.configurationSource(corsSource))
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

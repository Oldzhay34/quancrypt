package com.quancrypt.qbank.payment.infrastructure.security;

import org.springframework.boot.security.autoconfigure.actuate.web.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

/**
 * Every request needs a valid Bearer JWT. The service is stateless (no session, so no CSRF protection is needed).
 * Spring Boot's resource server auto-configuration builds the decoder from application.yml (JWKS URI, RS256);
 * infrastructure/config makes its JWKS download use the client certificate.
 */
@Configuration
public class SecurityConfig {

    /**
     * The management server (separate loopback port) answers health probes without credentials; every other
     * actuator endpoint is not exposed at all. The matcher only matches requests of the management server, so the
     * main port stays fully protected by {@link #apiSecurity}.
     */
    @Bean
    @Order(1)
    SecurityFilterChain managementSecurity(HttpSecurity http) throws Exception {
        http.securityMatcher(EndpointRequest.toAnyEndpoint())
                .csrf(AbstractHttpConfigurer::disable)
                .authorizeHttpRequests(requests -> requests.anyRequest().permitAll());
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        ProblemEntryPoint problems = new ProblemEntryPoint();
        http.csrf(AbstractHttpConfigurer::disable)
                .sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .httpBasic(AbstractHttpConfigurer::disable)
                .formLogin(AbstractHttpConfigurer::disable)
                .logout(AbstractHttpConfigurer::disable)
                .requestCache(AbstractHttpConfigurer::disable)
                .authorizeHttpRequests(requests -> requests.anyRequest().authenticated())
                .oauth2ResourceServer(resourceServer -> resourceServer
                        .jwt(Customizer.withDefaults())
                        .authenticationEntryPoint(problems)
                        .accessDeniedHandler(problems));
        return http.build();
    }
}

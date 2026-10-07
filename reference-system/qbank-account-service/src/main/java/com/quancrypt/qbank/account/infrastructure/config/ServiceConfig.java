package com.quancrypt.qbank.account.infrastructure.config;

import com.quancrypt.qbank.account.api.TraceIdFilter;
import com.quancrypt.qbank.account.domain.model.Account;
import com.quancrypt.qbank.account.domain.model.AccountId;
import com.quancrypt.qbank.account.domain.model.PasswordHash;
import com.quancrypt.qbank.account.domain.model.UserCredential;
import com.quancrypt.qbank.account.facade.AccountFacade;
import com.quancrypt.qbank.account.facade.AuthenticationFacade;
import com.quancrypt.qbank.account.facade.JwksFacade;
import com.quancrypt.qbank.account.infrastructure.persistence.InMemoryAccountRepository;
import com.quancrypt.qbank.account.infrastructure.persistence.InMemoryCredentialRepository;
import com.quancrypt.qbank.account.infrastructure.security.AccessTokenFilter;
import com.quancrypt.qbank.account.infrastructure.security.BcryptPasswordVerifier;
import com.quancrypt.qbank.account.infrastructure.security.JwtKeyMaterial;
import com.quancrypt.qbank.account.infrastructure.security.NimbusTokenIssuer;
import com.quancrypt.qbank.account.infrastructure.security.RsaVerificationKeySource;
import com.quancrypt.qbank.account.infrastructure.time.SystemClock;
import com.quancrypt.qbank.account.port.inbound.AuthenticateUserUseCase;
import com.quancrypt.qbank.account.port.inbound.GetAccountUseCase;
import com.quancrypt.qbank.account.port.inbound.GetJwksUseCase;
import com.quancrypt.qbank.account.port.outbound.AccountRepository;
import com.quancrypt.qbank.account.port.outbound.Clock;
import com.quancrypt.qbank.account.port.outbound.CredentialRepository;
import com.quancrypt.qbank.account.port.outbound.PasswordVerifier;
import com.quancrypt.qbank.account.port.outbound.TokenIssuer;
import com.quancrypt.qbank.account.port.outbound.VerificationKeySource;
import com.quancrypt.qbank.account.usecase.AuthenticateUserService;
import com.quancrypt.qbank.account.usecase.GetAccountService;
import com.quancrypt.qbank.account.usecase.GetJwksService;
import java.time.Duration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;

/** Composition root: the only place that creates and wires the concrete classes. */
@Configuration
@EnableConfigurationProperties({QbankProperties.class, DemoDataProperties.class})
public class ServiceConfig {

    private static final String SIGNING_KEY_NAME = "jwt-signing";

    @Bean
    Clock clock() {
        return new SystemClock();
    }

    @Bean
    JwtKeyMaterial jwtKeyMaterial(QbankProperties properties) {
        return JwtKeyMaterial.load(
                properties.certsPath().resolve(SIGNING_KEY_NAME + ".key.pem"),
                properties.certsPath().resolve(SIGNING_KEY_NAME + ".pub.pem"));
    }

    @Bean
    TokenIssuer tokenIssuer(JwtKeyMaterial keys) {
        return new NimbusTokenIssuer(keys);
    }

    @Bean
    VerificationKeySource verificationKeySource(JwtKeyMaterial keys) {
        return new RsaVerificationKeySource(keys);
    }

    @Bean
    PasswordVerifier passwordVerifier() {
        return new BcryptPasswordVerifier();
    }

    @Bean
    AccountRepository accountRepository(DemoDataProperties demo) {
        return new InMemoryAccountRepository(demo.accounts().stream()
                .map(a -> new Account(new AccountId(a.accountId()), a.ownerName(), a.currency(), a.balance()))
                .toList());
    }

    @Bean
    CredentialRepository credentialRepository(DemoDataProperties demo) {
        return new InMemoryCredentialRepository(demo.users().stream()
                .map(u -> new UserCredential(u.username(), new PasswordHash(u.passwordHash()), new AccountId(u.accountId())))
                .toList());
    }

    @Bean
    AuthenticateUserUseCase authenticateUserUseCase(
            CredentialRepository credentials,
            PasswordVerifier passwordVerifier,
            TokenIssuer tokenIssuer,
            Clock clock,
            QbankProperties properties) {
        return new AuthenticateUserService(
                credentials, passwordVerifier, tokenIssuer, clock, Duration.ofSeconds(properties.jwt().ttlSeconds()));
    }

    @Bean
    GetAccountUseCase getAccountUseCase(AccountRepository accounts, CredentialRepository credentials) {
        return new GetAccountService(accounts, credentials);
    }

    @Bean
    GetJwksUseCase getJwksUseCase(VerificationKeySource keySource) {
        return new GetJwksService(keySource);
    }

    @Bean
    AuthenticationFacade authenticationFacade(AuthenticateUserUseCase useCase) {
        return new AuthenticationFacade(useCase);
    }

    @Bean
    AccountFacade accountFacade(GetAccountUseCase useCase) {
        return new AccountFacade(useCase);
    }

    @Bean
    JwksFacade jwksFacade(GetJwksUseCase useCase) {
        return new JwksFacade(useCase);
    }

    @Bean
    FilterRegistrationBean<TraceIdFilter> traceIdFilter() {
        FilterRegistrationBean<TraceIdFilter> registration = new FilterRegistrationBean<>(new TraceIdFilter());
        registration.setOrder(Ordered.HIGHEST_PRECEDENCE);
        return registration;
    }

    @Bean
    FilterRegistrationBean<AccessTokenFilter> accessTokenFilter(JwtKeyMaterial keys) {
        FilterRegistrationBean<AccessTokenFilter> registration = new FilterRegistrationBean<>(new AccessTokenFilter(keys));
        registration.addUrlPatterns("/api/v1/accounts", "/api/v1/accounts/*");
        registration.setOrder(Ordered.HIGHEST_PRECEDENCE + 10);
        return registration;
    }
}

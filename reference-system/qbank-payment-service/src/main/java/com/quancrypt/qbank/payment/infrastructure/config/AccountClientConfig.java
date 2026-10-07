package com.quancrypt.qbank.payment.infrastructure.config;

import com.quancrypt.qbank.payment.infrastructure.client.RestClientAccountDirectory;
import com.quancrypt.qbank.payment.port.outbound.AccountDirectory;
import com.quancrypt.qbank.payment.port.outbound.AccountLookupException;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.retry.Retry;
import io.github.resilience4j.retry.RetryConfig;
import java.net.http.HttpClient;
import java.time.Duration;
import org.springframework.boot.security.oauth2.server.resource.autoconfigure.servlet.JwkSetUriJwtDecoderBuilderCustomizer;
import org.springframework.boot.ssl.SslBundles;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestTemplate;

/**
 * Everything that talks to the account service over mutual TLS: the RestClient behind AccountDirectory and the
 * download of the account service's JWKS for JWT validation. Both present the payment-to-account client certificate
 * (SSL bundle "accountclient") and trust only the demo CA.
 */
@Configuration
public class AccountClientConfig {

    private static final String BUNDLE = "accountclient";

    @Bean
    AccountDirectory accountDirectory(QbankProperties properties, SslBundles sslBundles) {
        RestClient client = RestClient.builder()
                .baseUrl(properties.accountServiceUrl())
                .requestFactory(requestFactory(properties, sslBundles))
                .build();
        return new RestClientAccountDirectory(client, circuitBreaker(), retry());
    }

    /**
     * The JWKS download of Spring Boot's resource server decoder (spring.security.oauth2.resourceserver.jwt.jwk-set-uri
     * and jws-algorithms: RS256, see application.yml) must present the client certificate too.
     */
    @Bean
    JwkSetUriJwtDecoderBuilderCustomizer jwksOverMutualTls(QbankProperties properties, SslBundles sslBundles) {
        JdkClientHttpRequestFactory requests = requestFactory(properties, sslBundles);
        return builder -> builder.restOperations(new RestTemplate(requests));
    }

    /** Tokens need a subject and an expiry; Boot adds this validator to the default timestamp validation. */
    @Bean
    OAuth2TokenValidator<Jwt> requiredClaimsValidator() {
        OAuth2Error error = new OAuth2Error("invalid_token", "required claims are missing", null);
        return jwt -> {
            String subject = jwt.getSubject();
            boolean complete = jwt.getExpiresAt() != null && subject != null && !subject.isBlank();
            return complete ? OAuth2TokenValidatorResult.success() : OAuth2TokenValidatorResult.failure(error);
        };
    }

    private static JdkClientHttpRequestFactory requestFactory(QbankProperties properties, SslBundles sslBundles) {
        QbankProperties.AccountClient timeouts = properties.accountClient();
        HttpClient httpClient = HttpClient.newBuilder()
                .sslContext(sslBundles.getBundle(BUNDLE).createSslContext())
                .connectTimeout(Duration.ofMillis(timeouts.connectTimeoutMs()))
                .build();
        JdkClientHttpRequestFactory requests = new JdkClientHttpRequestFactory(httpClient);
        requests.setReadTimeout(Duration.ofMillis(timeouts.readTimeoutMs()));
        return requests;
    }

    /** Opens after a majority of recent calls failed technically; business answers (404, 403, 401) never count. */
    static CircuitBreaker circuitBreaker() {
        CircuitBreakerConfig config = CircuitBreakerConfig.custom()
                .slidingWindowSize(10)
                .minimumNumberOfCalls(5)
                .failureRateThreshold(50)
                .waitDurationInOpenState(Duration.ofSeconds(10))
                .recordExceptions(RestClientAccountDirectory.TransientUpstreamException.class)
                .ignoreExceptions(AccountLookupException.class)
                .build();
        return CircuitBreaker.of("account-directory", config);
    }

    /** One retry after a technical failure; the lookup is a GET and therefore safe to repeat. */
    static Retry retry() {
        RetryConfig config = RetryConfig.custom()
                .maxAttempts(2)
                .waitDuration(Duration.ofMillis(200))
                .retryExceptions(RestClientAccountDirectory.TransientUpstreamException.class)
                .build();
        return Retry.of("account-directory", config);
    }
}

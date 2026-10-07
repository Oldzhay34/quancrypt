package com.quancrypt.qbank.payment.infrastructure.client;

import com.quancrypt.qbank.payment.domain.model.AccountId;
import com.quancrypt.qbank.payment.domain.model.AccountSummary;
import com.quancrypt.qbank.payment.domain.model.Caller;
import com.quancrypt.qbank.payment.port.outbound.AccountDirectory;
import com.quancrypt.qbank.payment.port.outbound.AccountLookupException;
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.retry.Retry;
import java.io.IOException;
import java.util.Objects;
import java.util.function.Supplier;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.client.ClientHttpResponse;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/**
 * Looks accounts up in the account service with a RestClient that presents the payment-to-account client
 * certificate (mTLS) and forwards the caller's bearer token, so the account service decides ownership (D-101).
 * Timeouts are set on the RestClient; a retry and a circuit breaker wrap the call (hexagonal-service, section 6).
 */
public final class RestClientAccountDirectory implements AccountDirectory {

    private static final Logger LOG = LoggerFactory.getLogger(RestClientAccountDirectory.class);
    private static final String TRACE_ID_KEY = "traceId";
    private static final String TRACE_ID_HEADER = "X-Trace-Id";

    /** A failure worth retrying and worth counting against the circuit breaker. */
    public static final class TransientUpstreamException extends RuntimeException {

        private static final long serialVersionUID = 1L;

        TransientUpstreamException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    private final RestClient client;
    private final CircuitBreaker breaker;
    private final Retry retry;
    private final JsonMapper json = JsonMapper.builder().build();

    public RestClientAccountDirectory(RestClient client, CircuitBreaker breaker, Retry retry) {
        this.client = Objects.requireNonNull(client, "client");
        this.breaker = Objects.requireNonNull(breaker, "breaker");
        this.retry = Objects.requireNonNull(retry, "retry");
    }

    @Override
    public AccountSummary findAccount(AccountId accountId, Caller caller) {
        Supplier<AccountSummary> call = () -> fetch(accountId, caller);
        Supplier<AccountSummary> guarded = Retry.decorateSupplier(retry, CircuitBreaker.decorateSupplier(breaker, call));
        try {
            return guarded.get();
        } catch (CallNotPermittedException e) {
            LOG.warn("account lookup refused: circuit breaker is open");
            throw new AccountLookupException(AccountLookupException.Reason.UNAVAILABLE);
        } catch (TransientUpstreamException e) {
            LOG.warn("account lookup failed after retries: {}", e.getMessage());
            throw new AccountLookupException(AccountLookupException.Reason.UNAVAILABLE);
        }
    }

    private AccountSummary fetch(AccountId accountId, Caller caller) {
        String traceId = MDC.get(TRACE_ID_KEY);
        try {
            return client.get()
                    .uri("/api/v1/accounts/{accountId}", accountId.value())
                    .header(HttpHeaders.AUTHORIZATION, "Bearer " + caller.bearerToken())
                    .headers(headers -> {
                        if (traceId != null) {
                            headers.set(TRACE_ID_HEADER, traceId);
                        }
                    })
                    .exchange((request, response) -> interpret(response));
        } catch (RestClientException e) {
            throw new TransientUpstreamException("the account service could not be reached", e);
        }
    }

    private AccountSummary interpret(ClientHttpResponse response) throws IOException {
        HttpStatusCode status = response.getStatusCode();
        if (status.value() == 200) {
            return parse(response);
        }
        switch (status.value()) {
            case 404 -> throw new AccountLookupException(AccountLookupException.Reason.NOT_FOUND);
            case 403 -> throw new AccountLookupException(AccountLookupException.Reason.FORBIDDEN);
            case 401 -> throw new AccountLookupException(AccountLookupException.Reason.UNAUTHORIZED);
            default -> {
                if (status.is4xxClientError()) {
                    // A request the account service refuses is no outage: no retry, no circuit breaker failure (D-106).
                    LOG.warn("account lookup refused by the account service status={}", status.value());
                    throw new AccountLookupException(AccountLookupException.Reason.UNAVAILABLE);
                }
                throw new TransientUpstreamException(
                        "the account service answered with status " + status.value(), null);
            }
        }
    }

    private AccountSummary parse(ClientHttpResponse response) throws IOException {
        try {
            JsonNode body = json.readTree(response.getBody());
            return new AccountSummary(
                    new AccountId(body.get("accountId").asString()), body.get("currency").asString());
        } catch (RuntimeException e) {
            throw new TransientUpstreamException("the account service sent an unreadable answer", e);
        }
    }
}

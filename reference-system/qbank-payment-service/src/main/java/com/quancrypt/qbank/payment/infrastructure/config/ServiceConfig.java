package com.quancrypt.qbank.payment.infrastructure.config;

import com.quancrypt.qbank.payment.api.TraceIdFilter;
import com.quancrypt.qbank.payment.facade.PaymentFacade;
import com.quancrypt.qbank.payment.facade.TerminalTransactionFacade;
import com.quancrypt.qbank.payment.infrastructure.crypto.RsaOaepCardTokenizer;
import com.quancrypt.qbank.payment.infrastructure.crypto.Sha1WithRsaReceiptSigner;
import com.quancrypt.qbank.payment.infrastructure.persistence.InMemoryIdempotencyStore;
import com.quancrypt.qbank.payment.infrastructure.persistence.InMemoryPaymentRepository;
import com.quancrypt.qbank.payment.infrastructure.persistence.InMemoryTerminalTransactionRepository;
import com.quancrypt.qbank.payment.infrastructure.time.SystemClock;
import com.quancrypt.qbank.payment.infrastructure.time.UuidIdGenerator;
import com.quancrypt.qbank.payment.port.inbound.CreatePaymentUseCase;
import com.quancrypt.qbank.payment.port.inbound.GetPaymentUseCase;
import com.quancrypt.qbank.payment.port.inbound.IssueReceiptUseCase;
import com.quancrypt.qbank.payment.port.inbound.RecordTerminalTransactionUseCase;
import com.quancrypt.qbank.payment.port.outbound.AccountDirectory;
import com.quancrypt.qbank.payment.port.outbound.CardTokenizer;
import com.quancrypt.qbank.payment.port.outbound.Clock;
import com.quancrypt.qbank.payment.port.outbound.IdGenerator;
import com.quancrypt.qbank.payment.port.outbound.IdempotencyStore;
import com.quancrypt.qbank.payment.port.outbound.PaymentRepository;
import com.quancrypt.qbank.payment.port.outbound.ReceiptSigner;
import com.quancrypt.qbank.payment.port.outbound.TerminalTransactionRepository;
import com.quancrypt.qbank.payment.usecase.CreatePaymentService;
import com.quancrypt.qbank.payment.usecase.GetPaymentService;
import com.quancrypt.qbank.payment.usecase.IssueReceiptService;
import com.quancrypt.qbank.payment.usecase.RecordTerminalTransactionService;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;

/** Composition root: the only place that creates and wires the concrete classes. */
@Configuration
@EnableConfigurationProperties(QbankProperties.class)
public class ServiceConfig {

    @Bean
    Clock clock() {
        return new SystemClock();
    }

    @Bean
    IdGenerator idGenerator() {
        return new UuidIdGenerator();
    }

    @Bean
    PaymentRepository paymentRepository() {
        return new InMemoryPaymentRepository();
    }

    @Bean
    TerminalTransactionRepository terminalTransactionRepository() {
        return new InMemoryTerminalTransactionRepository();
    }

    @Bean
    IdempotencyStore idempotencyStore() {
        return new InMemoryIdempotencyStore();
    }

    /** Tokenizes with the public card token key only; the matching private key is never loaded (D-97). */
    @Bean
    CardTokenizer cardTokenizer(QbankProperties properties) {
        return RsaOaepCardTokenizer.fromPemFile(properties.certsPath().resolve("card-token.pub.pem"));
    }

    @Bean
    ReceiptSigner receiptSigner(QbankProperties properties) {
        return Sha1WithRsaReceiptSigner.fromPemFiles(
                properties.certsPath().resolve("receipt-signing.pub.pem"),
                properties.certsPath().resolve("receipt-signing.key.pem"));
    }

    @Bean
    CreatePaymentUseCase createPaymentUseCase(
            AccountDirectory accounts,
            CardTokenizer tokenizer,
            PaymentRepository payments,
            IdempotencyStore idempotency,
            IdGenerator ids,
            Clock clock) {
        return new CreatePaymentService(accounts, tokenizer, payments, idempotency, ids, clock);
    }

    @Bean
    GetPaymentUseCase getPaymentUseCase(PaymentRepository payments) {
        return new GetPaymentService(payments);
    }

    @Bean
    IssueReceiptUseCase issueReceiptUseCase(
            PaymentRepository payments, ReceiptSigner signer, IdempotencyStore idempotency, Clock clock) {
        return new IssueReceiptService(payments, signer, idempotency, clock);
    }

    @Bean
    RecordTerminalTransactionUseCase recordTerminalTransactionUseCase(TerminalTransactionRepository transactions) {
        return new RecordTerminalTransactionService(transactions);
    }

    @Bean
    PaymentFacade paymentFacade(CreatePaymentUseCase create, GetPaymentUseCase get, IssueReceiptUseCase receipt) {
        return new PaymentFacade(create, get, receipt);
    }

    @Bean
    TerminalTransactionFacade terminalTransactionFacade(RecordTerminalTransactionUseCase useCase) {
        return new TerminalTransactionFacade(useCase);
    }

    @Bean
    FilterRegistrationBean<TraceIdFilter> traceIdFilter() {
        FilterRegistrationBean<TraceIdFilter> registration = new FilterRegistrationBean<>(new TraceIdFilter());
        registration.setOrder(Ordered.HIGHEST_PRECEDENCE);
        return registration;
    }
}

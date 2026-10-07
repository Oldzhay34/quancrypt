package com.quancrypt.qbank.payment.api.controller;

import com.quancrypt.qbank.payment.api.dto.CreatePaymentRequest;
import com.quancrypt.qbank.payment.api.dto.PaymentResponse;
import com.quancrypt.qbank.payment.api.dto.ReceiptBody;
import com.quancrypt.qbank.payment.api.dto.SignedReceiptResponse;
import com.quancrypt.qbank.payment.facade.PaymentFacade;
import com.quancrypt.qbank.payment.facade.dto.CallerView;
import com.quancrypt.qbank.payment.facade.dto.NewPaymentView;
import com.quancrypt.qbank.payment.facade.dto.PaymentView;
import com.quancrypt.qbank.payment.facade.dto.ReceiptView;
import com.quancrypt.qbank.payment.facade.dto.SignedReceiptView;
import com.quancrypt.qbank.payment.facade.error.BadRequestException;
import java.util.regex.Pattern;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

/** The payment endpoints of the contract. The caller is the verified JWT; its token is forwarded for ownership. */
@RestController
public class PaymentController {

    private static final int MAX_IDEMPOTENCY_KEY_LENGTH = 128;
    private static final Pattern ACCOUNT_ID = Pattern.compile("[A-Za-z0-9._-]{1,64}");
    private static final Pattern AMOUNT = Pattern.compile("[0-9]+\\.[0-9]{2}");
    private static final Pattern CURRENCY = Pattern.compile("[A-Z]{3}");
    private static final Pattern CARD_NUMBER = Pattern.compile("[0-9]{13,19}");

    private final PaymentFacade facade;

    public PaymentController(PaymentFacade facade) {
        this.facade = facade;
    }

    @PostMapping("/api/v1/payments")
    @ResponseStatus(HttpStatus.CREATED)
    public PaymentResponse create(
            @AuthenticationPrincipal Jwt jwt,
            @RequestHeader(name = "Idempotency-Key", required = false) String idempotencyKey,
            @RequestBody(required = false) CreatePaymentRequest request) {
        validate(request);
        validateKey(idempotencyKey);
        PaymentView view = facade.createPayment(
                caller(jwt), idempotencyKey,
                new NewPaymentView(request.accountId(), request.amount(), request.currency(), request.cardNumber()));
        return new PaymentResponse(view.paymentId(), view.accountId(), view.amount(), view.currency(), view.createdAt());
    }

    @GetMapping("/api/v1/payments/{paymentId}")
    public PaymentResponse get(@PathVariable String paymentId) {
        PaymentView view = facade.getPayment(paymentId);
        return new PaymentResponse(view.paymentId(), view.accountId(), view.amount(), view.currency(), view.createdAt());
    }

    @PostMapping("/api/v1/payments/{paymentId}/receipt")
    public SignedReceiptResponse issueReceipt(
            @AuthenticationPrincipal Jwt jwt,
            @RequestHeader(name = "Idempotency-Key", required = false) String idempotencyKey,
            @PathVariable String paymentId) {
        validateKey(idempotencyKey);
        SignedReceiptView view = facade.issueReceipt(caller(jwt), idempotencyKey, paymentId);
        ReceiptView receipt = view.receipt();
        return new SignedReceiptResponse(
                view.paymentId(),
                new ReceiptBody(
                        receipt.paymentId(), receipt.accountId(), receipt.amount(), receipt.currency(), receipt.issuedAt()),
                view.signature(),
                view.algorithm(),
                view.keyId());
    }

    private static CallerView caller(Jwt jwt) {
        return new CallerView(jwt.getSubject(), jwt.getTokenValue());
    }

    private static void validate(CreatePaymentRequest request) {
        if (request == null
                || request.accountId() == null || !ACCOUNT_ID.matcher(request.accountId()).matches()
                || request.amount() == null || !AMOUNT.matcher(request.amount()).matches()
                || request.currency() == null || !CURRENCY.matcher(request.currency()).matches()
                || request.cardNumber() == null || !CARD_NUMBER.matcher(request.cardNumber()).matches()) {
            throw new BadRequestException("the payment request is malformed");
        }
    }

    private static void validateKey(String idempotencyKey) {
        if (idempotencyKey != null && (idempotencyKey.isEmpty() || idempotencyKey.length() > MAX_IDEMPOTENCY_KEY_LENGTH)) {
            throw new BadRequestException("the idempotency key must be 1 to 128 characters");
        }
    }
}

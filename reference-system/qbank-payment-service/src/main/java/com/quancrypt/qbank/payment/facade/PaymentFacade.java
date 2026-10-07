package com.quancrypt.qbank.payment.facade;

import com.quancrypt.qbank.payment.facade.dto.CallerView;
import com.quancrypt.qbank.payment.facade.dto.NewPaymentView;
import com.quancrypt.qbank.payment.facade.dto.PaymentView;
import com.quancrypt.qbank.payment.facade.dto.ReceiptView;
import com.quancrypt.qbank.payment.facade.dto.SignedReceiptView;
import com.quancrypt.qbank.payment.facade.error.BadRequestException;
import com.quancrypt.qbank.payment.facade.error.ConflictException;
import com.quancrypt.qbank.payment.facade.error.ForbiddenException;
import com.quancrypt.qbank.payment.facade.error.ResourceNotFoundException;
import com.quancrypt.qbank.payment.facade.error.ServiceUnavailableException;
import com.quancrypt.qbank.payment.facade.error.UnauthorizedException;
import com.quancrypt.qbank.payment.port.inbound.AccountAccessDeniedException;
import com.quancrypt.qbank.payment.port.inbound.AccountNotFoundException;
import com.quancrypt.qbank.payment.port.inbound.CallerNotAuthenticatedException;
import com.quancrypt.qbank.payment.port.inbound.CreatePaymentCommand;
import com.quancrypt.qbank.payment.port.inbound.CreatePaymentUseCase;
import com.quancrypt.qbank.payment.port.inbound.GetPaymentUseCase;
import com.quancrypt.qbank.payment.port.inbound.IdempotencyConflictException;
import com.quancrypt.qbank.payment.port.inbound.InvalidRequestException;
import com.quancrypt.qbank.payment.port.inbound.IssueReceiptCommand;
import com.quancrypt.qbank.payment.port.inbound.IssueReceiptUseCase;
import com.quancrypt.qbank.payment.port.inbound.PaymentNotFoundException;
import com.quancrypt.qbank.payment.port.inbound.PaymentResult;
import com.quancrypt.qbank.payment.port.inbound.SignedReceiptResult;
import com.quancrypt.qbank.payment.port.inbound.UpstreamUnavailableException;
import java.math.BigDecimal;
import java.util.Objects;
import java.util.UUID;

/** Entry point of the api layer for payments and receipts. */
public final class PaymentFacade {

    private final CreatePaymentUseCase createPayment;
    private final GetPaymentUseCase getPayment;
    private final IssueReceiptUseCase issueReceipt;

    public PaymentFacade(
            CreatePaymentUseCase createPayment, GetPaymentUseCase getPayment, IssueReceiptUseCase issueReceipt) {
        this.createPayment = Objects.requireNonNull(createPayment, "createPayment");
        this.getPayment = Objects.requireNonNull(getPayment, "getPayment");
        this.issueReceipt = Objects.requireNonNull(issueReceipt, "issueReceipt");
    }

    /**
     * Creates a payment on behalf of the caller.
     *
     * @throws BadRequestException when the request is malformed
     * @throws UnauthorizedException when the account service rejects the caller's token
     * @throws ForbiddenException when the account does not belong to the caller
     * @throws ResourceNotFoundException when the account does not exist
     * @throws ConflictException when the idempotency key was used with a different request
     * @throws ServiceUnavailableException when the account service is unavailable
     */
    public PaymentView createPayment(CallerView caller, String idempotencyKey, NewPaymentView payment) {
        BigDecimal amount = parseAmount(payment.amount());
        try {
            PaymentResult result = createPayment.create(new CreatePaymentCommand(
                    caller.username(), caller.bearerToken(), idempotencyKey, payment.accountId(), amount,
                    payment.currency(), payment.cardNumber()));
            return toView(result);
        } catch (InvalidRequestException e) {
            throw new BadRequestException(e.getMessage());
        } catch (CallerNotAuthenticatedException e) {
            throw new UnauthorizedException();
        } catch (AccountAccessDeniedException e) {
            throw new ForbiddenException();
        } catch (AccountNotFoundException e) {
            throw new ResourceNotFoundException();
        } catch (IdempotencyConflictException e) {
            throw new ConflictException();
        } catch (UpstreamUnavailableException e) {
            throw new ServiceUnavailableException();
        }
    }

    /**
     * Returns a payment. An id that is not a UUID cannot name an existing payment and is reported as not found.
     *
     * @throws ResourceNotFoundException when the payment does not exist
     */
    public PaymentView getPayment(String paymentId) {
        try {
            return toView(getPayment.get(parseId(paymentId)));
        } catch (PaymentNotFoundException e) {
            throw new ResourceNotFoundException();
        }
    }

    /**
     * Issues a signed receipt.
     *
     * @throws ResourceNotFoundException when the payment does not exist
     * @throws ConflictException when the idempotency key was used with a different request
     */
    public SignedReceiptView issueReceipt(CallerView caller, String idempotencyKey, String paymentId) {
        try {
            SignedReceiptResult result = issueReceipt.issue(
                    new IssueReceiptCommand(caller.username(), idempotencyKey, parseId(paymentId)));
            SignedReceiptResult.ReceiptData receipt = result.receipt();
            return new SignedReceiptView(
                    result.paymentId().toString(),
                    new ReceiptView(
                            receipt.paymentId().toString(), receipt.accountId(), receipt.amount().toPlainString(),
                            receipt.currency(), receipt.issuedAt().toString()),
                    result.signature(),
                    result.algorithm(),
                    result.keyId());
        } catch (InvalidRequestException e) {
            throw new BadRequestException(e.getMessage());
        } catch (PaymentNotFoundException e) {
            throw new ResourceNotFoundException();
        } catch (IdempotencyConflictException e) {
            throw new ConflictException();
        }
    }

    private static BigDecimal parseAmount(String amount) {
        if (amount == null) {
            throw new BadRequestException("amount is required");
        }
        try {
            return new BigDecimal(amount);
        } catch (NumberFormatException e) {
            throw new BadRequestException("amount is not a decimal number");
        }
    }

    private static UUID parseId(String paymentId) {
        if (paymentId == null) {
            throw new ResourceNotFoundException();
        }
        try {
            return UUID.fromString(paymentId);
        } catch (IllegalArgumentException e) {
            throw new ResourceNotFoundException();
        }
    }

    private static PaymentView toView(PaymentResult result) {
        return new PaymentView(
                result.paymentId().toString(), result.accountId(), result.amount().toPlainString(), result.currency(),
                result.createdAt().toString());
    }
}

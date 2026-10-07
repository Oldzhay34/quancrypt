package com.quancrypt.qbank.account.api.error;

import com.quancrypt.qbank.account.facade.error.BadRequestException;
import com.quancrypt.qbank.account.facade.error.ForbiddenException;
import com.quancrypt.qbank.account.facade.error.ResourceNotFoundException;
import com.quancrypt.qbank.account.facade.error.UnauthorizedException;
import java.net.URI;
import org.jspecify.annotations.Nullable;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

/**
 * Renders every error as RFC 9457 problem details. Titles and details are fixed texts: request values are never
 * reflected into the response.
 */
@RestControllerAdvice
public class ProblemAdvice extends ResponseEntityExceptionHandler {

    private static final Logger LOG = LoggerFactory.getLogger(ProblemAdvice.class);

    @ExceptionHandler(BadRequestException.class)
    ResponseEntity<Object> badRequest(BadRequestException ex, WebRequest request) {
        return respond(ex, HttpStatus.BAD_REQUEST, request);
    }

    @ExceptionHandler(UnauthorizedException.class)
    ResponseEntity<Object> unauthorized(UnauthorizedException ex, WebRequest request) {
        return respond(ex, HttpStatus.UNAUTHORIZED, request);
    }

    @ExceptionHandler(ForbiddenException.class)
    ResponseEntity<Object> forbidden(ForbiddenException ex, WebRequest request) {
        return respond(ex, HttpStatus.FORBIDDEN, request);
    }

    @ExceptionHandler(ResourceNotFoundException.class)
    ResponseEntity<Object> notFound(ResourceNotFoundException ex, WebRequest request) {
        return respond(ex, HttpStatus.NOT_FOUND, request);
    }

    @ExceptionHandler(Exception.class)
    ResponseEntity<Object> unexpected(Exception ex, WebRequest request) {
        LOG.error("unhandled exception", ex);
        return respond(ex, HttpStatus.INTERNAL_SERVER_ERROR, request);
    }

    @Override
    protected ResponseEntity<Object> handleExceptionInternal(
            Exception ex, @Nullable Object body, HttpHeaders headers, HttpStatusCode statusCode, WebRequest request) {
        ProblemDetail problem = ProblemDetail.forStatus(statusCode);
        ProblemKind kind = ProblemKind.of(statusCode);
        problem.setType(URI.create(ProblemKind.TYPE_BASE + kind.code()));
        problem.setTitle(kind.title());
        problem.setDetail(kind.detail());
        HttpHeaders responseHeaders = new HttpHeaders();
        responseHeaders.putAll(headers);
        responseHeaders.setContentType(MediaType.APPLICATION_PROBLEM_JSON);
        return new ResponseEntity<>(problem, responseHeaders, statusCode);
    }

    private ResponseEntity<Object> respond(Exception ex, HttpStatus status, WebRequest request) {
        return handleExceptionInternal(ex, null, new HttpHeaders(), status, request);
    }
}

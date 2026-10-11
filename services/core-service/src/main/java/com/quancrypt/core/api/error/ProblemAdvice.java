package com.quancrypt.core.api.error;

import com.quancrypt.core.facade.error.ApiProblemException;
import com.quancrypt.core.facade.error.ProblemKind;
import jakarta.validation.ConstraintViolationException;
import java.net.URI;
import java.util.stream.Collectors;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.HttpMediaTypeNotAcceptableException;
import org.springframework.web.HttpMediaTypeNotSupportedException;
import org.springframework.web.HttpRequestMethodNotSupportedException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.MissingRequestHeaderException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.web.servlet.resource.NoResourceFoundException;

/**
 * Renders every failure as RFC 9457 problem details with the problem types of the contract. Details are fixed sentences,
 * use case sentences or field names; request values are never reflected, and unexpected failures show nothing but
 * "internal error" (the log gets the class name only).
 */
@RestControllerAdvice
public class ProblemAdvice {

    private static final Logger LOG = LoggerFactory.getLogger(ProblemAdvice.class);

    @ExceptionHandler(ApiProblemException.class)
    ResponseEntity<ProblemDetail> problem(ApiProblemException e) {
        return respond(e.kind(), e.getMessage());
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ProblemDetail> invalidBody(MethodArgumentNotValidException e) {
        String fields = e.getBindingResult().getFieldErrors().stream().map(f -> f.getField()).distinct().sorted().collect(Collectors.joining(", "));
        return respond(ProblemKind.VALIDATION_FAILED, "the request body is invalid: " + (fields.isEmpty() ? "see the contract" : fields));
    }

    @ExceptionHandler({HandlerMethodValidationException.class, ConstraintViolationException.class})
    ResponseEntity<ProblemDetail> invalidParameter(Exception e) {
        return respond(ProblemKind.VALIDATION_FAILED, "a request parameter or header is invalid");
    }

    @ExceptionHandler({HttpMessageNotReadableException.class, MissingServletRequestParameterException.class,
        MissingRequestHeaderException.class, HttpMediaTypeNotAcceptableException.class})
    ResponseEntity<ProblemDetail> unreadable(Exception e) {
        return respond(ProblemKind.VALIDATION_FAILED, "the request is malformed: check the JSON, the required parameters and the contract");
    }

    /** A path variable that is not a UUID names nothing (404, D-145b); a bad query parameter is a 400. */
    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    ResponseEntity<ProblemDetail> typeMismatch(MethodArgumentTypeMismatchException e) {
        boolean pathVariable = e.getParameter().hasParameterAnnotation(org.springframework.web.bind.annotation.PathVariable.class);
        return pathVariable ? respond(ProblemKind.NOT_FOUND, "the resource was not found")
                : respond(ProblemKind.VALIDATION_FAILED, "a request parameter has the wrong type");
    }

    /**
     * Only the artifact upload declares 415 in the contract, and its content type is judged by the use case; a JSON body
     * sent with another content type is a malformed request (400) for every other operation.
     */
    @ExceptionHandler(HttpMediaTypeNotSupportedException.class)
    ResponseEntity<ProblemDetail> mediaType(HttpMediaTypeNotSupportedException e) {
        return respond(ProblemKind.VALIDATION_FAILED, "the request body must be application/json");
    }

    /** The contract has no 405: an unknown path or method names no operation. */
    @ExceptionHandler({NoResourceFoundException.class, HttpRequestMethodNotSupportedException.class})
    ResponseEntity<ProblemDetail> noOperation(Exception e) {
        return respond(ProblemKind.NOT_FOUND, "the operation was not found");
    }

    @ExceptionHandler(Exception.class)
    ResponseEntity<ProblemDetail> unexpected(Exception e) {
        LOG.error("unhandled failure {}", e.getClass().getName());
        return respond(ProblemKind.INTERNAL_ERROR, "an internal error occurred");
    }

    private static ResponseEntity<ProblemDetail> respond(ProblemKind kind, String detail) {
        ProblemDetail problem = ProblemDetail.forStatus(HttpStatus.valueOf(kind.status()));
        problem.setType(URI.create(kind.type()));
        problem.setTitle(kind.title());
        problem.setDetail(detail);
        return ResponseEntity.status(kind.status()).contentType(MediaType.APPLICATION_PROBLEM_JSON).body(problem);
    }
}

package com.quancrypt.analyzer.api.error;

import com.quancrypt.analyzer.facade.error.ApiProblemException;
import com.quancrypt.analyzer.facade.error.ProblemKind;
import java.net.URI;
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
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.web.servlet.resource.NoResourceFoundException;

/**
 * Renders every failure as RFC 9457 problem details with the problem types of the contract. Details are fixed sentences
 * or use case sentences; the query and the body are never reflected (the `instance` is the request path, which names no
 * project), and unexpected failures show nothing but "internal error" (the log gets the class name only).
 */
@RestControllerAdvice
public class ProblemAdvice {

    private static final Logger LOG = LoggerFactory.getLogger(ProblemAdvice.class);

    @ExceptionHandler(ApiProblemException.class)
    ResponseEntity<ProblemDetail> problem(ApiProblemException e) {
        return respond(e.kind(), e.getMessage());
    }

    @ExceptionHandler({HttpMessageNotReadableException.class, MissingServletRequestParameterException.class,
        MethodArgumentTypeMismatchException.class, HttpMediaTypeNotAcceptableException.class,
        HttpMediaTypeNotSupportedException.class, org.apache.tomcat.util.http.InvalidParameterException.class})
    ResponseEntity<ProblemDetail> malformed(Exception e) {
        return respond(ProblemKind.VALIDATION_FAILED, "the request is malformed: check the JSON, the parameters and the contract");
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

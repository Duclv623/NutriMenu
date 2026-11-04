package com.menufood.userservice.exception;

import com.menufood.userservice.dto.response.ErrorResponse;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

@RestControllerAdvice
public class GlobalExceptionHandler {
    @ExceptionHandler(ResourceNotFoundException.class)
    public ResponseEntity<ErrorResponse> handleNotFound(ResourceNotFoundException exception,
                                                       HttpServletRequest request) {
        return error(HttpStatus.NOT_FOUND, exception.getMessage(), request, Map.of());
    }

    @ExceptionHandler(DuplicateEmailException.class)
    public ResponseEntity<ErrorResponse> handleDuplicateEmail(DuplicateEmailException exception,
                                                             HttpServletRequest request) {
        return error(HttpStatus.CONFLICT, exception.getMessage(), request, Map.of());
    }

    @ExceptionHandler(DataIntegrityViolationException.class)
    public ResponseEntity<ErrorResponse> handleConflict(HttpServletRequest request) {
        return error(HttpStatus.CONFLICT, "Dữ liệu bị trùng hoặc vi phạm ràng buộc", request, Map.of());
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ErrorResponse> handleValidation(MethodArgumentNotValidException exception,
                                                         HttpServletRequest request) {
        Map<String, String> errors = new LinkedHashMap<>();
        exception.getBindingResult().getFieldErrors()
                .forEach(field -> errors.put(field.getField(), field.getDefaultMessage()));
        return error(HttpStatus.BAD_REQUEST, "Dữ liệu không hợp lệ", request, errors);
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ErrorResponse> handleInvalidJson(HttpServletRequest request) {
        return error(HttpStatus.BAD_REQUEST, "JSON, ngày tháng hoặc giá trị enum không hợp lệ", request, Map.of());
    }

    private ResponseEntity<ErrorResponse> error(HttpStatus status, String message,
                                               HttpServletRequest request, Map<String, String> errors) {
        return ResponseEntity.status(status).body(new ErrorResponse(
                Instant.now(), status.value(), message, request.getRequestURI(), errors));
    }
}

package com.example.mealoptimizerservice.exception;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import java.time.LocalDateTime;
import java.util.stream.Collectors;

public class OptimizerBusinessException extends RuntimeException {
    private final HttpStatus status;
    public OptimizerBusinessException(HttpStatus status, String message) {
        super(message);
        this.status = status;
    }
    public HttpStatus getStatus() { return status; }
}

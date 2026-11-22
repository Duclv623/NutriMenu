package com.example.foodcatalogservice.exception;

import org.springframework.http.HttpStatus;

public class BusinessRuleException extends RuntimeException {
    private final HttpStatus status;

    public BusinessRuleException(HttpStatus status, String message) {
        super(message);
        this.status = status;
    }

    public HttpStatus getStatus() {
        return status;
    }
}

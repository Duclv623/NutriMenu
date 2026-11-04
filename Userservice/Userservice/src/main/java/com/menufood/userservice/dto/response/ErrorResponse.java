package com.menufood.userservice.dto.response;

import lombok.AllArgsConstructor;
import lombok.Getter;

import java.time.Instant;
import java.util.Map;

@Getter
@AllArgsConstructor
public class ErrorResponse {
    private final Instant timestamp;
    private final int status;
    private final String message;
    private final String path;
    private final Map<String, String> errors;
}

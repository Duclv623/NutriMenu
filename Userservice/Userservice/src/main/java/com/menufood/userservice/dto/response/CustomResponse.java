package com.menufood.userservice.dto.response;

import lombok.AllArgsConstructor;
import lombok.Getter;

@Getter
@AllArgsConstructor
public class CustomResponse<T> {
    private final boolean success;
    private final T data;
    private final String message;
}

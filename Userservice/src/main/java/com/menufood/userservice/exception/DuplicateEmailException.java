package com.menufood.userservice.exception;

public class DuplicateEmailException extends RuntimeException {
    public DuplicateEmailException() {
        super("Email đã được sử dụng");
    }
}

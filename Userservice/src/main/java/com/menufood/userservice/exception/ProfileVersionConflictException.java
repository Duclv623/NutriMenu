package com.menufood.userservice.exception;

public class ProfileVersionConflictException extends RuntimeException {
    public ProfileVersionConflictException() {
        super("Hồ sơ đã thay đổi hoặc thiếu phiên bản hiện tại. Hãy tải lại trước khi lưu.");
    }
}

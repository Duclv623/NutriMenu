package com.menufood.userservice.dto.response;

import lombok.Builder;
import lombok.Getter;

import java.time.Instant;
import java.util.UUID;

@Getter
@Builder
public class UserResponseDTO {
    private UUID id;
    private String email;
    private String fullName;
    private String role;
    private Instant createdAt;
}

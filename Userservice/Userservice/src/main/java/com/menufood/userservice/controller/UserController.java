package com.menufood.userservice.controller;

import com.menufood.userservice.dto.request.UserProfileRequestDTO;
import com.menufood.userservice.dto.response.CustomResponse;
import com.menufood.userservice.dto.response.UserProfileResponseDTO;
import com.menufood.userservice.dto.response.UserResponseDTO;
import com.menufood.userservice.service.UserProfileService;
import com.menufood.userservice.service.UserService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/users/me")
@RequiredArgsConstructor
public class UserController {
    private final UserService userService;
    private final UserProfileService userProfileService;

    @GetMapping
    public CustomResponse<UserResponseDTO> getCurrentUser(Authentication authentication) {
        return new CustomResponse<>(true, userService.getCurrentUser(authentication.getName()),
                "Lấy thông tin tài khoản thành công");
    }

    @GetMapping("/profile")
    public CustomResponse<UserProfileResponseDTO> getProfile(Authentication authentication) {
        return new CustomResponse<>(true, userProfileService.getProfile(authentication.getName()),
                "Lấy hồ sơ dinh dưỡng thành công");
    }

    @PutMapping("/profile")
    public CustomResponse<UserProfileResponseDTO> saveProfile(Authentication authentication,
                                                             @Valid @RequestBody UserProfileRequestDTO request) {
        return new CustomResponse<>(true, userProfileService.saveProfile(authentication.getName(), request),
                "Lưu hồ sơ dinh dưỡng thành công");
    }
}

package com.menufood.userservice.controller;

import com.menufood.userservice.dto.request.RegisterRequestDTO;
import com.menufood.userservice.dto.response.CustomResponse;
import com.menufood.userservice.dto.response.UserResponseDTO;
import com.menufood.userservice.service.UserService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/api/auth")
@RequiredArgsConstructor
public class AuthController {
    private final UserService userService;

    @GetMapping("/csrf")
    public Map<String, String> csrf(CsrfToken token) {
        return Map.of("headerName", token.getHeaderName(), "token", token.getToken());
    }

    @PostMapping("/register")
    @ResponseStatus(HttpStatus.CREATED)
    public CustomResponse<UserResponseDTO> register(@Valid @RequestBody RegisterRequestDTO request) {
        return new CustomResponse<>(true, userService.register(request), "Đăng ký thành công");
    }
}

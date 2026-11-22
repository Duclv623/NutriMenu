package com.menufood.userservice.service;

import com.menufood.userservice.dto.request.RegisterRequestDTO;
import com.menufood.userservice.dto.response.UserResponseDTO;
import com.menufood.userservice.entity.User;
import com.menufood.userservice.exception.DuplicateEmailException;
import com.menufood.userservice.exception.ResourceNotFoundException;
import com.menufood.userservice.repository.UserRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.Locale;

@Service
@RequiredArgsConstructor
public class UserService {
    private final UserRepository userRepository;
    private final PasswordEncoder passwordEncoder;

    @Transactional
    public UserResponseDTO register(RegisterRequestDTO request) {
        String email = request.getEmail().strip().toLowerCase(Locale.ROOT);
        if (userRepository.existsByEmail(email)) {
            throw new DuplicateEmailException();
        }

        User user = new User();
        user.setEmail(email);
        user.setPasswordHash(passwordEncoder.encode(request.getPassword()));
        user.setFullName(request.getFullName().strip());
        return toResponse(userRepository.saveAndFlush(user));
    }

    @Transactional(readOnly = true)
    public UserResponseDTO getCurrentUser(String email) {
        User user = userRepository.findByEmail(email)
                .orElseThrow(() -> new ResourceNotFoundException("Không tìm thấy tài khoản"));
        return toResponse(user);
    }

    private UserResponseDTO toResponse(User user) {
        return UserResponseDTO.builder()
                .id(user.getId())
                .email(user.getEmail())
                .fullName(user.getFullName())
                .role(user.getRole())
                .createdAt(user.getCreatedAt())
                .build();
    }
}

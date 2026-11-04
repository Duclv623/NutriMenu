package com.menufood.userservice.service;

import com.menufood.userservice.dto.request.UserProfileRequestDTO;
import com.menufood.userservice.dto.response.UserProfileResponseDTO;
import com.menufood.userservice.entity.User;
import com.menufood.userservice.entity.UserProfile;
import com.menufood.userservice.exception.ResourceNotFoundException;
import com.menufood.userservice.repository.UserProfileRepository;
import com.menufood.userservice.repository.UserRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.time.LocalDate;
import java.time.Period;
import java.util.LinkedHashSet;
import java.util.Set;
import java.util.stream.Collectors;

@Service
@RequiredArgsConstructor
public class UserProfileService {
    private final UserRepository userRepository;
    private final UserProfileRepository userProfileRepository;

    @Transactional(readOnly = true)
    public UserProfileResponseDTO getProfile(String email) {
        User user = findUser(email);
        UserProfile profile = userProfileRepository.findById(user.getId())
                .orElseThrow(() -> new ResourceNotFoundException("Bạn chưa tạo hồ sơ dinh dưỡng"));
        return toResponse(profile);
    }

    @Transactional
    public UserProfileResponseDTO saveProfile(String email, UserProfileRequestDTO request) {
        User user = findUser(email);
        UserProfile profile = userProfileRepository.findById(user.getId()).orElseGet(() -> {
            UserProfile newProfile = new UserProfile();
            newProfile.setUser(user);
            return newProfile;
        });

        profile.setDateOfBirth(request.getDateOfBirth());
        profile.setGender(request.getGender());
        profile.setHeight(request.getHeight());
        profile.setWeight(request.getWeight());
        profile.setActivityLevel(request.getActivityLevel());
        profile.setGoal(request.getGoal());
        profile.setTargetWeight(request.getTargetWeight());
        profile.getAllergies().clear();
        profile.getAllergies().addAll(normalize(request.getAllergies()));
        profile.getRestrictedIngredients().clear();
        profile.getRestrictedIngredients().addAll(normalize(request.getRestrictedIngredients()));
        profile.getPreferences().clear();
        profile.getPreferences().addAll(normalize(request.getPreferences()));
        // Cập nhật thời điểm cả khi chỉ thay đổi các danh sách ăn uống.
        profile.setUpdatedAt(Instant.now());

        return toResponse(userProfileRepository.saveAndFlush(profile));
    }

    private User findUser(String email) {
        return userRepository.findByEmail(email)
                .orElseThrow(() -> new ResourceNotFoundException("Không tìm thấy tài khoản"));
    }

    private Set<String> normalize(Set<String> values) {
        return values.stream().map(String::strip)
                .collect(Collectors.toCollection(LinkedHashSet::new));
    }

    private UserProfileResponseDTO toResponse(UserProfile profile) {
        return UserProfileResponseDTO.builder()
                .userId(profile.getUserId())
                .dateOfBirth(profile.getDateOfBirth())
                .age(Period.between(profile.getDateOfBirth(), LocalDate.now()).getYears())
                .gender(profile.getGender())
                .height(profile.getHeight())
                .weight(profile.getWeight())
                .activityLevel(profile.getActivityLevel())
                .goal(profile.getGoal())
                .targetWeight(profile.getTargetWeight())
                .allergies(new LinkedHashSet<>(profile.getAllergies()))
                .restrictedIngredients(new LinkedHashSet<>(profile.getRestrictedIngredients()))
                .preferences(new LinkedHashSet<>(profile.getPreferences()))
                .updatedAt(profile.getUpdatedAt())
                .build();
    }
}

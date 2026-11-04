package com.menufood.userservice.dto.response;

import com.menufood.userservice.entity.ActivityLevel;
import com.menufood.userservice.entity.Gender;
import com.menufood.userservice.entity.WeightGoal;
import lombok.Builder;
import lombok.Getter;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.Set;
import java.util.UUID;

@Getter
@Builder
public class UserProfileResponseDTO {
    private UUID userId;
    private LocalDate dateOfBirth;
    private int age;
    private Gender gender;
    private BigDecimal height;
    private BigDecimal weight;
    private ActivityLevel activityLevel;
    private WeightGoal goal;
    private BigDecimal targetWeight;
    private Set<String> allergies;
    private Set<String> restrictedIngredients;
    private Set<String> preferences;
    private Instant updatedAt;
}

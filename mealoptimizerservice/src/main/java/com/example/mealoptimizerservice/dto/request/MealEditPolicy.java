package com.example.mealoptimizerservice.dto.request;

import com.example.mealoptimizerservice.entity.enums.MedicalTag;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.PositiveOrZero;

import java.util.Set;
import java.util.HashSet;

import com.example.mealoptimizerservice.entity.MealPlan;

public record MealEditPolicy(
        @NotNull @PositiveOrZero Long expectedVersion,
        @NotNull Set<@Positive Long> excludedDishIds,
        @NotNull Set<MedicalTag> contraindications) {
    public MealEditPolicy withRecordedFilters(MealPlan plan) {
        Set<Long> dishes = new HashSet<>(plan.getExcludedDishIds());
        dishes.addAll(excludedDishIds);
        Set<MedicalTag> tags = new HashSet<>(plan.getContraindications());
        tags.addAll(contraindications);
        return new MealEditPolicy(expectedVersion, dishes, tags);
    }
}

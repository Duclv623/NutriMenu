package com.example.mealoptimizerservice.dto;

import com.example.mealoptimizerservice.entity.MealPlan;
import com.example.mealoptimizerservice.entity.MealPlanItem;
import com.example.mealoptimizerservice.entity.enums.*;
import jakarta.validation.constraints.*;
import lombok.*;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.*;

// --- DTO giao tiếp với Food Catalog Service ---
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class DishSolverDto {
    private Long dishId;
    private String code;
    private String nameVi;
    private DishRole role;
    private IngredientGroup ingredientGroup;
    private Set<MealSlot> validMealSlots;
    private long caloriesX10;
    private long netCarbX10;
    private long fiberX10;
    private long proteinX10;
    private long fatX10;
    private long glX10;
    private int minServingX2;
    private int maxServingX2;
    private int stepServingX2;
    private int basePreferenceScore;
    private String householdUnitLabel;
    private Map<Long, RawIngredientNeedDto> rawIngredientsPerServing;

    @Data
    @NoArgsConstructor
    @AllArgsConstructor
    @Builder
    public static class RawIngredientNeedDto {
        private Long ingredientId;
        private String ingredientNameVi;
        private IngredientGroup group;
        private BigDecimal rawWeightG;
    }
}

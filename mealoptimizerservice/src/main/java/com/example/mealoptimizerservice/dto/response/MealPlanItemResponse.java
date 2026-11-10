package com.example.mealoptimizerservice.dto.response;

import com.example.mealoptimizerservice.entity.MealPlan;
import com.example.mealoptimizerservice.entity.MealPlanItem;
import com.example.mealoptimizerservice.entity.enums.*;
import jakarta.validation.constraints.*;
import lombok.*;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.*;

@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class MealPlanItemResponse {
    private Long itemId;
    private MealSlot mealSlot;
    private Long dishId;
    private String dishCode;
    private String dishNameVi;
    private DishRole dishRole;
    private IngredientGroup ingredientGroup;
    private Integer servingScaledX2;
    private BigDecimal servingMultiplier;
    private String householdUnitDisplay;
    private BigDecimal caloriesKcal;
    private BigDecimal netCarbG;
    private BigDecimal fiberG;
    private BigDecimal proteinG;
    private BigDecimal fatG;
    private BigDecimal glycemicLoad;
    private MealItemStatus status;
    private Boolean isLocked;

    public static MealPlanItemResponse fromEntity(MealPlanItem item) {
        return MealPlanItemResponse.builder()
                .itemId(item.getId())
                .mealSlot(item.getMealSlot())
                .dishId(item.getDishId())
                .dishCode(item.getDishCode())
                .dishNameVi(item.getDishNameVi())
                .dishRole(item.getDishRole())
                .ingredientGroup(item.getIngredientGroup())
                .servingScaledX2(item.getServingScaledX2())
                .servingMultiplier(item.getServingMultiplier())
                .householdUnitDisplay(item.getHouseholdUnitDisplay())
                .caloriesKcal(item.getSnapshotCaloriesKcal())
                .netCarbG(item.getSnapshotNetCarbG())
                .fiberG(item.getSnapshotFiberG())
                .proteinG(item.getSnapshotProteinG())
                .fatG(item.getSnapshotFatG())
                .glycemicLoad(item.getSnapshotGl())
                .status(item.getStatus())
                .isLocked(item.getIsLocked())
                .build();
    }
}

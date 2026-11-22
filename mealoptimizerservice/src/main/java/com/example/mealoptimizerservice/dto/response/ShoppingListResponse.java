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
public class ShoppingListResponse {
    private LocalDate fromDate;
    private LocalDate toDate;
    private int totalMealsIncluded;
    private List<ShoppingItemDto> items;

    @Data
    @NoArgsConstructor
    @AllArgsConstructor
    @Builder
    public static class ShoppingItemDto {
        private Long ingredientId;
        private String ingredientNameVi;
        private IngredientGroup group;
        private BigDecimal totalRawWeightG;
    }
}

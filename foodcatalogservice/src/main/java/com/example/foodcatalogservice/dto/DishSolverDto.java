package com.example.foodcatalogservice.dto;
import com.example.foodcatalogservice.entity.enums.DishRole;
import com.example.foodcatalogservice.entity.enums.IngredientGroup;
import com.example.foodcatalogservice.entity.enums.MealSlot;
import lombok.*;

import java.util.Set;
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
}
package com.example.foodcatalogservice.dto;
import lombok.*;

import java.math.BigDecimal;

@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class RecipeIngredientBreakdownDto {
    private Long ingredientId;
    private String ingredientNameVi;
    private BigDecimal rawWeightG;
    private BigDecimal appliedYieldFactor;
    private BigDecimal cookedWeightG;
    private boolean isMainIngredient;
}
